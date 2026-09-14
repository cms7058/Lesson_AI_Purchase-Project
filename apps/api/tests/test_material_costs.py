from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Role": "procurement_manager", "X-User-Id": "cost-manager"}


def test_custom_category_codes_and_industry_imports():
    root = client.post("/api/v1/material-categories", headers=MANAGER, json={"name":"自定义分类","code_segment":"XYZ"}).json()
    second = client.post("/api/v1/material-categories", headers=MANAGER,json={"name":"机械件","parent_id":root["id"],"code_segment":"M1"}).json()
    leaf = client.post("/api/v1/material-categories",headers=MANAGER,json={"name":"轴类","parent_id":second["id"],"code_segment":"SHAFT"}).json()
    assert leaf["code"] == "XYZ-M1-SHAFT"
    assert leaf["path_name"] == "自定义分类 / 机械件 / 轴类"
    assert client.post("/api/v1/material-categories",headers=MANAGER,json={"name":"重复编码","code_segment":"xyz"}).status_code == 409
    assert client.post("/api/v1/material-categories",headers=MANAGER,json={"name":"无效编码","code_segment":"A-B"}).status_code == 422
    assert client.get(f"/api/v1/material-categories/{leaf['id']}/next-material-code").json()["code"] == "XYZ-M1-SHAFT-0001"
    preview = client.get("/api/v1/material-categories/industry-templates/nonstandard").json()
    assert len(preview["items"]) == 26
    assert client.post("/api/v1/material-categories/import/nonstandard",headers={"X-User-Role":"buyer"}).status_code == 403
    first = client.post("/api/v1/material-categories/import/nonstandard",headers=MANAGER)
    assert first.status_code == 200
    assert first.json()["created"] == 26
    assert client.post("/api/v1/material-categories/import/nonstandard",headers=MANAGER).json() == {"created":0,"skipped":26}
    tree = client.get("/api/v1/material-categories/tree").json()
    assert any(row["code"] == "NS-03-01" and row["level"] == 3 for row in tree)


def test_import_conflict_rolls_back_whole_batch():
    root = client.post("/api/v1/material-categories",headers=MANAGER,json={"name":"汽车零部件制造","code_segment":"AUTO"}).json()
    client.post("/api/v1/material-categories",headers=MANAGER,json={"name":"企业自定义名称","code_segment":"02","parent_id":root["id"]})
    response = client.post("/api/v1/material-categories/import/automotive",headers=MANAGER)
    assert response.status_code == 409
    tree = client.get("/api/v1/material-categories/tree").json()
    assert not any(row["code"] == "AUTO-01" for row in tree)


def make_receipt(code, accepted=8, inspected=10):
    order = client.post("/api/v1/orders",headers=MANAGER,json={"supplier_id":"SUP-COST","supplier_name":"成本测试供应商","factory_code":"F1","lines":[{"material_code":code,"material_name":"测试轴","quantity":10,"unit_price":10,"unit":"件","tax_rate":0,"delivery_date":"2026-01-01"}]}).json()
    receipt = client.post("/api/v1/receipts",headers=MANAGER,json={"order_id":order["id"],"material_code":code,"material_name":"测试轴","received_quantity":10,"received_date":"2026-01-03"}).json()
    assert client.post(f"/api/v1/receipts/{receipt['id']}/confirm",headers=MANAGER).status_code == 200
    assert client.post("/api/v1/inspections",headers=MANAGER,json={"receipt_id":receipt["id"],"inspected_quantity":inspected,"accepted_quantity":accepted,"rejected_quantity":inspected-accepted}).status_code == 201
    return receipt


def test_material_cost_adjustment_history_and_guardrails():
    code = f"COST-{uuid4().hex[:8]}"
    receipt = make_receipt(code)
    query = {"material_code":code,"currency":"CNY"}
    initial = client.get("/api/v1/material-costs/summary",params=query).json()
    assert initial["counts"]["orders"] == 1
    assert Decimal(str(initial["suppliers"][0]["corrected_unit_cost"])) == Decimal("12.5")
    payload = {"logistics":10,"rework":20,"delay":10,"credit":10,"basis":"actual","evidence":"凭证 FEE-001；供应商退款 CR-001"}
    endpoint = f"/api/v1/material-costs/receipts/{receipt['id']}/adjustment"
    assert client.put(endpoint,headers={"X-User-Role":"buyer"},json=payload).status_code == 403
    assert client.put(endpoint,headers=MANAGER,json=payload).status_code == 200
    group = client.get("/api/v1/material-costs/summary",params=query).json()["suppliers"][0]
    assert Decimal(str(group["corrected_unit_cost"])) == Decimal("16.25")
    assert Decimal(str(group["corrected_amount"])) == 130
    assert group["confirmed_batches"] == 1
    history = client.get("/api/v1/material-costs/history/receipts",params={**query,"page_size":1}).json()
    assert history["total"] == 1
    assert history["items"][0]["late_days"] == 2
    assert history["items"][0]["evidence"] == payload["evidence"]
    assert client.put(endpoint,headers=MANAGER,json={**payload,"credit":999}).status_code == 422
    assert client.put(endpoint,headers=MANAGER,json={**payload,"logistics":-1}).status_code == 422
    assert client.get("/api/v1/material-costs/summary",params={**query,"currency":"USD"}).json()["suppliers"] == []
    assert client.delete(endpoint,headers=MANAGER).status_code == 204
    assert client.get("/api/v1/material-costs/history/receipts",params=query).json()["items"][0]["basis"] == "unconfirmed"


def test_partial_and_zero_accepted_receipts_do_not_invent_unit_costs():
    partial_code = f"PART-{uuid4().hex[:8]}"
    partial = make_receipt(partial_code,accepted=4,inspected=5)
    rows = client.get("/api/v1/material-costs/history/receipts",params={"material_code":partial_code}).json()["items"]
    assert rows[0]["eligible"] is False
    assert rows[0]["corrected_unit_cost"] is None
    assert client.put(f"/api/v1/material-costs/receipts/{partial['id']}/adjustment",headers=MANAGER,json={"evidence":"测试估算"}).status_code == 409
    zero_code = f"ZERO-{uuid4().hex[:8]}"
    make_receipt(zero_code,accepted=0)
    group = client.get("/api/v1/material-costs/summary",params={"material_code":zero_code}).json()["suppliers"][0]
    assert group["corrected_unit_cost"] is None
    assert Decimal(str(group["corrected_amount"])) == 100


def test_comparison_snapshots_are_immutable_and_currency_separated():
    code = f"SNAP-{uuid4().hex[:8]}"
    quotes = []
    for currency in ["CNY","USD"]:
        response = client.post("/api/v1/quotations",headers=MANAGER,json={"supplier_id":"SUP-SNAP","supplier_name":"快照供应商","currency":currency,"lines":[{"material_code":code,"material_name":"测试物料","quantity":10,"unit_price":10,"unit":"件","tax_rate":0}]})
        assert response.status_code == 201
        quotes.append(response.json())
    assert client.get("/api/v1/quotations/compare",params={"material_code":code,"quantity":10}).status_code == 409
    params = {"material_code":code,"quantity":10,"currency":"CNY"}
    compared = client.get("/api/v1/quotations/compare",params=params,headers=MANAGER)
    assert compared.status_code == 200
    client.patch(f"/api/v1/quotations/{quotes[0]['id']}",headers=MANAGER,json={"delivery_days":99})
    history = client.get("/api/v1/material-costs/history/comparisons",params=params).json()
    assert history["total"] == 1
    assert history["items"][0]["result"] == compared.json()
    assert client.get("/api/v1/material-costs/history/comparisons",params={**params,"currency":"USD"}).json()["total"] == 0

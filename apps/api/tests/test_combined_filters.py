import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.list_filters import SPECS, field_type, fields_for

client = TestClient(app)
H = {"X-User-Role": "admin"}


def query(resource, filters, **params):
    return client.get(f"/api/v1/{resource}", headers=H, params={"page": 1, "page_size": 1, "filters": json.dumps(filters), **params})


def f(field, value, op="eq"):
    return {"field": field, "op": op, "value": value}


@pytest.mark.parametrize("resource", [r for r in SPECS if not r.startswith("supplier/")])
def test_every_registered_list_filters_count_and_rows(resource):
    field = next(k for k, v in fields_for(resource).items() if field_type(v) == "text")
    response = query(resource, [f(field, "DOES-NOT-EXIST-"+uuid4().hex)])
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0, response.text
    assert response.json()["items"] == [], response.text


def test_order_compound_relations_and_page_count():
    tag = uuid4().hex[:8]
    orders = []
    for i in range(3):
        r = client.post("/api/v1/orders", headers=H, json={"supplier_id":tag,"supplier_name":"组合供应商"+tag,"factory_code":"F1","lines":[{"material_code":"MATCH-"+tag,"material_name":"测试","quantity":5,"unit":"件","unit_price":10},{"material_code":"OTHER","material_name":"完整明细","quantity":1,"unit":"件","unit_price":1}]})
        assert r.status_code == 201, r.text
        orders.append(r.json())
    filters = [f("supplier_name", tag, "contains"), f("material_code", "MATCH-"+tag), f("status", "draft"), f("created_at", "2020-01-01T00:00:00", "gte")]
    first = query("orders", filters).json()
    second = query("orders", filters, page=2).json()
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert len(first["items"][0]["lines"]) == 2  # filtering must not truncate child rows
    assert query("orders", filters+[f("order_no", orders[0]["order_no"])]).json()["total"] == 1
    assert query("orders", [f("supplier_name", "' OR 1=1 --")]).json()["total"] == 0
    assert query("orders", [f("supplier_name", "%", "contains")]).json()["total"] == 0


def test_type_validation_and_no_filter_leak():
    for condition in [f("password_hash", "secret"), f("status", 1), f("created_at", "bad-date"), f("status", "x", "sql")]:
        assert query("orders", [condition]).status_code == 422
    assert query("materials", [f("standard_price", "NaN")]).status_code == 422
    assert query("materials", [f("active", "true")]).status_code == 422
    assert query("materials", [f("standard_price", 0, "gte"), f("active", True)]).status_code == 200
    assert client.get("/api/v1/orders", headers=H).json()["total"] > 0


def test_order_status_trace_and_completion():
    tag = uuid4().hex[:8]
    order = client.post("/api/v1/orders", headers=H, json={"supplier_id":tag,"supplier_name":tag,"factory_code":"F1","lines":[{"material_code":tag,"material_name":"测试","quantity":5,"unit":"件","unit_price":10}]}).json()
    url = "/api/v1/orders/"+order["id"]
    assert client.patch(url, headers=H, json={"status":"completed"}).status_code == 409
    assert client.patch(url, headers=H, json={"status":"supplier_confirmed"}).status_code == 200
    receipt = client.post("/api/v1/receipts", headers=H, json={"order_id":order["id"],"material_code":tag,"material_name":"测试","received_quantity":5}).json()
    assert client.post(f"/api/v1/receipts/{receipt['id']}/confirm", headers=H).status_code == 200
    assert query("orders", [f("order_no",order["order_no"]),f("status","quality_tracking")]).json()["total"] == 1
    assert client.patch(url, headers=H, json={"status":"draft"}).status_code == 409
    assert client.post("/api/v1/inspections", headers=H, json={"receipt_id":receipt["id"],"inspected_quantity":5,"accepted_quantity":5,"rejected_quantity":0}).status_code == 201
    trace = client.get(url+"/trace", headers=H, params={"kind":"inspections"}).json()
    assert trace["total"] == 1 and trace["status"] == "completed"
    assert trace["items"][0]["receipt_id"] == receipt["id"]
    assert client.get(url+"/trace?kind=secrets",headers=H).status_code == 422


def test_contextual_rfq_demo_is_explicit_idempotent_and_never_formal():
    from app.core.database import SessionLocal
    from app.domain.persistence import (
        QuotationLineRecord,
        QuotationRecord,
        RFQInvitationRecord,
        RFQLineRecord,
        RFQRecord,
    )
    tag = uuid4().hex[:8]
    with SessionLocal.begin() as db:
        quote = QuotationRecord(quotation_no="COM-Q-"+tag,supplier_id="COM-S-"+tag,supplier_name="测试供应商",currency="CNY",lines=[QuotationLineRecord(material_code=tag,material_name="测试物料",quantity=10,unit="件",unit_price=20,tax_rate=.13)])
        db.add(quote)
        db.flush()
        rfq = RFQRecord(rfq_no="COM-RFQ-"+tag,title="组合测试",currency="CNY",status="published",lines=[RFQLineRecord(material_code=tag,material_name="测试物料",quantity=10,unit="件")],invitations=[RFQInvitationRecord(supplier_id=quote.supplier_id,supplier_name=quote.supplier_name,quotation_id=quote.id,status="responded")])
        db.add(rfq)
        db.flush()
        url, qid = f"/api/v1/rfqs/{rfq.id}", quote.id
    assert query("rfqs",[f("material_code",tag),f("supplier_name","测试供应商"),f("status","published")]).json()["total"] == 1
    assert client.post(url+"/demo-feedback",headers={"X-User-Role":"buyer"}).status_code == 403
    response = client.post(url+"/demo-feedback",headers=H)
    assert response.status_code == 200, response.text
    assert response.json()["inserted"] == 18
    assert client.post(url+"/demo-feedback",headers=H).json()["inserted"] == 0
    pending = client.get(url+"/award-analysis?include_demo=true",headers=H).json()
    assert not pending["tco_ready"] and pending["lowest_ids"] == []
    assert client.put(url+f"/quotations/{qid}/review",headers=H,json={"status":"verified","note":"组合测试核验"}).status_code == 200
    simulated = client.get(url+"/award-analysis?include_demo=true",headers=H).json()
    assert simulated["tco_ready"]
    assert simulated["items"][0]["materials"][0]["profile"]["regression"]
    assert not client.get(url+"/award-analysis",headers=H).json()["tco_ready"]
    assert client.post(url+"/award",headers=H,json={"method":"tco","quotation_id":qid}).status_code == 409


def test_partial_inspection_return_replacement_closes_order():
    tag = uuid4().hex[:8]
    order = client.post("/api/v1/orders",headers=H,json={"supplier_id":tag,"supplier_name":tag,"factory_code":"F1","lines":[{"material_code":tag,"material_name":"测试","quantity":5,"unit":"件","unit_price":10}]}).json()
    def receive(quantity):
        r = client.post("/api/v1/receipts",headers=H,json={"order_id":order["id"],"material_code":tag,"material_name":"测试","received_quantity":quantity})
        assert r.status_code == 201, r.text
        receipt = r.json()
        assert client.post(f"/api/v1/receipts/{receipt['id']}/confirm",headers=H).status_code == 200
        return receipt
    receipt = receive(5)
    for accepted, rejected in [(2,0),(1,2)]:
        result = client.post("/api/v1/inspections",headers=H,json={"receipt_id":receipt["id"],"inspected_quantity":accepted+rejected,"accepted_quantity":accepted,"rejected_quantity":rejected})
        assert result.status_code == 201, result.text
    ret = client.post("/api/v1/returns",headers=H,json={"receipt_id":receipt["id"],"quantity":2,"reason":"不合格退换"}).json()
    for status in ["sent","completed"]:
        assert client.patch(f"/api/v1/returns/{ret['id']}/status",headers=H,json={"status":status}).status_code == 200
    replacement = receive(2)
    assert client.post("/api/v1/inspections",headers=H,json={"receipt_id":replacement["id"],"inspected_quantity":2,"accepted_quantity":2,"rejected_quantity":0}).status_code == 201
    assert query("orders",[f("order_no",order["order_no"])]).json()["items"][0]["status"] == "completed"

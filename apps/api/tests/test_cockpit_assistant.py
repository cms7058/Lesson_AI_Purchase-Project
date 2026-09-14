from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from test_supplier_portal import scenario as scenario  # noqa: PLC0414

from app.core.database import SessionLocal
from app.domain.persistence import GoodsReceiptRecord
from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Role": "procurement_manager"}


def ask(message, **kwargs):
    return client.post("/api/v1/assistant/chat", headers=MANAGER, json={"message": message, **kwargs})


def test_free_conversation_and_followup():
    assert "你好" in ask("你好").json()["message"]
    response = ask("TOC是什么，如何计算？").json()
    assert "合格交付数量" in response["message"] and response["result"] is None
    response = ask("如何比较供应商？").json()
    assert "同一物料" in response["message"] and response["result"] is None
    response = ask("其中待送货的有哪些", history=[{"role": "user", "content": "请帮我看看采购订单"}]).json()
    assert response["result"]["resource"] == "orders"
    assert {"field": "status", "op": "eq", "value": "supplier_confirmed"} in response["result"]["filters"]


def test_category_aggregation_rolls_up_without_double_counting():
    from app.domain.persistence import (
        MaterialCategoryAssignmentRecord,
        MaterialCategoryRecord,
        MaterialRecord,
    )
    tag = uuid4().hex[:8]
    with SessionLocal() as db:
        parent = None
        for level in range(1, 4):
            node = MaterialCategoryRecord(code=f"CAT-{tag}-{level}", name=f"分类{level}", level=level, parent_id=parent, path_name=f"分类{level}")
            db.add(node); db.flush(); parent = node.id
        material = MaterialRecord(code=f"CM-{tag}", name="分类测试件", unit="件")
        db.add(material); db.flush()
        db.add(MaterialCategoryAssignmentRecord(material_id=material.id, category_id=parent)); db.commit()
    order = client.post('/api/v1/orders', headers=MANAGER, json={"supplier_id": tag, "supplier_name": tag, "factory_code": "F1", "lines": [{"material_code": f"CM-{tag}", "material_name": "测试", "quantity": 2, "unit": "件", "unit_price": 25}]}).json()
    result = client.get('/api/v1/analytics/cockpit', params={"supplier": order['supplier_name']}).json()
    assert len(result['category_amount']) == 3
    for row in result['category_amount']:
        assert row['value'] == 50 and sum(t['value'] for t in row['trend']) == 50


def test_assistant_resources_paging_and_permissions():
    for message, resource in [("查询订单", "orders"), ("查询询价单", "rfqs"), ("查询供应商", "suppliers"), ("查询物料", "materials"), ("查询价格", "quotations"), ("查询人员", "staff-users"), ("查询权限", "buyer-authorizations")]:
        response = ask(message, page_size=1)
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["resource"] == resource
        assert len(result["rows"]) <= 1
        assert sum(row["value"] for row in result["chart"]["data"]) <= result["total"]
    for resource in ["staff-users", "buyer-authorizations"]:
        assert client.post("/api/v1/assistant/chat", json={"message": "查询", "resource": resource}).status_code == 403
    assert ask("查询", resource="supplier-accounts").status_code == 422
    assert ask("查询订单", filters=[{"field": "password", "op": "eq", "value": "x"}]).status_code == 422
    assert ask("查询订单", page_size=1000).status_code == 422
    assert ask("查询订单", filters=[{"field": "order_no", "op": "eq", "value": "' OR 1=1 --"}]).json()["result"]["total"] == 0


def test_cockpit_linked_counts_currency_and_assistant_filter():
    supplier = "Cockpit-" + uuid4().hex[:8]
    for currency, quantity in [("CNY", 2), ("CNY", 3), ("USD", 100)]:
        response = client.post("/api/v1/orders", headers=MANAGER, json={"supplier_id": supplier, "supplier_name": supplier, "factory_code": "F01", "currency": currency, "lines": [{"material_code": "CHAT-M01", "material_name": "测试物料", "quantity": quantity, "unit": "件", "unit_price": 10}]})
        assert response.status_code == 201, response.text
    response = client.get("/api/v1/analytics/cockpit", params={"supplier": supplier, "currency": "CNY", "page_size": 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["kpis"]["order_count"] == 2
    assert data["kpis"]["purchase_amount"] == 50
    assert len(data["rows"]) == 1
    assert sum(x["value"] for x in data["order_status"]) == 2
    assert sum(x["value"] for x in data["trend"]) == 50
    assert sum(x["amount"] for x in data["buyer_timeline"]) == 50
    assert data["material_amount"] == [{"name": "CHAT-M01", "value": 50}]
    assert sum(x["value"] for x in data["supplier_amount"]) == 50
    assert client.get("/api/v1/analytics/cockpit", params={"supplier": supplier, "status": "completed"}).json()["total"] == 0
    assert client.get("/api/v1/analytics/cockpit?start=2026-09-10&end=2026-09-01").status_code == 422
    result = ask(f"查询订单 供应商名称：{supplier} 币种：CNY").json()["result"]
    assert result["total"] == 2
    result = ask("查询物料编码 CHAT-M01 的订单").json()["result"]
    assert result["total"] == 3


def test_supplier_assistant_scope(scenario):
    rfq, suppliers, sessions = scenario
    client.post(f"/api/v1/rfqs/{rfq['id']}/publish", headers=MANAGER)
    result = client.post("/api/v1/assistant/chat", headers=sessions[0], json={"message": "查询询价单"}).json()["result"]
    assert result["total"] == 1
    assert client.post("/api/v1/assistant/chat", headers=sessions[0], json={"message": "查询询价单", "filters": [{"field": "supplier_name", "op": "contains", "value": "其他供应商"}]}).status_code == 422
    for supplier in suppliers[:2]:
        response = client.post("/api/v1/orders", headers=MANAGER, json={"supplier_id": supplier["id"], "supplier_name": supplier["name"], "factory_code": "F01", "lines": [{"material_code": "M01", "material_name": "测试", "quantity": 1, "unit": "件", "unit_price": 10}]})
        assert response.status_code == 201
    result = client.post("/api/v1/assistant/chat", headers=sessions[0], json={"message": "查询订单"}).json()["result"]
    assert result["total"] == 0  # Draft orders are not supplier-visible.
    for resource in ["suppliers", "materials", "quotations", "staff-users", "buyer-authorizations"]:
        assert client.post("/api/v1/assistant/chat", headers=sessions[0], json={"message": "查询", "resource": resource}).status_code == 403
    greeting = client.post("/api/v1/assistant/chat", headers=sessions[0], json={"message": "你好"}).json()
    assert greeting["evidence"] == {}
    assert client.post("/api/v1/assistant/chat", headers={"Authorization": "Bearer invalid"}, json={"message": "查询订单"}).status_code == 401


def test_buyer_assignment_and_on_time_receipt_statistics():
    tag = uuid4().hex[:8]
    buyer = client.post('/api/v1/staff-users', headers=MANAGER, json={"user_code": "B-"+tag, "name": "采购员统计测试", "role": "buyer", "status": "active"}).json()
    response = client.post('/api/v1/orders', headers=MANAGER, json={"supplier_id": "BS-"+tag, "supplier_name": "统计供应商"+tag, "factory_code": "F1", "lines": [{"material_code": "M1", "material_name": "测试件", "quantity": 10, "unit": "件", "unit_price": 20, "delivery_date": "2026-09-03"}]})
    assert response.status_code == 201, response.text
    order = response.json()
    url = '/api/v1/analytics/order-buyers/'+order['id']
    assert client.put(url, json={"buyer_id": buyer['id']}).status_code == 403
    assert client.put(url, headers=MANAGER, json={"buyer_id": "missing"}).status_code == 422
    assert client.put(url, headers=MANAGER, json={"buyer_id": buyer['id']}).status_code == 200
    with SessionLocal() as db:
        for index, (day, status) in enumerate([(2, "received"), (4, "inspected"), (1, "draft")]):
            db.add(GoodsReceiptRecord(receipt_no=f'BR-{tag}-{index}', order_id=order['id'], order_no=order['order_no'], supplier_name=order['supplier_name'], factory_code='F1', material_code='M1', material_name='测试件', received_quantity=1, received_date=date(2026,9,day), status=status))
        db.commit()
    result = client.get('/api/v1/analytics/cockpit', params={"buyer": buyer['id']}).json()
    assert result['total'] == 1
    row = result['buyer_stats'][0]
    assert row['order_count'] == 1 and row['amount'] == 200
    assert result['buyer_timeline'][0]['buyer_id'] == buyer['id']
    assert result['buyer_timeline'][0]['amount'] == 200
    assert row['eligible_receipts'] == 2 and row['on_time_receipts'] == 1
    assert row['on_time_rate'] == 50
    assert result['buyer_supplier_delivery'][0]['on_time_rate'] == 50
    assert client.delete('/api/v1/staff-users/'+buyer['id'],headers=MANAGER).status_code == 409
    assert client.put(url, headers=MANAGER, json={"buyer_id": None}).status_code == 200
    assert client.get('/api/v1/analytics/cockpit',params={"buyer":buyer['id']}).json()['total']==0

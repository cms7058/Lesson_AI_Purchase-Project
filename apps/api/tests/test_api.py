from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_modules_include_full_scope() -> None:
    response = client.get("/api/v1/modules")
    codes = {item["code"] for item in response.json()}
    assert {"orders", "forecast", "sourcing", "routing", "workflows", "templates", "materials", "personnel"} <= codes


def test_create_order_calculates_total() -> None:
    response = client.post(
        "/api/v1/orders",
        json={
            "supplier_id": "SUP-001",
            "supplier_name": "示例供应商",
            "factory_code": "F01",
            "currency": "CNY",
            "lines": [
                {
                    "material_code": "MAT-001",
                    "material_name": "航空维修件",
                    "quantity": "10",
                    "unit": "件",
                    "unit_price": "100",
                    "tax_rate": "0.13",
                }
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["total_amount"] == "1130.00"


def test_buyer_cannot_create_data_connector() -> None:
    response = client.post(
        "/api/v1/data-connectors",
        json={"name": "ERP生产系统", "connector_type": "erp"},
    )
    assert response.status_code == 403


def test_manager_can_create_data_connector_and_audit_log() -> None:
    headers = {"X-User-Id": "manager-001", "X-User-Role": "procurement_manager"}
    connector_name = f"ERP生产系统-测试-{uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/data-connectors",
        headers=headers,
        json={
            "name": connector_name, "connector_type": "erp", "sync_mode": "scheduled"
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    connector = response.json()
    updated = client.patch(
        f"/api/v1/data-connectors/{connector['id']}",
        headers=headers,
        json={"status": "active", "sync_mode": "manual"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"
    page = client.get("/api/v1/data-connectors?page=1&page_size=10", headers=headers).json()
    assert any(item["id"] == connector["id"] for item in page["items"])
    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert any(item["resource_type"] == "data_connector" for item in logs.json()["items"])
    assert client.delete(f"/api/v1/data-connectors/{connector['id']}", headers=headers).status_code == 204


def test_tco_comparison_recommends_best_overall_quote() -> None:
    headers = {"X-User-Id": "buyer-001", "X-User-Role": "buyer"}
    material_code = f"MAT-TOC-{uuid4().hex[:8]}"
    shared_line = {"material_code": material_code, "material_name": "航空维修组件", "quantity": "100", "unit": "件", "tax_rate": "0.13"}
    first = client.post(
        "/api/v1/quotations",
        headers=headers,
        json={
            "supplier_id": "SUP-A", "supplier_name": "供应商A", "delivery_days": 18,
            "service_score": "88", "quality_pass_rate": "99", "lines": [{**shared_line, "unit_price": "100", "logistics_cost": "200", "expected_quality_loss": "50"}],
        },
    )
    second = client.post(
        "/api/v1/quotations",
        headers=headers,
        json={
            "supplier_id": "SUP-B", "supplier_name": "供应商B", "delivery_days": 8,
            "service_score": "92", "quality_pass_rate": "99.5", "lines": [{**shared_line, "unit_price": "101", "logistics_cost": "0", "expected_quality_loss": "0"}],
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201
    result = client.get(f"/api/v1/quotations/compare?material_code={material_code}&quantity=100", headers=headers)
    assert result.status_code == 200
    assert result.json()["items"][0]["supplier_name"] == "供应商B"
    assert result.json()["methodology"].startswith("TOC=")


def test_order_template_renders_order_fields() -> None:
    headers = {"X-User-Id": "manager-002", "X-User-Role": "procurement_manager"}
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "supplier_id": "SUP-TPL", "supplier_name": "模板供应商", "factory_code": "F02",
            "lines": [{"material_code": "MAT-TPL", "material_name": "模板物料", "quantity": "5", "unit": "件", "unit_price": "20"}],
        },
    ).json()
    template = client.post(
        "/api/v1/templates",
        headers=headers,
        json={
            "name": f"订单模板-{uuid4().hex[:8]}", "template_type": "order",
            "content": "订单：{{order_no}}；供应商：{{supplier_name}}；物料：{{material_name}}；数量：{{quantity}} {{unit}}",
        },
    ).json()
    rendered = client.post(f"/api/v1/templates/{template['id']}/render/orders/{order['id']}", headers=headers)
    assert rendered.status_code == 200
    assert "模板供应商" in rendered.json()["content"]
    assert rendered.json()["placeholders_unresolved"] == []


def test_paginated_order_list_and_update() -> None:
    response = client.get("/api/v1/orders?page=1&page_size=2")
    assert response.status_code == 200
    assert {"items", "page", "page_size", "total"} <= response.json().keys()
    if response.json()["items"]:
        order = response.json()["items"][0]
        update = client.patch(
            f"/api/v1/orders/{order['id']}",
            headers={"X-User-Role": "procurement_manager"},
            json={"payment_terms": "验收后30天付款"},
        )
        assert update.status_code == 200
        assert update.json()["payment_terms"] == "验收后30天付款"


def test_quote_can_link_quotation_template() -> None:
    headers = {"X-User-Id": "manager-003", "X-User-Role": "procurement_manager"}
    template = client.post(
        "/api/v1/templates",
        headers=headers,
        json={"name": f"报价模板-{uuid4().hex[:8]}", "template_type": "quotation", "content": "报价单 {{supplier_name}}"},
    ).json()
    material_code = f"MAT-LINK-{uuid4().hex[:8]}"
    quote = client.post(
        "/api/v1/quotations",
        headers=headers,
        json={"supplier_id": "SUP-LINK", "supplier_name": "关联供应商", "lines": [{"material_code": material_code, "material_name": "关联物料", "quantity": 1, "unit": "件", "unit_price": 1}]},
    ).json()
    linked = client.post(
        "/api/v1/template-links",
        headers=headers,
        json={"document_type": "quotation", "document_id": quote["id"], "template_id": template["id"]},
    )
    assert linked.status_code == 201
    assert linked.json()["document_id"] == quote["id"]


def test_order_template_exports_docx_and_pdf() -> None:
    headers = {"X-User-Id": "manager-export", "X-User-Role": "procurement_manager"}
    order = client.post("/api/v1/orders", headers=headers, json={"supplier_id": "SUP-EXPORT", "supplier_name": "导出供应商", "factory_code": "F01", "lines": [{"material_code": "MAT-EXPORT", "material_name": "导出物料", "quantity": 1, "unit": "件", "unit_price": 100}]}).json()
    template = client.post("/api/v1/templates", headers=headers, json={"name": f"导出订单模板-{uuid4().hex[:8]}", "template_type": "order", "content": "订单 {{order_no}}\n供应商 {{supplier_name}}\n物料 {{material_name}}"}).json()
    for output_format in ("docx", "pdf"):
        result = client.post(f"/api/v1/documents/order/{order['id']}/export", headers=headers, json={"template_id": template["id"], "output_format": output_format})
        assert result.status_code == 200
        assert result.json()["download_url"].endswith(output_format)


def test_supplier_master_data_crud_search_and_pagination() -> None:
    headers = {"X-User-Id": "manager-master", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    created = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={
            "code": f"SUP-{suffix}",
            "name": f"航空维修供应商-{suffix}",
            "category": "航空维修件",
            "status": "qualified",
            "risk_level": "medium",
        },
    )
    assert created.status_code == 201
    supplier = created.json()
    listed = client.get(
        f"/api/v1/suppliers?page=1&page_size=10&keyword={suffix}&status=qualified"
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["code"] == f"SUP-{suffix}"
    updated = client.patch(
        f"/api/v1/suppliers/{supplier['id']}",
        headers=headers,
        json={"risk_level": "low"},
    )
    assert updated.status_code == 200
    assert updated.json()["risk_level"] == "low"
    deleted = client.delete(f"/api/v1/suppliers/{supplier['id']}", headers=headers)
    assert deleted.status_code == 204


def test_material_and_factory_master_data_are_operable() -> None:
    headers = {"X-User-Id": "manager-master", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    material = client.post(
        "/api/v1/materials",
        headers=headers,
        json={
            "code": f"MAT-{suffix}",
            "name": "航空维修组件",
            "specification": "AMM-TEST",
            "standard_price": 1200,
            "safety_stock": 20,
            "lead_time_days": 30,
        },
    )
    factory = client.post(
        "/api/v1/factories",
        headers=headers,
        json={
            "code": f"F-{suffix}",
            "name": "华东维修工厂",
            "address": "上海市",
            "latitude": 31.2304,
            "longitude": 121.4737,
            "daily_receiving_capacity": 500,
        },
    )
    assert material.status_code == 201
    assert factory.status_code == 201
    assert client.get(f"/api/v1/materials?keyword={suffix}").json()["total"] == 1
    assert client.get(f"/api/v1/factories?keyword={suffix}").json()["total"] == 1
    assert client.delete(f"/api/v1/materials/{material.json()['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/factories/{factory.json()['id']}", headers=headers).status_code == 204


def test_buyer_cannot_maintain_master_data() -> None:
    response = client.post(
        "/api/v1/materials",
        headers={"X-User-Role": "buyer"},
        json={"code": f"MAT-{uuid4().hex[:8]}", "name": "无权创建物料"},
    )
    assert response.status_code == 403


def test_requisition_approval_and_order_conversion_closed_loop() -> None:
    buyer = {"X-User-Id": "buyer-requisition", "X-User-Role": "buyer"}
    manager = {"X-User-Id": "manager-requisition", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    created = client.post(
        "/api/v1/requisitions",
        headers=buyer,
        json={
            "title": f"航空维修备件补库-{suffix}",
            "factory_code": "F-EAST",
            "department": "维修保障部",
            "cost_center": "CC-MRO",
            "priority": "urgent",
            "needed_date": "2026-10-01",
            "reason": "安全库存不足",
            "lines": [{
                "material_code": f"MAT-REQ-{suffix}", "material_name": "维修组件",
                "quantity": 10, "unit": "件", "estimated_unit_price": 125,
            }],
        },
    )
    assert created.status_code == 201
    request = created.json()
    assert request["estimated_total"] == "1250.00"
    submitted = client.post(f"/api/v1/requisitions/{request['id']}/submit", headers=buyer)
    assert submitted.json()["status"] == "pending_approval"
    forbidden = client.post(
        f"/api/v1/requisitions/{request['id']}/decision",
        headers=buyer,
        json={"approved": True},
    )
    assert forbidden.status_code == 403
    approved = client.post(
        f"/api/v1/requisitions/{request['id']}/decision",
        headers=manager,
        json={"approved": True, "comment": "预算与交期满足要求"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    converted = client.post(
        f"/api/v1/requisitions/{request['id']}/convert-to-order",
        headers=buyer,
        json={"supplier_id": "SUP-DEMO", "supplier_name": "华东维修供应商"},
    )
    assert converted.status_code == 201
    assert converted.json()["factory_code"] == "F-EAST"
    assert converted.json()["lines"][0]["unit_price"] == "125.0000"
    listed = client.get(f"/api/v1/requisitions?keyword={suffix}&status=converted").json()
    assert listed["total"] == 1
    assert listed["items"][0]["order_id"] == converted.json()["id"]


def test_requisition_status_rules_prevent_invalid_changes() -> None:
    headers = {"X-User-Role": "procurement_manager"}
    created = client.post(
        "/api/v1/requisitions",
        headers=headers,
        json={"title": "状态校验申请", "factory_code": "F01", "lines": [{"material_code": "MAT-STATE", "material_name": "状态物料", "quantity": 1}]},
    ).json()
    client.post(f"/api/v1/requisitions/{created['id']}/submit", headers=headers)
    locked_update = client.patch(
        f"/api/v1/requisitions/{created['id']}", headers=headers, json={"title": "不应更新"}
    )
    locked_delete = client.delete(f"/api/v1/requisitions/{created['id']}", headers=headers)
    assert locked_update.status_code == 409
    assert locked_delete.status_code == 409


def test_formal_rfq_publish_response_and_award_flow() -> None:
    buyer = {"X-User-Id": "buyer-rfq", "X-User-Role": "buyer"}
    manager = {"X-User-Id": "manager-rfq", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    supplier_id = f"SUP-RFQ-{suffix}"
    material_code = f"MAT-RFQ-{suffix}"
    rfq = client.post(
        "/api/v1/rfqs",
        headers=buyer,
        json={"title": f"维修件正式询价-{suffix}", "deadline": "2026-10-15", "lines": [{"material_code": material_code, "material_name": "维修件", "quantity": 5}], "invitations": [{"supplier_id": supplier_id, "supplier_name": "受邀供应商"}]},
    )
    assert rfq.status_code == 201
    project = rfq.json()
    assert client.post(f"/api/v1/rfqs/{project['id']}/publish", headers=buyer).json()["status"] == "published"
    quote = client.post(
        "/api/v1/quotations",
        headers=buyer,
        json={"supplier_id": supplier_id, "supplier_name": "受邀供应商", "lines": [{"material_code": material_code, "material_name": "维修件", "quantity": 5, "unit": "件", "unit_price": 100}]},
    ).json()
    linked = client.post(f"/api/v1/rfqs/{project['id']}/responses", headers=buyer, json={"quotation_id": quote["id"]})
    assert linked.status_code == 200
    assert linked.json()["invitations"][0]["status"] == "responded"
    reviewed = client.put(f"/api/v1/rfqs/{project['id']}/quotations/{quote['id']}/review", headers=buyer, json={"status": "verified", "note": "已核验测试报价"})
    assert reviewed.status_code == 200
    assert client.post(f"/api/v1/rfqs/{project['id']}/award", headers=buyer, json={"quotation_id": quote["id"]}).status_code == 403
    awarded = client.post(f"/api/v1/rfqs/{project['id']}/award", headers=manager, json={"quotation_id": quote["id"]})
    assert awarded.status_code == 200
    assert awarded.json()["status"] == "awarded"
    assert client.get(f"/api/v1/rfqs?keyword={suffix}&status=awarded").json()["total"] == 1


def test_receiving_quality_return_and_payment_closed_loop() -> None:
    headers = {"X-User-Id": "manager-fulfillment", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    order = client.post(
        "/api/v1/orders", headers=headers,
        json={"supplier_id": "SUP-FLOW", "supplier_name": "履约供应商", "factory_code": "F01", "lines": [{"material_code": f"MAT-FLOW-{suffix}", "material_name": "履约物料", "quantity": 10, "unit": "件", "unit_price": 100}]},
    ).json()
    receipt = client.post(
        "/api/v1/receipts", headers=headers,
        json={"order_id": order["id"], "material_code": f"MAT-FLOW-{suffix}", "material_name": "履约物料", "received_quantity": 10},
    )
    assert receipt.status_code == 201
    receipt_id = receipt.json()["id"]
    assert client.post(f"/api/v1/receipts/{receipt_id}/confirm", headers=headers).json()["status"] == "received"
    inspection = client.post(
        "/api/v1/inspections", headers=headers,
        json={"receipt_id": receipt_id, "inspected_quantity": 10, "accepted_quantity": 8, "rejected_quantity": 2, "defect_description": "尺寸超差"},
    )
    assert inspection.status_code == 201
    assert inspection.json()["result"] == "partial"
    purchase_return = client.post(
        "/api/v1/returns", headers=headers,
        json={"receipt_id": receipt_id, "quantity": 2, "reason": "质检不合格退货"},
    )
    assert purchase_return.status_code == 201
    return_id = purchase_return.json()["id"]
    assert client.patch(f"/api/v1/returns/{return_id}/status", headers=headers, json={"status": "sent"}).status_code == 200
    assert client.patch(f"/api/v1/returns/{return_id}/status", headers=headers, json={"status": "completed"}).json()["status"] == "completed"
    reconciliation = client.post(
        "/api/v1/reconciliations", headers=headers,
        json={"order_id": order["id"], "amount": 1130, "adjustment_amount": -226, "remark": "扣除不合格品"},
    )
    assert reconciliation.status_code == 201
    reconciliation_id = reconciliation.json()["id"]
    assert client.post(f"/api/v1/reconciliations/{reconciliation_id}/confirm", headers=headers).json()["status"] == "confirmed"
    invoice = client.post(
        "/api/v1/invoices", headers=headers,
        json={"invoice_no": f"INV-{suffix}", "reconciliation_id": reconciliation_id, "amount": 904, "tax_amount": 104},
    )
    assert invoice.status_code == 201
    invoice_id = invoice.json()["id"]
    assert client.patch(f"/api/v1/invoices/{invoice_id}/status", headers=headers, json={"status": "verified"}).json()["status"] == "verified"
    payment = client.post(
        "/api/v1/payments", headers=headers,
        json={"invoice_id": invoice_id, "amount": 904, "planned_date": "2026-11-01"},
    )
    assert payment.status_code == 201
    payment_id = payment.json()["id"]
    assert client.patch(f"/api/v1/payments/{payment_id}/status", headers=headers, json={"status": "approved"}).json()["status"] == "approved"
    paid = client.patch(f"/api/v1/payments/{payment_id}/status", headers=headers, json={"status": "paid"})
    assert paid.status_code == 200
    assert paid.json()["paid_date"] is not None
    for path in ("receipts", "inspections", "returns", "reconciliations", "invoices", "payments"):
        result = client.get(f"/api/v1/{path}?page=1&page_size=10")
        assert result.status_code == 200
        assert result.json()["total"] >= 1


def test_workflow_approval_and_notification_closed_loop() -> None:
    headers = {"X-User-Id": "manager-workflow", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    created = client.post(
        "/api/v1/workflows",
        headers=headers,
        json={
            "name": f"订单审批通知-{suffix}",
            "business_type": "order",
            "trigger_type": "manual",
            "steps": [
                {"name": "采购经理审批", "action": "approval"},
                {
                    "name": "发送订单通知",
                    "action": "email",
                    "recipient": "buyer@example.com",
                    "subject": "订单流程通知",
                    "content": "订单 {{business_id}} 已进入处理流程",
                },
            ],
        },
    )
    assert created.status_code == 201
    workflow = created.json()
    assert workflow["status"] == "draft"
    activated = client.patch(
        f"/api/v1/workflows/{workflow['id']}",
        headers=headers,
        json={"status": "active"},
    )
    assert activated.status_code == 200
    executed = client.post(
        f"/api/v1/workflows/{workflow['id']}/execute",
        headers=headers,
        json={"business_id": "PO-WORKFLOW-001"},
    )
    assert executed.status_code == 201
    run = executed.json()
    assert run["status"] == "awaiting_approval"
    assert run["result"]["steps"][0]["status"] == "waiting"
    outbox_before_approval = client.get(
        "/api/v1/notification-outbox?page=1&page_size=100"
    ).json()
    assert not any(
        item["workflow_run_id"] == run["id"] for item in outbox_before_approval["items"]
    )
    approved = client.post(f"/api/v1/workflow-runs/{run['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    outbox = client.get("/api/v1/notification-outbox?page=1&page_size=100").json()
    notice = next(item for item in outbox["items"] if item["workflow_run_id"] == run["id"])
    assert notice["recipient"] == "buyer@example.com"
    assert "PO-WORKFLOW-001" in notice["body"]
    dispatch = client.post(
        f"/api/v1/notification-outbox/{notice['id']}/dispatch", headers=headers
    )
    assert dispatch.status_code == 409
    assert "SMTP" in dispatch.json()["detail"]
    runs = client.get("/api/v1/workflow-runs?page=1&page_size=10").json()
    assert any(item["id"] == run["id"] for item in runs["items"])


def test_workflow_permissions_pagination_and_delete() -> None:
    manager = {"X-User-Role": "procurement_manager"}
    buyer = {"X-User-Role": "buyer"}
    suffix = uuid4().hex[:8]
    forbidden = client.post(
        "/api/v1/workflows",
        headers=buyer,
        json={
            "name": f"无权创建-{suffix}",
            "business_type": "quotation",
            "trigger_type": "manual",
            "steps": [{"name": "审批", "action": "approval"}],
        },
    )
    assert forbidden.status_code == 403
    created = client.post(
        "/api/v1/workflows",
        headers=manager,
        json={
            "name": f"可删除工作流-{suffix}",
            "business_type": "contract",
            "trigger_type": "status_change",
            "steps": [{"name": "创建合同文件", "action": "create_document"}],
        },
    )
    assert created.status_code == 201
    listed = client.get("/api/v1/workflows?page=1&page_size=10")
    assert listed.status_code == 200
    assert listed.json()["page_size"] == 10
    deleted = client.delete(f"/api/v1/workflows/{created.json()['id']}", headers=manager)
    assert deleted.status_code == 204


def test_contract_template_approval_export_and_termination_flow() -> None:
    buyer = {"X-User-Id": "buyer-contract", "X-User-Role": "buyer"}
    manager = {"X-User-Id": "manager-contract", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    template = client.post(
        "/api/v1/templates",
        headers=manager,
        json={
            "name": f"合同审批模板-{suffix}",
            "template_type": "contract",
            "content": "{{company_name}}\n合同 {{contract_no}}\n供应商 {{supplier_name}}",
        },
    ).json()
    created = client.post(
        "/api/v1/contracts",
        headers=buyer,
        json={
            "title": f"维修件年度合同-{suffix}",
            "supplier_id": "SUP-CONTRACT",
            "supplier_name": "合同供应商",
            "amount": 200000,
            "effective_date": "2026-10-01",
            "expiry_date": "2027-09-30",
            "template_id": template["id"],
        },
    )
    assert created.status_code == 201
    contract = created.json()
    listed = client.get("/api/v1/contracts?page=1&page_size=100").json()
    listed_contract = next(item for item in listed["items"] if item["id"] == contract["id"])
    assert listed_contract["template_id"] == template["id"]
    filtered = client.get(f"/api/v1/contracts?keyword={suffix}&status=draft").json()
    assert filtered["total"] == 1
    assert client.post(f"/api/v1/contracts/{contract['id']}/submit", headers=buyer).json()["status"] == "pending_approval"
    assert client.patch(f"/api/v1/contracts/{contract['id']}", headers=buyer, json={"amount": 1}).status_code == 409
    assert client.post(f"/api/v1/contracts/{contract['id']}/decision", headers=buyer, json={"approved": True}).status_code == 403
    approved = client.post(
        f"/api/v1/contracts/{contract['id']}/decision",
        headers=manager,
        json={"approved": True, "comment": "条款与预算审核通过"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"
    exported = client.post(
        f"/api/v1/documents/contract/{contract['id']}/export",
        headers=manager,
        json={"template_id": template["id"], "output_format": "pdf"},
    )
    assert exported.status_code == 200
    assert exported.json()["download_url"].endswith(".pdf")
    terminated = client.post(f"/api/v1/contracts/{contract['id']}/terminate", headers=manager)
    assert terminated.status_code == 200
    assert terminated.json()["status"] == "terminated"
    assert client.delete(f"/api/v1/contracts/{contract['id']}", headers=manager).status_code == 409


def test_contract_reject_returns_to_editable_draft_and_validates_dates() -> None:
    manager = {"X-User-Role": "procurement_manager"}
    invalid = client.post(
        "/api/v1/contracts",
        headers=manager,
        json={"title": "日期错误合同", "supplier_id": "SUP-DATE", "supplier_name": "日期供应商", "amount": 1, "effective_date": "2027-01-01", "expiry_date": "2026-01-01"},
    )
    assert invalid.status_code == 422
    wrong_template = client.post(
        "/api/v1/templates",
        headers=manager,
        json={"name": f"错误订单模板-{uuid4().hex[:8]}", "template_type": "order", "content": "这是订单业务模板"},
    ).json()
    wrong_link = client.post(
        "/api/v1/contracts",
        headers=manager,
        json={"title": "错误模板合同", "supplier_id": "SUP-WRONG", "supplier_name": "错误模板供应商", "amount": 1, "template_id": wrong_template["id"]},
    )
    assert wrong_link.status_code == 404
    contract = client.post(
        "/api/v1/contracts",
        headers=manager,
        json={"title": "可驳回合同", "supplier_id": "SUP-REJECT", "supplier_name": "驳回供应商", "amount": 100},
    ).json()
    client.post(f"/api/v1/contracts/{contract['id']}/submit", headers=manager)
    rejected = client.post(
        f"/api/v1/contracts/{contract['id']}/decision",
        headers=manager,
        json={"approved": False, "comment": "请补充付款条款"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "draft"
    assert client.patch(f"/api/v1/contracts/{contract['id']}", headers=manager, json={"amount": 120}).status_code == 200
    assert client.delete(f"/api/v1/contracts/{contract['id']}", headers=manager).status_code == 204


def test_demand_forecast_regression_and_purchase_recommendation_crud() -> None:
    headers = {"X-User-Id": "analyst-plan", "X-User-Role": "analyst"}
    suffix = uuid4().hex[:8]
    created = client.post(
        "/api/v1/forecasts", headers=headers,
        json={"name": f"轴承需求预测-{suffix}", "material_code": f"MAT-FC-{suffix}", "material_name": "航空轴承", "history": [{"period": f"2026-{month:02d}", "quantity": quantity} for month, quantity in enumerate([100, 110, 120, 130, 140, 150], 1)], "horizon": 3, "safety_stock": 50, "on_hand": 100, "in_transit": 20},
    )
    assert created.status_code == 201
    item = created.json()
    assert item["result"]["predicted"] == [160.0, 170.0, 180.0]
    assert item["result"]["recommended_purchase"] == 440.0
    updated = client.patch(f"/api/v1/forecasts/{item['id']}", headers=headers, json={"on_hand": 200})
    assert updated.status_code == 200
    assert updated.json()["result"]["recommended_purchase"] == 340.0
    assert client.get(f"/api/v1/forecasts?keyword={suffix}&page_size=10").json()["total"] == 1
    assert client.delete(f"/api/v1/forecasts/{item['id']}", headers=headers).status_code == 204


def test_external_sourcing_candidate_ranking_crud() -> None:
    headers = {"X-User-Id": "buyer-source", "X-User-Role": "buyer"}
    suffix = uuid4().hex[:8]
    created = client.post(
        "/api/v1/sourcing-projects", headers=headers,
        json={"name": f"航空维修件寻源-{suffix}", "category": "航空维修件", "requirements": "AS9100，30天交付", "candidates": [{"supplier_name": "高质量供应商", "country": "中国", "capabilities": "AS9100", "price_score": 82, "quality_score": 96, "delivery_score": 90, "risk_level": "low"}, {"supplier_name": "高风险低价供应商", "country": "海外", "price_score": 98, "quality_score": 75, "delivery_score": 65, "risk_level": "high"}]},
    )
    assert created.status_code == 201
    item = created.json()
    evaluated = client.post(f"/api/v1/sourcing-projects/{item['id']}/evaluate", headers=headers)
    assert evaluated.status_code == 200
    assert evaluated.json()["result"]["recommended_supplier"] == "高质量供应商"
    assert evaluated.json()["status"] == "evaluated"
    updated = client.patch(f"/api/v1/sourcing-projects/{item['id']}", headers=headers, json={"requirements": "增加EASA认证"})
    assert updated.json()["status"] == "draft"
    assert client.delete(f"/api/v1/sourcing-projects/{item['id']}", headers=headers).status_code == 204


def test_multi_factory_min_cost_routing_optimization_crud() -> None:
    headers = {"X-User-Id": "analyst-route", "X-User-Role": "analyst"}
    suffix = uuid4().hex[:8]
    created = client.post(
        "/api/v1/routing-plans", headers=headers,
        json={"name": f"双工厂分配-{suffix}", "material_code": f"MAT-RT-{suffix}", "supplies": [{"supplier": "S1", "capacity": 100}, {"supplier": "S2", "capacity": 100}], "demands": [{"factory": "F1", "quantity": 80}, {"factory": "F2", "quantity": 70}], "lanes": [{"supplier": "S1", "factory": "F1", "unit_cost": 5, "lead_days": 1, "risk_score": 0}, {"supplier": "S1", "factory": "F2", "unit_cost": 9, "lead_days": 1, "risk_score": 0}, {"supplier": "S2", "factory": "F1", "unit_cost": 8, "lead_days": 1, "risk_score": 0}, {"supplier": "S2", "factory": "F2", "unit_cost": 4, "lead_days": 1, "risk_score": 0}], "lead_weight": 0, "risk_weight": 0},
    )
    assert created.status_code == 201
    item = created.json()
    optimized = client.post(f"/api/v1/routing-plans/{item['id']}/optimize", headers=headers)
    assert optimized.status_code == 200
    result = optimized.json()["result"]
    assert result["feasible"] is True
    assert result["allocated"] == 150
    assert result["total_transport_cost"] == 680
    assert client.patch(f"/api/v1/routing-plans/{item['id']}", headers=headers, json={"lead_weight": 2}).json()["status"] == "draft"
    assert client.delete(f"/api/v1/routing-plans/{item['id']}", headers=headers).status_code == 204


def test_procurement_report_generation_crud() -> None:
    headers = {"X-User-Id": "manager-report", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    created = client.post("/api/v1/reports", headers=headers, json={"title": f"采购运营报告-{suffix}", "report_type": "overview", "notes": "月度管理层报告"})
    assert created.status_code == 201
    item = created.json()
    generated = client.post(f"/api/v1/reports/{item['id']}/generate", headers=headers)
    assert generated.status_code == 200
    assert generated.json()["status"] == "generated"
    assert "quality_pass_rate" in generated.json()["content"]["summary"]
    assert len(generated.json()["content"]["insights"]) == 3
    assert client.get(f"/api/v1/reports?keyword={suffix}&status=generated").json()["total"] == 1
    assert client.patch(f"/api/v1/reports/{item['id']}", headers=headers, json={"notes": "更新说明"}).json()["status"] == "draft"
    assert client.delete(f"/api/v1/reports/{item['id']}", headers=headers).status_code == 204


def test_ai_assistant_uses_live_workspace_data_without_model_configuration() -> None:
    response = client.post(
        "/api/v1/assistant/chat",
        json={"message": "帮我查询采购数据并生成分析报告", "context_module": "workspace"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert "采购数据概览" in result["message"]
    assert "采购订单" in result["evidence"]
    assert "生成采购报告" in result["suggested_tools"]


def test_three_level_material_numbering_staff_authorization_and_supplier_links() -> None:
    manager = {"X-User-Id": "manager-org", "X-User-Role": "procurement_manager"}
    buyer_header = {"X-User-Id": "buyer-org", "X-User-Role": "buyer"}
    suffix = uuid4().hex[:8]
    root = client.post("/api/v1/material-categories", headers=manager, json={"name": f"机械类-{suffix}"})
    assert root.status_code == 201
    assert root.json()["code"] == "01"
    assert root.json()["level"] == 1
    second = client.post("/api/v1/material-categories", headers=manager, json={"name": "航空维修件", "parent_id": root.json()["id"]})
    assert second.status_code == 201
    assert second.json()["code"] == "01-01"
    third = client.post("/api/v1/material-categories", headers=manager, json={"name": "轴承组件", "parent_id": second.json()["id"]})
    assert third.status_code == 201
    assert third.json()["code"] == "01-01-01"
    assert third.json()["path_name"] == f"机械类-{suffix} / 航空维修件 / 轴承组件"
    too_deep = client.post("/api/v1/material-categories", headers=manager, json={"name": "第四级", "parent_id": third.json()["id"]})
    assert too_deep.status_code == 409
    assert client.get("/api/v1/material-categories?page=1&page_size=10&level=3").json()["total"] == 1
    material = client.post("/api/v1/materials", headers=manager, json={"code": f"MAT-ORG-{suffix}", "name": "三级分类物料"}).json()
    assigned = client.put(f"/api/v1/materials/{material['id']}/category", headers=manager, json={"material_id": material["id"], "category_id": third.json()["id"]})
    assert assigned.status_code == 200
    supplier = client.post("/api/v1/suppliers", headers=manager, json={"code": f"SUP-ORG-{suffix}", "name": "分类供应商", "status": "qualified"}).json()
    linked = client.post("/api/v1/supplier-category-links", headers=manager, json={"supplier_id": supplier["id"], "category_id": third.json()["id"], "qualification_status": "qualified"})
    assert linked.status_code == 201
    assert linked.json()["category_code"] == "01-01-01"
    assert client.post("/api/v1/supplier-category-links", headers=manager, json={"supplier_id": supplier["id"], "category_id": third.json()["id"]}).status_code == 409
    staff = client.post("/api/v1/staff-users", headers=manager, json={"user_code": f"BUY-{suffix}", "name": "航空件采购员", "email": "buyer@example.com", "role": "buyer"})
    assert staff.status_code == 201
    authorization = client.post("/api/v1/buyer-authorizations", headers=manager, json={"buyer_id": staff.json()["id"], "category_id": second.json()["id"], "valid_from": "2026-01-01", "valid_to": "2026-12-31"})
    assert authorization.status_code == 201
    assert authorization.json()["effective"] is True
    assert authorization.json()["category_level"] == 2
    assert client.post("/api/v1/buyer-authorizations", headers=manager, json={"buyer_id": staff.json()["id"], "category_id": second.json()["id"], "valid_from": "2026-06-01", "valid_to": "2027-01-31"}).status_code == 409
    assert client.post("/api/v1/staff-users", headers=buyer_header, json={"user_code": "NO-AUTH", "name": "无权人员"}).status_code == 403
    assert client.delete(f"/api/v1/material-categories/{third.json()['id']}", headers=manager).status_code == 409
    assert client.delete(f"/api/v1/buyer-authorizations/{authorization.json()['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/supplier-category-links/{linked.json()['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/staff-users/{staff.json()['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/materials/{material['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/suppliers/{supplier['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/material-categories/{third.json()['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/material-categories/{second.json()['id']}", headers=manager).status_code == 204
    assert client.delete(f"/api/v1/material-categories/{root.json()['id']}", headers=manager).status_code == 204


def test_procurement_analytics_shape() -> None:
    response = client.get("/api/v1/analytics/procurement")
    assert response.status_code == 200
    result = response.json()
    assert {"order_count", "purchase_amount", "supplier_count", "high_risk_supplier_count", "material_count"} <= result["kpis"].keys()
    assert {"order_status", "supplier_risk", "supplier_performance", "supplier_amount", "category_distribution"} <= result.keys()

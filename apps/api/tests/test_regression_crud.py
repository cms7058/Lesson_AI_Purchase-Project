from uuid import uuid4

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain import persistence as p
from app.main import app
from app.seed_demo import demo_id, seed

client=TestClient(app)
HEADERS={"X-User-Role":"procurement_manager","X-User-Id":"regression-manager"}


@pytest.mark.parametrize("kind,model", [("orders", p.PurchaseOrderRecord), ("quotations", p.QuotationRecord)])
def test_line_edits_are_persisted(kind, model):
    body=payload_for(kind, uuid4().hex[:8])
    created=client.post(f"/api/v1/{kind}", headers=HEADERS, json=body)
    assert created.status_code==201, created.text
    item_id=created.json()["id"]
    lines=[{**body["lines"][0], "quantity":7, "unit_price":31}, {**body["lines"][0], "material_code":"QA-SECOND", "quantity":2, "unit_price":19}]
    changed=client.patch(f"/api/v1/{kind}/{item_id}", headers=HEADERS, json={"lines":lines, "supplier_name":"编辑后的供应商"})
    assert changed.status_code==200, changed.text
    with SessionLocal() as db:
        record=db.get(model,item_id)
        assert len(record.lines)==2
        assert record.lines[0].quantity==7
        assert record.lines[0].unit_price==31
        assert record.supplier_name=="编辑后的供应商"
    assert client.delete(f"/api/v1/{kind}/{item_id}",headers=HEADERS).status_code==204


def test_receipt_inspection_and_return_quantity_guards():
    order=client.post("/api/v1/orders",headers=HEADERS,json=payload_for("orders",uuid4().hex[:8])).json()
    body={"order_id":order["id"],"material_code":order["lines"][0]["material_code"],"material_name":"数量测试","received_quantity":6}
    receipt=client.post("/api/v1/receipts",headers=HEADERS,json=body)
    assert receipt.status_code==201,receipt.text
    rid=receipt.json()["id"]
    assert client.post("/api/v1/receipts",headers=HEADERS,json=body).status_code==409
    assert client.patch(f"/api/v1/receipts/{rid}",headers=HEADERS,json={"received_quantity":11}).status_code==409
    assert client.post(f"/api/v1/receipts/{rid}/confirm",headers=HEADERS).status_code==200
    inspection={"receipt_id":rid,"inspected_quantity":6,"accepted_quantity":2,"rejected_quantity":4,"rework_quantity":7}
    assert client.post("/api/v1/inspections",headers=HEADERS,json=inspection).status_code==422
    inspection["rework_quantity"]=0
    assert client.post("/api/v1/inspections",headers=HEADERS,json=inspection).status_code==201
    returned={"receipt_id":rid,"quantity":3,"reason":"回归测试"}
    assert client.post("/api/v1/returns",headers=HEADERS,json=returned).status_code==201
    assert client.post("/api/v1/returns",headers=HEADERS,json=returned).status_code==409


def test_payment_cumulative_limit():
    with SessionLocal() as db:
        amount=float(db.get(p.SupplierInvoiceRecord,demo_id("invoice")).amount)
    result=client.post("/api/v1/payments",headers=HEADERS,json={"invoice_id":demo_id("invoice"),"amount":amount})
    assert result.status_code==409,result.text
    result=client.patch(f"/api/v1/payments/{demo_id('payment')}",headers=HEADERS,json={"amount":amount+1})
    assert result.status_code==409,result.text


def test_template_link_rejects_wrong_type_and_missing_document():
    body={"document_type":"quotation","document_id":str(uuid4()),"template_id":demo_id("template-quotation")}
    assert client.post("/api/v1/template-links",headers=HEADERS,json=body).status_code==404
    body["template_id"]=demo_id("template-order")
    assert client.post("/api/v1/template-links",headers=HEADERS,json=body).status_code==409


def test_docx_export_with_blank_lines(tmp_path):
    from app.services.document_export_service import DocumentExportService
    path=tmp_path / "blank-lines.docx"
    profile=p.CompanyProfileRecord(company_name="测试公司",short_name="TEST")
    DocumentExportService()._docx(path,profile,"order","第一行\n\n第三行")
    text=[p.text for p in Document(path).paragraphs]
    assert "第一行" in text and "第三行" in text


def test_quotation_template_can_be_changed_and_cleared():
    quote=client.post("/api/v1/quotations",headers=HEADERS,json=payload_for("quotations",uuid4().hex[:8])).json()
    url=f"/api/v1/quotations/{quote['id']}"
    linked=client.patch(url,headers=HEADERS,json={"template_id":demo_id("template-quotation")})
    assert linked.status_code==200,linked.text
    assert linked.json()["template_id"]==demo_id("template-quotation")
    invalid=client.patch(url,headers=HEADERS,json={"template_id":demo_id("template-order")})
    assert invalid.status_code==409
    cleared=client.patch(url,headers=HEADERS,json={"template_id":None})
    assert cleared.status_code==200 and cleared.json()["template_id"] is None
    assert client.delete(url,headers=HEADERS).status_code==204


@pytest.fixture(scope="module", autouse=True)
def demo_fixture():
    with SessionLocal.begin() as db:
        seed(db)


def payload_for(kind, tag):
    line={"material_code":f"QA-{tag}","material_name":"回归测试物料","quantity":10,"unit":"件","unit_price":20,"estimated_unit_price":20}
    simple={
        "suppliers":{"code":f"QA-{tag}","name":f"回归供应商{tag}"},
        "materials":{"code":f"QA-{tag}","name":"回归物料"},
        "factories":{"code":f"QA-{tag}","name":"回归工厂"},
        "staff-users":{"user_code":f"QA-{tag}","name":"回归采购员"},
        "material-categories":{"code_segment":tag[:8],"name":"回归分类"},
        "templates":{"name":f"回归模板{tag}","template_type":"order","content":"订单 {{order_no}}"},
        "data-connectors":{"name":f"回归连接器{tag}","connector_type":"erp"},
        "orders":{"supplier_id":"QA-SUP","supplier_name":"回归供应商","factory_code":"QA-F","lines":[line]},
        "quotations":{"supplier_id":"QA-SUP","supplier_name":"回归供应商","lines":[line]},
        "contracts":{"title":f"回归合同{tag}","supplier_id":"QA-SUP","supplier_name":"回归供应商","amount":100},
        "requisitions":{"title":f"回归申请{tag}","factory_code":"QA-F","lines":[line]},
        "rfqs":{"title":f"回归询价{tag}","lines":[line],"invitations":[{"supplier_id":demo_id("supplier-1"),"supplier_name":"【演示】华东精密"}]},
        "forecasts":{"name":f"回归预测{tag}","material_code":f"QA-{tag}","material_name":"回归物料","history":[{"period":f"2026-{m:02d}","quantity":m*10} for m in range(1,4)]},
        "sourcing-projects":{"name":f"回归寻源{tag}","category":"传动件"},
        "routing-plans":{"name":f"回归路径{tag}","material_code":f"QA-{tag}","supplies":[{"supplier":"S1","capacity":100}],"demands":[{"factory":"F1","quantity":50}],"lanes":[{"supplier":"S1","factory":"F1","unit_cost":3,"lead_days":1,"risk_score":0}]},
        "reports":{"title":f"回归报告{tag}","report_type":"overview"},
        "workflows":{"name":f"回归流程{tag}","business_type":"order","steps":[{"name":"审批","action":"approval"}]},
        "receipts":{"order_id":demo_id("draft-order-0"),"material_code":"DEMO-MAT-002","material_name":"【演示】传动轴","received_quantity":1},
        "reconciliations":{"order_id":demo_id("order-8-0"),"amount":50},
        "invoices":{"invoice_no":f"QA-INV-{tag}","reconciliation_id":demo_id("reconciliation-0"),"amount":50},
        "payments":{"invoice_id":demo_id("invoice"),"amount":50},
    }
    return simple[kind]


CASES=[
    ("suppliers",p.SupplierRecord,"name","修改供应商"),
    ("materials",p.MaterialRecord,"name","修改物料"),
    ("factories",p.FactoryRecord,"name","修改工厂"),
    ("staff-users",p.StaffUserRecord,"name","修改人员"),
    ("material-categories",p.MaterialCategoryRecord,"name","修改分类"),
    ("templates",p.BusinessTemplateRecord,"content","新订单 {{order_no}}"),
    ("data-connectors",p.DataConnectorRecord,"base_url","https://example.invalid"),
    ("orders",p.PurchaseOrderRecord,"payment_terms","验收后30天付款"),
    ("quotations",p.QuotationRecord,"delivery_days",25),
    ("contracts",p.ContractRecord,"title","修改合同"),
    ("requisitions",p.PurchaseRequisitionRecord,"title","修改采购申请"),
    ("rfqs",p.RFQRecord,"title","修改询价项目"),
    ("forecasts",p.DemandForecastRecord,"name","修改需求预测"),
    ("sourcing-projects",p.SourcingProjectRecord,"name","修改寻源项目"),
    ("routing-plans",p.RoutingPlanRecord,"name","修改路径方案"),
    ("reports",p.ProcurementReportRecord,"title","修改运营报告"),
    ("workflows",p.WorkflowDefinitionRecord,"status","active"),
    ("receipts",p.GoodsReceiptRecord,"remark","修改收货备注"),
    ("reconciliations",p.ReconciliationRecord,"remark","修改对账备注"),
    ("invoices",p.SupplierInvoiceRecord,"tax_amount",3),
    ("payments",p.PaymentRecord,"amount",45),
]


@pytest.mark.parametrize("kind,model,field,value",CASES,ids=[c[0] for c in CASES])
def test_database_crud_and_delete_middle_then_create(kind,model,field,value):
    created=[]
    for _ in range(3):
        response=client.post(f"/api/v1/{kind}",headers=HEADERS,json=payload_for(kind,uuid4().hex[:8]))
        assert response.status_code==201,response.text
        created.append(response.json()["id"])
    assert client.delete(f"/api/v1/{kind}/{created[1]}",headers=HEADERS).status_code==204
    response=client.post(f"/api/v1/{kind}",headers=HEADERS,json=payload_for(kind,uuid4().hex[:8]))
    assert response.status_code==201,response.text
    fourth=response.json()["id"]
    updated=client.patch(f"/api/v1/{kind}/{fourth}",headers=HEADERS,json={field:value})
    assert updated.status_code==200,updated.text
    with SessionLocal() as db:
        assert db.get(model,created[1]) is None
        record=db.get(model,fourth)
        assert record is not None
        assert getattr(record,field)==value
    page=client.get(f"/api/v1/{kind}?page=1&page_size=2",headers=HEADERS)
    assert page.status_code==200,page.text
    assert len(page.json()["items"])==2
    assert page.json()["total"]>=3
    for item_id in [created[0],created[2],fourth]:
        deleted=client.delete(f"/api/v1/{kind}/{item_id}",headers=HEADERS)
        assert deleted.status_code==204,deleted.text
        with SessionLocal() as db:
            assert db.get(model,item_id) is None
    assert client.patch(f"/api/v1/{kind}/{fourth}",headers=HEADERS,json={field:value}).status_code==404


@pytest.mark.parametrize("path",[
    f"orders/{demo_id('order-8-0')}",f"suppliers/{demo_id('supplier-1')}",
    f"materials/{demo_id('material-1')}",f"factories/{demo_id('factory-1')}",
    f"templates/{demo_id('template-order')}",f"material-categories/{demo_id('category-1')}",
])
def test_referenced_records_cannot_be_deleted(path):
    response=client.delete(f"/api/v1/{path}",headers=HEADERS)
    assert response.status_code==409,response.text


def test_demo_idempotency_and_all_list_endpoints():
    with SessionLocal.begin() as db:
        assert seed(db)=={}
    paths=[c[0] for c in CASES]+["supplier-category-links","buyer-authorizations","inspections","returns","workflow-runs","notification-outbox","audit-logs"]
    for path in paths:
        result=client.get(f"/api/v1/{path}?page=1&page_size=10",headers=HEADERS)
        assert result.status_code==200,(path,result.text)
        assert len(result.json()["items"])<=10
    response=client.get("/api/v1/material-costs/summary?material_code=DEMO-MAT-001")
    assert response.status_code==200
    assert response.json()["counts"]["receipts"]==18
    assert len(response.json()["suppliers"])==3

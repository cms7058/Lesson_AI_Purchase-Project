"""Idempotent, additive demo fixtures. Run: python -m app.seed_demo.

Only DEMO-prefixed identifiers are inserted. Existing rows are never overwritten.
All inserts are committed together; no email, webhook or external API is called.
"""
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine
from app.domain import persistence as p
from app.services.planning_service import _forecast_result, _optimize, _sourcing_result
from app.services.quotation_service import quotation_service

ACTOR = "DEMO-SEED-V1"


def demo_id(key):
    return str(uuid5(NAMESPACE_URL, f"pebs-demo-v1/{key}"))


def seed(db: Session):
    added = set()
    counts = {}

    def put(model, key, **values):
        record = db.get(model, demo_id(key))
        if record is not None:
            return record
        if hasattr(model, "created_by"):
            values.setdefault("created_by", ACTOR)
        record = model(id=demo_id(key), **values)
        db.add(record)
        db.flush()
        added.add(key)
        counts[model.__tablename__] = counts.get(model.__tablename__, 0) + 1
        return record

    root = put(p.MaterialCategoryRecord, "category-root", code="DEMO", name="演示制造物料", level=1, parent_id=None, path_name="演示制造物料")
    group = put(p.MaterialCategoryRecord, "category-group", code="DEMO-01", name="精密传动件", level=2, parent_id=root.id, path_name=f"{root.name} / 精密传动件")
    leaves = [put(p.MaterialCategoryRecord, f"category-{i}", code=f"DEMO-01-0{i}", name=name, level=3, parent_id=group.id, path_name=f"{group.path_name} / {name}") for i, name in [(1,"轴承"),(2,"传动轴")]]
    materials = [put(p.MaterialRecord, f"material-{i}", code=f"DEMO-MAT-00{i}", name=name, specification=spec, category=leaves[i-1].path_name, unit="件", standard_price=price, safety_stock=100, lead_time_days=15) for i,name,spec,price in [(1,"【演示】精密轴承","6205-2RS / 非真实采购",100),(2,"【演示】传动轴","D25×300 / 非真实采购",260)]]
    for i,material in enumerate(materials):
        put(p.MaterialCategoryAssignmentRecord,f"assignment-{i}",material_id=material.id,category_id=leaves[i].id)
    duplicate_material = put(p.MaterialRecord, "material-duplicate", code="DEMO-MAT-001A", name="【演示】精密轴承", specification="6205 2RS / 非真实采购", category=leaves[0].path_name, unit="件", standard_price=101, safety_stock=100, lead_time_days=15)
    put(p.MaterialCategoryAssignmentRecord, "assignment-duplicate", material_id=duplicate_material.id, category_id=leaves[0].id)
    materials.append(duplicate_material)
    suppliers = []
    for i,name,quality,delivery,service,risk in [(1,"【演示】华东精密",99,98,95,"low"),(2,"【演示】苏南制造",92,88,82,"medium"),(3,"【演示】沪上机电",97,94,89,"low")]:
        supplier = put(p.SupplierRecord,f"supplier-{i}",code=f"DEMO-SUP-00{i}",name=name,status="qualified",category="精密传动件",quality_pass_rate=quality,on_time_delivery_rate=delivery,service_score=service,risk_level=risk,contact=f"演示联系人{i}",email=f"supplier{i}@example.invalid",address="演示地址，不用于发货")
        suppliers.append(supplier)
        for j,leaf in enumerate(leaves):
            put(p.SupplierCategoryLinkRecord,f"supplier-category-{i}-{j}",supplier_id=supplier.id,category_id=leaf.id,qualification_status="qualified")
    for i,name,lat,lon in [(1,"【演示】苏州工厂",31.3,120.6),(2,"【演示】嘉兴工厂",30.7,120.7)]:
        put(p.FactoryRecord,f"factory-{i}",code=f"DEMO-F0{i}",name=name,address="演示园区",daily_receiving_capacity=1000,latitude=lat,longitude=lon)
    for i,role in [(1,"procurement_manager"),(2,"buyer"),(3,"buyer"),(4,"analyst")]:
        staff = put(p.StaffUserRecord,f"staff-{i}",user_code=f"DEMO-USER-{i}",name=f"【演示】采购人员{i}",role=role,department="演示采购部",email=f"buyer{i}@example.invalid",status="active")
        if role == "buyer":
            put(p.BuyerCategoryAuthorizationRecord,f"authorization-{i}",buyer_id=staff.id,category_id=leaves[i-2].id,valid_from=date(2026,1,1),valid_to=date(2027,12,31))
    templates = {}
    for kind in ["order","quotation","contract"]:
        number_key={"order":"order_no","quotation":"quotation_no","contract":"contract_no"}[kind]
        detail="金额：{{amount}} {{currency}}" if kind=="contract" else "物料：{{material_name}}\n数量：{{quantity}} {{unit}}"
        content="【演示文件，不具备交易效力】\n单据：{{"+number_key+"}}\n供应商：{{supplier_name}}\n"+detail
        templates[kind] = put(p.BusinessTemplateRecord,f"template-{kind}",name=f"【演示】{kind}标准模板",template_type=kind,version="1.0",content=content,status="active")
    contracts = [put(p.ContractRecord,f"contract-{i}",contract_no=f"DEMO-CT-{i:03d}",title=f"【演示】{supplier.name}年度采购协议",supplier_id=supplier.id,supplier_name=supplier.name,amount=200000,currency="CNY",status="draft",effective_date=date(2026,1,1),expiry_date=date(2027,12,31)) for i,supplier in enumerate(suppliers,1)]
    for contract in contracts:
        put(p.DocumentTemplateLinkRecord,f"contract-link-{contract.id}",document_type="contract",document_id=contract.id,template_id=templates["contract"].id)
    quotes = []
    for m,material in enumerate(materials):
        for j,supplier in enumerate(suppliers):
            key = f"quote-{m}-{j}"
            quote = put(p.QuotationRecord,key,quotation_no=f"DEMO-Q-{m+1}{j+1}",supplier_id=supplier.id,supplier_name=supplier.name,currency="CNY",delivery_days=[10,18,14][j],service_score=supplier.service_score,quality_pass_rate=supplier.quality_pass_rate,source_type="manual")
            if key in added:
                quote.lines.append(p.QuotationLineRecord(material_code=material.code,material_name=material.name,quantity=100,unit="件",unit_price=[105,92,99][j]+m*160,tax_rate=Decimal("0.13"),logistics_cost=100+j*100,expected_quality_loss=[50,900,250][j]))
            quotes.append(quote)
            put(p.DocumentTemplateLinkRecord,f"quote-link-{m}-{j}",document_type="quotation",document_id=quote.id,template_id=templates["quotation"].id)
    orders=[]
    for month in range(3,9):
        for j,supplier in enumerate(suppliers):
            key=f"order-{month}-{j}"
            material=materials[0]
            price=Decimal([103,89,97][j]+month-3)
            quantity=Decimal(100+(month-3)*20)
            rejected=Decimal([1,8,3][j])
            created=datetime(2026,month,1,tzinfo=UTC)
            order=put(p.PurchaseOrderRecord,key,order_no=f"DEMO-PO-{month:02d}{j+1}",supplier_id=supplier.id,supplier_name=supplier.name,factory_code=f"DEMO-F0{j%2+1}",status="completed",template_id=templates["order"].id,created_at=created)
            if key in added:
                order.lines.append(p.PurchaseOrderLineRecord(material_code=material.code,material_name=material.name,quantity=quantity,unit="件",unit_price=price,tax_rate=Decimal("0.13"),delivery_date=date(2026,month,15)))
            orders.append(order)
            receipt=put(p.GoodsReceiptRecord,f"receipt-{month}-{j}",receipt_no=f"DEMO-GR-{month:02d}{j+1}",order_id=order.id,order_no=order.order_no,supplier_name=supplier.name,factory_code=order.factory_code,material_code=material.code,material_name=material.name,received_quantity=quantity,accepted_quantity=quantity-rejected,rejected_quantity=rejected,received_date=date(2026,month,15+[0,5,2][j]),status="inspected",remark="【演示】虚构收货与质检记录",created_at=created)
            put(p.QualityInspectionRecord,f"inspection-{month}-{j}",inspection_no=f"DEMO-QI-{month:02d}{j+1}",receipt_id=receipt.id,receipt_no=receipt.receipt_no,inspected_quantity=quantity,accepted_quantity=quantity-rejected,rejected_quantity=rejected,rework_quantity=rejected,result="partial",defect_description="【演示】尺寸偏差",inspected_by=ACTOR,inspected_at=datetime(2026,month,21,tzinfo=UTC))
            put(p.CostAdjustmentRecord,f"cost-{month}-{j}",receipt_id=receipt.id,logistics=100+j*80,rework=rejected*30,delay=[0,1000,200][j],other=0,credit=rejected*price/2,basis="estimated",evidence="【演示】虚构估算费用，用于对比供应商，不是财务凭证")
            if month==8:
                put(p.PurchaseReturnRecord,f"return-{j}",return_no=f"DEMO-RT-{j+1}",receipt_id=receipt.id,receipt_no=receipt.receipt_no,supplier_name=supplier.name,material_code=material.code,quantity=rejected,reason="【演示】不合格品退回",status="draft")
                reconciliation=put(p.ReconciliationRecord,f"reconciliation-{j}",reconciliation_no=f"DEMO-RC-{j+1}",order_id=order.id,order_no=order.order_no,supplier_name=supplier.name,amount=quantity*price*Decimal("1.13"),status="confirmed" if j==0 else "draft",remark="【演示】仅用于界面查看")
                if j==0:
                    invoice=put(p.SupplierInvoiceRecord,"invoice",invoice_no="DEMO-INV-001",reconciliation_id=reconciliation.id,supplier_name=supplier.name,amount=reconciliation.amount,tax_amount=quantity*price*Decimal("0.13"),invoice_date=date(2026,8,25),status="verified")
                    put(p.PaymentRecord,"payment",payment_no="DEMO-PAY-001",invoice_id=invoice.id,invoice_no=invoice.invoice_no,supplier_name=supplier.name,amount=invoice.amount/2,planned_date=date(2026,9,20),status="planned")
    for j,supplier in enumerate(suppliers):
        key=f"draft-order-{j}"
        order=put(p.PurchaseOrderRecord,key,order_no=f"DEMO-PO-D0{j+1}",supplier_id=supplier.id,supplier_name=supplier.name,factory_code="DEMO-F01",template_id=templates["order"].id,status="draft")
        if key in added:
            order.lines.append(p.PurchaseOrderLineRecord(material_code=materials[1].code,material_name=materials[1].name,quantity=50,unit="件",unit_price=260+j*10,tax_rate=Decimal("0.13")))
    request=put(p.PurchaseRequisitionRecord,"requisition",request_no="DEMO-PR-001",title="【演示】九月生产备料申请",factory_code="DEMO-F01",department="演示装配车间",reason="【演示】非真实采购申请",needed_date=date(2026,10,1))
    if "requisition" in added:
        request.lines.append(p.PurchaseRequisitionLineRecord(material_code=materials[0].code,material_name=materials[0].name,quantity=500,unit="件",estimated_unit_price=100))
    rfq=put(p.RFQRecord,"rfq",rfq_no="DEMO-XJ-001",title="【演示】轴承季度询价",deadline=date(2026,10,1),requisition_id=request.id)
    if "rfq" in added:
        rfq.lines.append(p.RFQLineRecord(material_code=materials[0].code,material_name=materials[0].name,quantity=500,unit="件"))
        for supplier in suppliers:
            rfq.invitations.append(p.RFQInvitationRecord(supplier_id=supplier.id,supplier_name=supplier.name))
    forecast_data={"history":[{"period":f"2026-{m:02d}","quantity":q} for m,q in enumerate([280,300,330,370,410,450,470,510],1)],"horizon":3,"safety_stock":100,"on_hand":200,"in_transit":150}
    put(p.DemandForecastRecord,"forecast",name="【演示】轴承季度需求预测",material_code=materials[0].code,material_name=materials[0].name,input_json=json.dumps(forecast_data),result_json=json.dumps(_forecast_result(forecast_data)),status="ready")
    candidates=[{"supplier_name":s.name,"country":"中国","source_url":"","capabilities":"【演示】精密加工与批次追溯","price_score":v,"quality_score":float(s.quality_pass_rate),"delivery_score":float(s.on_time_delivery_rate),"risk_level":s.risk_level} for s,v in zip(suppliers,[85,98,91],strict=True)]
    put(p.SourcingProjectRecord,"sourcing",name="【演示】传动轴供应商寻源",category="传动件",requirements="【演示】按加工能力和交付质量评估，无外部真实背书",candidates_json=json.dumps(candidates,ensure_ascii=False),result_json=json.dumps(_sourcing_result(candidates),ensure_ascii=False),status="evaluated")
    routing={"supplies":[{"supplier":s.name,"capacity":300} for s in suppliers],"demands":[{"factory":"【演示】苏州工厂","quantity":350},{"factory":"【演示】嘉兴工厂","quantity":250}],"lanes":[{"supplier":s.name,"factory":f,"unit_cost":cost+j,"lead_days":j+1,"risk_score":j*5} for j,s in enumerate(suppliers) for f,cost in [("【演示】苏州工厂",3),("【演示】嘉兴工厂",5)]],"lead_weight":0.5,"risk_weight":0.1}
    put(p.RoutingPlanRecord,"routing",name="【演示】双工厂供货分配",material_code=materials[0].code,supplies_json=json.dumps(routing["supplies"],ensure_ascii=False),demands_json=json.dumps(routing["demands"],ensure_ascii=False),lanes_json=json.dumps({k:routing[k] for k in ["lanes","lead_weight","risk_weight"]},ensure_ascii=False),result_json=json.dumps(_optimize(routing),ensure_ascii=False),status="optimized")
    put(p.ProcurementReportRecord,"report",title="【演示】采购运营月报",report_type="overview",notes="【演示】点击生成，可汇总当前数据库的采购指标",content_json="{}",status="draft")
    put(p.WorkflowDefinitionRecord,"workflow",name="【演示】订单经理审批",business_type="order",trigger_type="manual",steps_json=json.dumps([{"name":"采购经理审批","action":"approval"}],ensure_ascii=False),status="draft")
    put(p.DataConnectorRecord,"connector",name="【演示】ERP接口配置（未连接）",connector_type="erp",base_url="https://erp.example.invalid",sync_mode="manual",status="draft")
    db.flush()
    for material in materials:
        result=quotation_service.compare(db,material.code,Decimal(100),"CNY")
        put(p.ComparisonSnapshotRecord,f"comparison-{material.code}",material_code=material.code,currency="CNY",quantity=100,result_json=result.model_dump_json())
    if counts:
        db.add(p.AuditLogRecord(actor_id=ACTOR,actor_role="admin",action="seed_demo",resource_type="demo_dataset",resource_id="V1",detail="【演示】仅新增虚构样例数据；不覆盖现有记录；无外部发送。"))
    db.flush()
    return counts


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        counts=seed(session)
    print(json.dumps({"inserted":counts,"material_codes":["DEMO-MAT-001","DEMO-MAT-002"],"note":"演示数据；重复执行不会覆盖现有记录"},ensure_ascii=False,indent=2))

"""Typed AND filters shared by list APIs, applied before count and pagination.

Only explicitly registered public fields can be searched. The listener lives for
one GET request and never applies to relationship loads or write operations.
"""
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, and_, event
from sqlalchemy.orm import Session, with_loader_criteria

from app.core.config import get_settings
from app.core.database import get_db
from app.domain import persistence as p
from app.domain.supplier_execution import SupplierDelivery
from app.domain.supplier_portal import SupplierAccount
from app.domain.supply_feedback import SupplyFeedback

# Field names are allowlisted, not supplied SQL identifiers.
SPECS = {
    "supplier/orders": (p.PurchaseOrderRecord, "我的采购订单", "order_no status created_at"),
    "supplier/invoices": (p.SupplierInvoiceRecord, "我的发票", "invoice_no amount tax_amount invoice_date status"),
    "supplier/deliveries": (SupplierDelivery, "交付记录", "carrier tracking_no shipped_date expected_date"),
    "supplier-deliveries": (SupplierDelivery, "供应商交付", "carrier tracking_no shipped_date expected_date"),
    "supplier/rfqs": (p.RFQRecord, "我的询价", "rfq_no title deadline currency status created_at"),
    "supplier-accounts": (SupplierAccount, "供应商账号", "username supplier_id active"),
    "supply-feedback/records": (SupplyFeedback, "供货反馈记录", "supplier_code material_code external_id record_date source_system is_demo created_at"),
    "orders": (p.PurchaseOrderRecord, "采购订单", "order_no supplier_id supplier_name factory_code currency status created_at"),
    "rfqs": (p.RFQRecord, "询价项目", "rfq_no title deadline currency status created_at"),
    "suppliers": (p.SupplierRecord, "供应商", "code name category contact email phone address unified_credit_code risk_level status created_at"),
    "materials": (p.MaterialRecord, "物料", "code name specification category unit standard_price safety_stock lead_time_days active created_at"),
    "factories": (p.FactoryRecord, "工厂", "code name address contact phone latitude longitude daily_receiving_capacity active created_at"),
    "requisitions": (p.PurchaseRequisitionRecord, "采购申请", "request_no title created_by department factory_code priority needed_date cost_center status created_at"),
    "contracts": (p.ContractRecord, "合同", "contract_no title supplier_id supplier_name amount currency effective_date expiry_date status created_at"),
    "quotations": (p.QuotationRecord, "报价", "quotation_no supplier_id supplier_name currency status created_at"),
    "receipts": (p.GoodsReceiptRecord, "收货", "receipt_no order_no supplier_name factory_code material_code material_name received_quantity accepted_quantity rejected_quantity received_date status created_at"),
    "inspections": (p.QualityInspectionRecord, "质检", "inspection_no receipt_no inspected_quantity accepted_quantity rejected_quantity rework_quantity result inspected_by inspected_at"),
    "returns": (p.PurchaseReturnRecord, "退货", "return_no receipt_no supplier_name material_code quantity reason status created_at"),
    "reconciliations": (p.ReconciliationRecord, "对账", "reconciliation_no order_no supplier_name amount adjustment_amount status created_at"),
    "invoices": (p.SupplierInvoiceRecord, "发票", "invoice_no supplier_name amount tax_amount invoice_date status created_at"),
    "payments": (p.PaymentRecord, "付款", "payment_no invoice_no supplier_name amount planned_date paid_date status created_at"),
    "templates": (p.BusinessTemplateRecord, "模板", "name template_type version status created_at"),
    "data-connectors": (p.DataConnectorRecord, "数据接入", "name connector_type sync_mode status created_at"),
    "forecasts": (p.DemandForecastRecord, "需求预测", "name material_code material_name status created_at"),
    "sourcing-projects": (p.SourcingProjectRecord, "寻源项目", "name category status created_at"),
    "routing-plans": (p.RoutingPlanRecord, "路径规划", "name material_code status created_at"),
    "reports": (p.ProcurementReportRecord, "报告", "title report_type status created_at"),
    "audit-logs": (p.AuditLogRecord, "审计日志", "actor_id actor_role action resource_type resource_id detail created_at"),
    "material-categories": (p.MaterialCategoryRecord, "物料分类", "code name level parent_id path_name active created_at"),
    "staff-users": (p.StaffUserRecord, "人员", "user_code name email department title role status created_at"),
    "buyer-authorizations": (p.BuyerCategoryAuthorizationRecord, "采购授权", "buyer_id category_id valid_from valid_to status created_at"),
    "supplier-category-links": (p.SupplierCategoryLinkRecord, "供应商物料分类", "supplier_id category_id qualification_status created_at"),
    "workflows": (p.WorkflowDefinitionRecord, "工作流", "name trigger_type status created_at"),
    "workflow-runs": (p.WorkflowRunRecord, "工作流执行", "workflow_id workflow_name business_id started_by status started_at finished_at"),
    "notification-outbox": (p.NotificationOutboxRecord, "通知", "recipient subject status created_at"),
}
LABELS = dict(part.split(":", 1) for part in ["order_no:订单号", "rfq_no:询价编号", "title:标题", "supplier_id:供应商编码/ID", "supplier_name:供应商", "factory_code:工厂编码", "currency:币种", "status:状态", "created_at:创建时间", "code:编码", "name:名称", "category:分类", "contact_name:联系人", "email:邮箱", "phone:电话", "specification:规格", "unit:单位", "address:地址", "requisition_no:申请编号", "requester:申请人", "department:部门", "contract_no:合同编号", "quotation_no:报价编号", "receipt_no:收货单号", "material_code:物料编码", "material_name:物料名称", "received_quantity:收货数量", "accepted_quantity:合格数量", "rejected_quantity:不合格数量", "received_date:收货日期", "inspection_no:质检单号", "inspected_quantity:检验数量", "rework_quantity:返修数量", "result:质检结果", "inspected_by:检验人", "inspected_at:检验时间", "return_no:退货单号", "quantity:数量", "reason:原因", "reconciliation_no:对账单号", "amount:金额", "adjustment_amount:调整金额", "invoice_no:发票号", "tax_amount:税额", "invoice_date:开票日期", "payment_no:付款单号", "planned_date:计划付款日期", "paid_date:实付日期", "template_type:模板类型", "version:版本", "connector_type:接入类型", "sync_mode:同步方式", "report_type:报告类型", "actor_id:操作人", "actor_role:角色", "action:操作", "resource_type:资源类型", "resource_id:资源ID", "detail:说明", "level:分类级别", "parent_id:上级ID", "path_name:分类路径", "active:启用", "user_code:人员编码", "role:角色", "buyer_id:采购员ID", "category_id:物料分类ID", "valid_from:生效日期", "valid_to:失效日期", "qualification_status:资格状态", "trigger_type:触发类型", "workflow_id:工作流ID", "recipient:接收人", "subject:主题", "deadline:报价截止日期"])
STATUS_LABELS = dict(part.split(":", 1) for part in ["draft:草稿", "pending_approval:待审批", "approved:已审批", "sent:已发送", "supplier_confirmed:待送货", "partially_delivered:部分送货", "completed:完成", "cancelled:已取消", "published:已发布", "awarded:已定标", "closed:已关闭", "active:启用", "inactive:停用", "qualified:合格", "pending:待处理", "rejected:驳回", "ready:就绪", "received:已收货", "inspected:已质检", "confirmed:已确认", "planned:计划中", "paid:已付款", "failed:失败", "success:成功"])
RELATIONS = {
    "supplier/orders": {"material_code": (p.PurchaseOrderRecord.lines, p.PurchaseOrderLineRecord.material_code)},
    "supplier/rfqs": {"material_code": (p.RFQRecord.lines, p.RFQLineRecord.material_code)},
    "orders": {name: (p.PurchaseOrderRecord.lines, getattr(p.PurchaseOrderLineRecord, name)) for name in ["material_code", "material_name", "quantity", "unit_price", "delivery_date"]},
    "rfqs": {"material_code": (p.RFQRecord.lines, p.RFQLineRecord.material_code), "supplier_name": (p.RFQRecord.invitations, p.RFQInvitationRecord.supplier_name), "supplier_id": (p.RFQRecord.invitations, p.RFQInvitationRecord.supplier_id)},
    "requisitions": {"material_code": (p.PurchaseRequisitionRecord.lines, p.PurchaseRequisitionLineRecord.material_code)},
    "quotations": {"material_code": (p.QuotationRecord.lines, p.QuotationLineRecord.material_code)},
}

LABELS.update(dict(part.split(":", 1) for part in ["request_no:申请编号", "created_by:创建人", "contact:联系人", "unified_credit_code:信用代码", "risk_level:风险等级", "standard_price:标准单价", "safety_stock:安全库存", "lead_time_days:交货周期(天)", "latitude:纬度", "longitude:经度", "daily_receiving_capacity:日收货能力", "priority:优先级", "needed_date:需求日期", "cost_center:成本中心", "effective_date:生效日期", "expiry_date:到期日期", "workflow_name:工作流名称", "business_id:业务单号", "started_by:发起人", "started_at:开始时间", "finished_at:完成时间", "total_amount:订单含税金额"]))
STATUS_LABELS.update(quality_tracking="质量追溯", candidate="候选", blacklisted="黑名单", disabled="停用", awaiting_approval="等待审批", running="运行中", converted="已转单", rejected="已驳回", submitted="已提交", verified="已验真", expired="已过期", terminated="已终止")
LABELS.update(username="登录名", supplier_code="供应商编码", external_id="外部批次编号", record_date="记录日期", source_system="来源系统", is_demo="模拟数据", unit_price="物料单价", delivery_date="交货日期")
LABELS.update(carrier="承运商", tracking_no="运单号", shipped_date="发货日期", expected_date="预计到货日期")


def fields_for(resource):
    model, _, names = SPECS[resource]
    return {name: getattr(model, name) for name in names.split() if name in model.__table__.columns} | {name: column for name, (_, column) in RELATIONS.get(resource, {}).items()}


def field_type(column):
    t = column.type
    if isinstance(t, Boolean):
        return "boolean"
    if isinstance(t, DateTime):
        return "datetime"
    if isinstance(t, Date):
        return "date"
    if isinstance(t, (Integer, Numeric)):
        return "number"
    return "text"


def parse_value(value, kind):
    if value is None or isinstance(value, (list, dict)):
        raise ValueError("缺少条件值")
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError("布尔条件必须为 true/false")
        return value
    if kind == "number":
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("数值必须有限")
        return result
    if kind == "date":
        return date.fromisoformat(str(value))
    if kind == "datetime":
        return datetime.fromisoformat(str(value))
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("文本条件最长300字")
    return value


def criteria_for(resource, raw):
    try:
        if len(raw) > 10000:
            raise ValueError("查询条件过长")
        conditions = json.loads(raw)
        if not isinstance(conditions, list) or len(conditions) > 12:
            raise ValueError("最多12个组合条件")
        fields = fields_for(resource)
        expressions = []
        related = {}
        for item in conditions:
            if not isinstance(item, dict) or set(item) != {"field", "op", "value"} or item["field"] not in fields:
                raise ValueError("不支持的查询字段")
            column = fields[item["field"]]
            kind, op = field_type(column), item["op"]
            allowed = {"eq", "ne"} | ({"contains"} if kind == "text" else {"gte", "lte"} if kind != "boolean" else set())
            if op not in allowed:
                raise ValueError("字段类型不支持该运算符")
            value = parse_value(item["value"], kind)
            expression = column.contains(value, autoescape=True) if op == "contains" else {"eq": column.__eq__, "ne": column.__ne__, "gte": column.__ge__, "lte": column.__le__}[op](value)
            relation = RELATIONS.get(resource, {}).get(item["field"])
            if relation:
                key = relation[0].key
                related.setdefault(key, (relation[0], []))[1].append(expression)
            else:
                expressions.append(expression)
        expressions.extend(relation.any(and_(*clauses)) for relation, clauses in related.values())
        return and_(*expressions) if expressions else None
    except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
        raise HTTPException(422, f"组合查询条件错误：{exc}") from exc


def list_filter_scope(request: Request, db: Session = Depends(get_db)):
    raw = request.query_params.get("filters")
    if not raw:
        yield
        return
    resource = request.url.path.removeprefix(get_settings().api_prefix + "/")
    if request.method != "GET" or resource not in SPECS:
        raise HTTPException(422, "该接口不支持组合查询")
    criteria = criteria_for(resource, raw)
    model = SPECS[resource][0]

    def apply_filter(state):
        if criteria is not None and state.is_select and not state.is_relationship_load and not state.is_column_load:
            state.statement = state.statement.options(with_loader_criteria(model, criteria, include_aliases=True, propagate_to_loaders=False))

    event.listen(db, "do_orm_execute", apply_filter)
    try:
        yield
    finally:
        event.remove(db, "do_orm_execute", apply_filter)


router = APIRouter()


@router.get("/list-filter-schema")
def filter_schema():
    return [{"resource": key, "label": label, "fields": [{"name": name, "label": LABELS.get(name, name), "type": field_type(column), "options": [{"value": k, "label": v} for k, v in STATUS_LABELS.items()] if name == "status" else []} for name, column in fields_for(key).items()]} for key, (_, label, _) in SPECS.items()]

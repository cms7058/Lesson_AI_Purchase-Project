import json
from datetime import UTC, datetime
from math import isclose

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.persistence import (
    ContractRecord,
    DemandForecastRecord,
    GoodsReceiptRecord,
    ProcurementReportRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    QualityInspectionRecord,
    RoutingPlanRecord,
    SourcingProjectRecord,
    SupplierRecord,
)
from app.domain.planning import (
    Forecast,
    ForecastCreate,
    ForecastUpdate,
    ProcurementReport,
    RoutingCreate,
    RoutingPlan,
    RoutingUpdate,
    SourcingCreate,
    SourcingProject,
    SourcingUpdate,
)


def _forecast_result(data: dict) -> dict:
    values = [float(item["quantity"]) for item in data["history"]]
    count = len(values)
    x_mean = (count - 1) / 2
    y_mean = sum(values) / count
    denominator = sum((index - x_mean) ** 2 for index in range(count))
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator if denominator else 0
    intercept = y_mean - slope * x_mean
    fitted = [max(0, intercept + slope * index) for index in range(count)]
    predicted = [round(max(0, intercept + slope * (count + index)), 2) for index in range(data["horizon"])]
    mae = sum(abs(actual - estimate) for actual, estimate in zip(values, fitted, strict=True)) / count
    total = sum(predicted)
    purchase = max(0, total + data["safety_stock"] - data["on_hand"] - data["in_transit"])
    return {"method": "linear_trend", "equation": f"y = {intercept:.4f} + {slope:.4f}x", "predicted": predicted, "forecast_total": round(total, 2), "recommended_purchase": round(purchase, 2), "mae": round(mae, 2), "trend": "up" if slope > 0.01 else "down" if slope < -0.01 else "stable"}


def _forecast(record: DemandForecastRecord) -> Forecast:
    data = json.loads(record.input_json)
    return Forecast(id=record.id, name=record.name, material_code=record.material_code, material_name=record.material_name, **data, result=json.loads(record.result_json), status=record.status, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at)


def _sourcing_result(candidates: list[dict]) -> dict:
    risk_penalty = {"low": 0, "medium": 8, "high": 20}
    ranked = []
    for item in candidates:
        score = item["price_score"] * 0.3 + item["quality_score"] * 0.35 + item["delivery_score"] * 0.25 + 10 - risk_penalty[item["risk_level"]]
        ranked.append({**item, "score": round(max(0, min(100, score)), 2)})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"ranking": ranked, "recommended_supplier": ranked[0]["supplier_name"] if ranked else "", "evaluated_at": datetime.now(UTC).isoformat()}


def _sourcing(record: SourcingProjectRecord) -> SourcingProject:
    return SourcingProject(id=record.id, name=record.name, category=record.category, requirements=record.requirements, candidates=json.loads(record.candidates_json), result=json.loads(record.result_json), status=record.status, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at)


def _routing(record: RoutingPlanRecord) -> RoutingPlan:
    settings = json.loads(record.lanes_json)
    return RoutingPlan(id=record.id, name=record.name, material_code=record.material_code, supplies=json.loads(record.supplies_json), demands=json.loads(record.demands_json), lanes=settings["lanes"], lead_weight=settings["lead_weight"], risk_weight=settings["risk_weight"], result=json.loads(record.result_json), status=record.status, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at)


def _optimize(data: dict) -> dict:
    supplies = {item["supplier"]: float(item["capacity"]) for item in data["supplies"]}
    demands = {item["factory"]: float(item["quantity"]) for item in data["demands"]}
    required = sum(demands.values())
    if sum(supplies.values()) + 1e-8 < required:
        return {"feasible": False, "message": "供应总能力不足", "required": required, "available": sum(supplies.values()), "allocations": []}
    supplier_names = list(supplies)
    factory_names = list(demands)
    source, supplier_start, factory_start = 0, 1, 1 + len(supplier_names)
    sink = factory_start + len(factory_names)
    graph: list[list[list[float | int]]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, end: int, capacity: float, cost: float) -> list[float | int]:
        forward: list[float | int] = [end, len(graph[end]), capacity, cost]
        backward: list[float | int] = [start, len(graph[start]), 0.0, -cost]
        graph[start].append(forward); graph[end].append(backward)
        return forward

    for index, name in enumerate(supplier_names):add_edge(source, supplier_start + index, supplies[name], 0)
    for index, name in enumerate(factory_names):add_edge(factory_start + index, sink, demands[name], 0)
    lane_edges = []
    for lane in data["lanes"]:
        capacity = float(lane.get("max_quantity") or min(supplies[lane["supplier"]], demands[lane["factory"]]))
        effective = float(lane["unit_cost"]) + float(lane["lead_days"]) * data["lead_weight"] + float(lane["risk_score"]) * data["risk_weight"]
        edge = add_edge(supplier_start + supplier_names.index(lane["supplier"]), factory_start + factory_names.index(lane["factory"]), capacity, effective)
        lane_edges.append((lane, edge, capacity, effective))
    flow = total_cost = 0.0
    while flow + 1e-8 < required:
        distance = [float("inf")] * len(graph); parent: list[tuple[int, int] | None] = [None] * len(graph); distance[source] = 0
        for _ in range(len(graph) - 1):
            changed = False
            for node, edges in enumerate(graph):
                if distance[node] == float("inf"):continue
                for edge_index, edge in enumerate(edges):
                    if float(edge[2]) > 1e-8 and distance[int(edge[0])] > distance[node] + float(edge[3]) + 1e-10:
                        distance[int(edge[0])] = distance[node] + float(edge[3]); parent[int(edge[0])] = (node, edge_index); changed = True
            if not changed:break
        if parent[sink] is None:break
        amount = required - flow; node = sink
        while node != source:
            previous, edge_index = parent[node] or (source, 0); amount = min(amount, float(graph[previous][edge_index][2])); node = previous
        node = sink
        while node != source:
            previous, edge_index = parent[node] or (source, 0); edge = graph[previous][edge_index]; edge[2] = float(edge[2]) - amount; reverse = graph[node][int(edge[1])]; reverse[2] = float(reverse[2]) + amount; node = previous
        flow += amount; total_cost += amount * distance[sink]
    allocations = []
    raw_transport_cost = 0.0
    for lane, edge, original_capacity, effective in lane_edges:
        quantity = original_capacity - float(edge[2])
        if quantity > 1e-8:
            raw_transport_cost += quantity * float(lane["unit_cost"])
            allocations.append({"supplier": lane["supplier"], "factory": lane["factory"], "quantity": round(quantity, 4), "unit_cost": lane["unit_cost"], "lead_days": lane["lead_days"], "risk_score": lane["risk_score"], "effective_unit_cost": round(effective, 4), "cost": round(quantity * float(lane["unit_cost"]), 2)})
    feasible = isclose(flow, required, abs_tol=1e-6)
    return {"feasible": feasible, "message": "已生成最优分配" if feasible else "现有线路容量无法满足全部工厂需求", "required": round(required, 4), "allocated": round(flow, 4), "total_transport_cost": round(raw_transport_cost, 2), "weighted_objective": round(total_cost, 2), "allocations": allocations, "optimized_at": datetime.now(UTC).isoformat()}


def _report(record: ProcurementReportRecord) -> ProcurementReport:
    return ProcurementReport(id=record.id, title=record.title, report_type=record.report_type, notes=record.notes, content=json.loads(record.content_json), status=record.status, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at)


class PlanningService:
    def list_records(self, db: Session, model, page: int, page_size: int, keyword: str, status: str):
        query = select(model)
        name_field = model.title if model is ProcurementReportRecord else model.name
        if keyword:query = query.where(name_field.ilike(f"%{keyword}%"))
        if status:query = query.where(model.status == status)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        return list(db.scalars(query.order_by(model.created_at.desc()).offset((page - 1) * page_size).limit(page_size))), total

    def create_forecast(self, db: Session, payload: ForecastCreate, user: str) -> Forecast:
        data = payload.model_dump(mode="json", exclude={"name", "material_code", "material_name"})
        item = DemandForecastRecord(name=payload.name, material_code=payload.material_code, material_name=payload.material_name, input_json=json.dumps(data, ensure_ascii=False), result_json=json.dumps(_forecast_result(data), ensure_ascii=False), created_by=user)
        db.add(item);db.flush();db.refresh(item);return _forecast(item)

    def update_forecast(self, db: Session, item: DemandForecastRecord, payload: ForecastUpdate) -> Forecast:
        data = json.loads(item.input_json); changes = payload.model_dump(exclude_none=True, mode="json")
        for key in ("name", "material_name"):
            if key in changes:setattr(item, key, changes.pop(key))
        data.update(changes);item.input_json=json.dumps(data,ensure_ascii=False);item.result_json=json.dumps(_forecast_result(data),ensure_ascii=False);db.flush();db.refresh(item);return _forecast(item)

    def create_sourcing(self, db: Session, payload: SourcingCreate, user: str) -> SourcingProject:
        item=SourcingProjectRecord(name=payload.name,category=payload.category,requirements=payload.requirements,candidates_json=json.dumps([c.model_dump(mode="json") for c in payload.candidates],ensure_ascii=False),created_by=user);db.add(item);db.flush();db.refresh(item);return _sourcing(item)

    def update_sourcing(self, db: Session, item: SourcingProjectRecord, payload: SourcingUpdate) -> SourcingProject:
        values=payload.model_dump(exclude_none=True,mode="json")
        candidates=values.pop("candidates",None)
        for key,value in values.items():setattr(item,key,value)
        if candidates is not None:item.candidates_json=json.dumps(candidates,ensure_ascii=False)
        item.status="draft";item.result_json="{}";db.flush();db.refresh(item);return _sourcing(item)

    def create_routing(self, db: Session, payload: RoutingCreate, user: str) -> RoutingPlan:
        data=payload.model_dump(mode="json");settings={"lanes":data["lanes"],"lead_weight":data["lead_weight"],"risk_weight":data["risk_weight"]};item=RoutingPlanRecord(name=payload.name,material_code=payload.material_code,supplies_json=json.dumps(data["supplies"],ensure_ascii=False),demands_json=json.dumps(data["demands"],ensure_ascii=False),lanes_json=json.dumps(settings,ensure_ascii=False),created_by=user);db.add(item);db.flush();db.refresh(item);return _routing(item)

    def update_routing(self,db:Session,item:RoutingPlanRecord,payload:RoutingUpdate)->RoutingPlan:
        current=_routing(item).model_dump(mode="json",exclude={"id","result","status","created_by","created_at","updated_at","material_code"});current.update(payload.model_dump(exclude_none=True,mode="json"));validated=RoutingCreate(material_code=item.material_code,**current).model_dump(mode="json");item.name=validated["name"];item.supplies_json=json.dumps(validated["supplies"],ensure_ascii=False);item.demands_json=json.dumps(validated["demands"],ensure_ascii=False);item.lanes_json=json.dumps({"lanes":validated["lanes"],"lead_weight":validated["lead_weight"],"risk_weight":validated["risk_weight"]},ensure_ascii=False);item.status="draft";item.result_json="{}";db.flush();db.refresh(item);return _routing(item)

    def generate_report(self,db:Session,item:ProcurementReportRecord)->ProcurementReport:
        order_count=db.scalar(select(func.count()).select_from(PurchaseOrderRecord)) or 0
        purchase_amount=float(db.scalar(select(func.coalesce(func.sum(PurchaseOrderLineRecord.quantity*PurchaseOrderLineRecord.unit_price),0))) or 0)
        supplier_count=db.scalar(select(func.count()).select_from(SupplierRecord)) or 0
        active_contracts=db.scalar(select(func.count()).select_from(ContractRecord).where(ContractRecord.status=="active")) or 0
        receipts=db.scalar(select(func.coalesce(func.sum(GoodsReceiptRecord.received_quantity),0))) or 0
        accepted=db.scalar(select(func.coalesce(func.sum(QualityInspectionRecord.accepted_quantity),0))) or 0
        inspected=db.scalar(select(func.coalesce(func.sum(QualityInspectionRecord.inspected_quantity),0))) or 0
        content={"summary":{"orders":order_count,"purchase_amount":round(purchase_amount,2),"suppliers":supplier_count,"active_contracts":active_contracts,"received_quantity":float(receipts),"quality_pass_rate":round(float(accepted)/float(inspected)*100,2) if inspected else 0},"insights":[f"系统当前共管理 {order_count} 张采购订单，采购明细金额 {purchase_amount:.2f} 元。",f"共维护 {supplier_count} 家供应商，有效合同 {active_contracts} 份。",f"累计收货 {float(receipts):.2f}，已检物料质量合格率为 {round(float(accepted)/float(inspected)*100,2) if inspected else 0:.2f}%。"],"generated_at":datetime.now(UTC).isoformat(),"metric_version":1}
        item.content_json=json.dumps(content,ensure_ascii=False);item.status="generated";db.flush();db.refresh(item);return _report(item)


planning_service=PlanningService()

__all__=["_forecast", "_optimize", "_report", "_routing", "_sourcing", "_sourcing_result", "planning_service"]

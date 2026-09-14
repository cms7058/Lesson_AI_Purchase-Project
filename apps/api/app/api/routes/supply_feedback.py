import csv
import hashlib
import hmac
import io
import json
import secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.routes.supplier_portal import editor, manager
from app.core.database import get_db
from app.domain.persistence import DataConnectorRecord, MaterialRecord, SupplierRecord
from app.domain.supply_feedback import FeedbackAccess, FeedbackBatch, FeedbackRow, SupplyFeedback
from app.services.audit_service import write_audit_log
from app.services.supply_analysis import (
    METRICS,
    distribution,
    metric_groups,
    metric_values,
    observations,
    rfq_analysis,
)

router = APIRouter(tags=["supply-feedback"])


@router.post("/supply-feedback/weight-demo", dependencies=[Depends(manager)])
def weight_demo(db=Depends(get_db)):
    from app.services.feedback_demo import seed_weight_demo
    result = seed_weight_demo(db)
    analysis = rfq_analysis(db, result["rfq_id"], include_demo=True)
    from app.api.routes.doe import Design, DoeRecord, Factor, Observations, create, save

    for material_code, model in analysis["weight_models"].items():
        existing = [
            json.loads(row.payload)
            for row in db.scalars(select(DoeRecord).where(DoeRecord.material_code == material_code))
        ]
        if any(item.get("model_fingerprint") == model["fingerprint"] for item in existing):
            continue
        factors = [
            Factor(name=item["label"], low=float(weight["min"]), high=float(weight["max"]))
            for item, weight in zip(model["features"], model["weights"], strict=True)
        ]
        study = create(
            Design(
                material_code=material_code,
                model_fingerprint=model["fingerprint"],
                factors=factors,
                runs=30,
                design_kind="screening",
                seed=20260913,
            ),
            db,
        )
        values = [
            150 + sum((index + 1) * value * 2.5 for index, value in enumerate(row["coded"])) + ((row["run"] % 3) - 1) * 0.08
            for row in study["design"]
        ]
        save(
            study["id"],
            Observations(
                values=values,
                evidence="【模拟】六因子DOE及五折交叉验证演示，不得作为正式定价系数依据。",
                version=1,
                simulated=True,
            ),
            db,
        )
    return rfq_analysis(db, result["rfq_id"], include_demo=True)


@router.post("/supply-feedback/demo", dependencies=[Depends(manager)])
def demo(db=Depends(get_db)):
    from app.services.feedback_demo import seed_feedback_demo
    return seed_feedback_demo(db)


@router.get("/supply-feedback/demo-analysis", dependencies=[Depends(editor)])
def demo_analysis(db=Depends(get_db)):
    from uuid import NAMESPACE_URL, uuid5
    return rfq_analysis(db, str(uuid5(NAMESPACE_URL, "pebs-feedback-demo-rfq")), include_demo=True)


@router.post("/rfqs/{rfq_id}/demo-feedback", dependencies=[Depends(manager)])
def rfq_demo(rfq_id: str, db=Depends(get_db)):
    from app.services.feedback_demo import seed_rfq_demo
    return seed_rfq_demo(db, rfq_id)

FIELDS = {
    "external_id": "来源系统唯一批次ID；同连接器重复ID且内容相同跳过，内容不同拒绝整批",
    "supplier_code": "已有供应商编码（非名称或UUID）", "material_code": "已有物料编码",
    "record_date": "业务日期 YYYY-MM-DD", "unit": "计量单位，与询价单位一致才可分析TOC", "currency": "三位大写币种，不自动换汇",
    "metrics_available_date": "质量/交付/返工/响应指标实际全部可用日期 YYYY-MM-DD，不早于业务日期；多元预测定标必须提供，历史缺失仅可诊断",
    "received_quantity": "本批收货数量>0", "inspected_quantity": "本批检验数量；缺失时空白，不按0补齐",
    "accepted_quantity": "合格数量<=检验数量", "on_time_quantity": "准时到货数量<=收货数量",
    "rework_quantity": "返工数量<=检验数量", "response_hours": "供应商实际服务响应时长（小时），越低越好",
    "lead_time_days": "订单确认至实际到货的交期天数；用于DOE与多元TOC模型，缺失不能按0",
    "unit_price": "未税采购单价", "tax_rate": "税率0—1，例如0.13",
    "logistics_cost": "本批物流总费用", "rework_cost": "本批返工总费用", "delay_cost": "本批延期总费用",
    "other_cost": "本批其他费用", "credit": "本批退款/索赔，不能超过总成本",
    "costs_confirmed": "true/false；只有全批质检完成、提供价格且成本确认的记录进入TOC；默认false",
}


@router.get("/supply-feedback/guide", dependencies=[Depends(manager)])
def guide():
    return {"fields": [{"name": k, "description": FIELDS[k], "required": f.is_required()} for k, f in FeedbackRow.model_fields.items()], "instructions": ["ERP/MES/WMS/QMS侧先按供应商编码+物料编码+批次汇总为统一字段，本版本接收推送，不主动拉取第三方系统。", "在连接器中启用状态，生成专用反馈令牌；外部POST JSON {rows:[...]}，Authorization: Bearer <token>。令牌仅能写入该连接器，轮换后旧令牌失效。", "人工导入支持UTF-8/BOM CSV，字段与API一致；单次1—1000行、最大5MB。整批校验后提交，不接受部分成功。", "质量合格率=合格/检验；准时率=准时数量/收货；返工率=返工/检验；服务=响应小时。按批次分布计算中位数及均值，不把缺失数据当0。", "Shapiro-Wilk检验3—5000个样本，p<0.05拒绝正态假设。百分比有界，正态参考曲线不是数据真实性保证；统计最多使用最新5000条。", "TOC模拟数据默认排除，勾选后仅供演示，不能直接用于正式TOC定标。"], "example": {"rows": [{"external_id": "WMS-GR-0001", "supplier_code": "YOUR-SUPPLIER", "material_code": "YOUR-MATERIAL", "record_date": "2026-09-01", "received_quantity": 100, "inspected_quantity": 100, "accepted_quantity": 98, "on_time_quantity": 95, "rework_quantity": 2, "response_hours": 4, "unit_price": 100, "costs_confirmed": True}]}}


@router.get("/supply-feedback/template", dependencies=[Depends(manager)])
def template():
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(FeedbackRow.model_fields))
    writer.writeheader()
    return Response(content=("\ufeff"+buffer.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="supply-feedback-template.csv"'})


def connector(db, connector_id):
    record = db.get(DataConnectorRecord, connector_id)
    if not record:
        raise HTTPException(404, "未找到连接器")
    return record


@router.get("/data-connectors/{connector_id}/feedback-access", dependencies=[Depends(manager)])
def access_info(connector_id: str, db=Depends(get_db)):
    record = connector(db, connector_id)
    return {"endpoint": f"/api/v1/integration-feedback/{record.id}", "token_set": bool(db.get(FeedbackAccess, record.id)), "status": record.status}


@router.post("/data-connectors/{connector_id}/feedback-token")
def rotate_token(connector_id: str, db=Depends(get_db), user=Depends(manager)):
    connector(db, connector_id)
    token = secrets.token_urlsafe(40)
    access = db.get(FeedbackAccess, connector_id) or FeedbackAccess(connector_id=connector_id)
    access.token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.add(access)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="rotate", resource_type="feedback_token", resource_id=connector_id, detail="轮换反馈接入令牌（不记录明文）")
    db.commit()
    return {"token": token, "message": "仅此一次显示，请安全保存；旧令牌已失效"}


def ingest(db, record, rows, actor):
    if record.status != "active":
        raise HTTPException(409, "连接器未启用")
    suppliers = set(db.scalars(select(SupplierRecord.code)))
    materials = set(db.scalars(select(MaterialRecord.code)))
    seen = {}
    inserted, skipped = 0, 0
    for i, row in enumerate(rows, 1):
        if row.supplier_code not in suppliers or row.material_code not in materials:
            raise HTTPException(422, f"第{i}行供应商或物料编码不存在，请先维护主数据")
        content = row.model_dump_json()
        previous = db.scalar(select(SupplyFeedback).where(SupplyFeedback.connector_id == record.id, SupplyFeedback.external_id == row.external_id))
        existing = previous.payload_json if previous else seen.get(row.external_id)
        if existing:
            if existing != content:
                raise HTTPException(409, f"第{i}行批次ID重复但内容不同，未写入本批数据")
            skipped += 1
            continue
        db.add(SupplyFeedback(connector_id=record.id, external_id=row.external_id, supplier_code=row.supplier_code, material_code=row.material_code, record_date=row.record_date, source_system=str(record.connector_type), is_demo=False, payload_json=content))
        seen[row.external_id] = content
        inserted += 1
    write_audit_log(db, actor_id=actor, actor_role="integration", action="import", resource_type="supply_feedback", resource_id=record.id, detail=f"新增{inserted}条，重复跳过{skipped}条")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "存在并发重复记录，请重试同一批次") from None
    return {"inserted": inserted, "skipped": skipped}


@router.post("/integration-feedback/{connector_id}")
def push(connector_id: str, payload: FeedbackBatch, authorization: str = Header(""), db=Depends(get_db)):
    access = db.get(FeedbackAccess, connector_id)
    actual = hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest()
    if not authorization.startswith("Bearer ") or not access or not hmac.compare_digest(actual, access.token_hash):
        raise HTTPException(401, "反馈接入令牌无效")
    return ingest(db, connector(db, connector_id), payload.rows, "connector:"+connector_id)


@router.post("/data-connectors/{connector_id}/feedback-import")
async def import_csv(connector_id: str, file: UploadFile = File(...), db=Depends(get_db), user=Depends(manager)):
    content = await file.read(5*1024*1024+1)
    if len(content) > 5*1024*1024:
        raise HTTPException(422, "文件不能超过5MB")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("缺少或重复表头")
        unknown = set(reader.fieldnames) - set(FeedbackRow.model_fields)
        required = {k for k, f in FeedbackRow.model_fields.items() if f.is_required()}
        missing = required - set(reader.fieldnames)
        if unknown:
            raise ValueError("未知字段：" + ", ".join(sorted(unknown)))
        if missing:
            raise ValueError("缺少必填字段：" + ", ".join(sorted(missing)))
        rows = []
        for i, row in enumerate(reader, 2):
            if i > 1001:
                raise ValueError("单次最多1000行")
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"第{i}行列数与模板表头不一致")
            try:
                rows.append(FeedbackRow.model_validate({k: v for k, v in row.items() if v != ""}))
            except ValidationError as exc:
                raise ValueError(f"第{i}行："+str(exc.errors()[0]["msg"])) from exc
        if not rows:
            raise ValueError("没有数据行")
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        raise HTTPException(422, "CSV校验失败："+str(exc)[:300]) from exc
    return ingest(db, connector(db, connector_id), rows, user.user_id)


@router.get("/supply-feedback/records", dependencies=[Depends(manager)])
def records(connector_id: str = "", page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db=Depends(get_db)):
    filters = [SupplyFeedback.connector_id == connector_id] if connector_id else []
    total = db.scalar(select(func.count()).select_from(SupplyFeedback).where(*filters))
    data = db.scalars(select(SupplyFeedback).where(*filters).order_by(SupplyFeedback.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    return {"items": [{**json.loads(r.payload_json), "source_system": r.source_system, "is_demo": r.is_demo} for r in data], "total": total, "page": page, "page_size": page_size}


@router.get("/supplier-metrics", dependencies=[Depends(editor)])
def groups(material_code: str = "", supplier_code: str = "", include_demo: bool = False, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db=Depends(get_db)):
    data = metric_groups(db, material_code, include_demo)
    if supplier_code:
        data = [r for r in data if r["supplier_code"] == supplier_code]
    return {"items": data[(page-1)*page_size:page*page_size], "total": len(data), "page": page, "page_size": page_size}


@router.get("/supplier-metrics/statistics", dependencies=[Depends(editor)])
def statistics(supplier_code: str, material_code: str, metric: str, include_demo: bool = False, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db=Depends(get_db)):
    if metric not in METRICS:
        raise HTTPException(422, "未知指标")
    data = [{**r, "value": metric_values(r)[metric]} for r in observations(db, supplier_code, material_code, include_demo)]
    valid = [r for r in data if r["value"] is not None]
    return {"label": METRICS[metric], "statistics": distribution([r["value"] for r in valid]), "items": data[(page-1)*page_size:page*page_size], "total": len(data), "page": page, "page_size": page_size, "missing_count": len(data)-len(valid), "demo_count": sum(r["is_demo"] for r in data)}


@router.get("/rfqs/{rfq_id}/award-analysis", dependencies=[Depends(editor)])
def award_analysis(rfq_id: str, include_demo: bool = False, db=Depends(get_db)):
    return rfq_analysis(db, rfq_id, include_demo)

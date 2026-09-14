import json
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import median
from uuid import NAMESPACE_URL, uuid5

from app.domain.persistence import (
    DataConnectorRecord,
    MaterialRecord,
    QuotationLineRecord,
    QuotationRecord,
    RFQInvitationRecord,
    RFQLineRecord,
    RFQRecord,
    SupplierRecord,
)
from app.domain.supplier_portal import QuotationReview
from app.domain.supply_feedback import FeedbackRow, SupplyFeedback


def seed_weight_demo(db):
    """Independent lagged signal demo. Never replaces real rows or existing demo cohorts."""
    def key(name):
        return str(uuid5(NAMESPACE_URL, "pebs-toc-weights-v1-"+name))
    connector_id = key("connector")
    if not db.get(DataConnectorRecord, connector_id):
        db.add(DataConnectorRecord(id=connector_id, name="【模拟】多元TOC权重样本", connector_type="mes", status="active", created_by="DEMO-WEIGHTS"))
    material = "DEMO-WT-M001"
    if not db.get(MaterialRecord, key("material")):
        db.add(MaterialRecord(id=key("material"), code=material, name="【模拟】权重分析零件", unit="件"))
    rfq = db.get(RFQRecord, key("rfq"))
    if not rfq:
        rfq = RFQRecord(id=key("rfq"), rfq_no="DEMO-WT-RFQ", title="【模拟】多指标权重与时间验证", currency="CNY", status="published", created_by="DEMO-WEIGHTS")
        rfq.lines.append(RFQLineRecord(material_code=material, material_name="【模拟】权重分析零件", quantity=100, unit="件"))
        db.add(rfq)
    inserted = 0
    for s in range(3):
        code = f"DEMO-WT-S{s+1}"
        if not db.get(SupplierRecord, key(code)):
            db.add(SupplierRecord(id=key(code), code=code, name=f"【模拟】权重供应商{s+1}", status="qualified"))
        rng = random.Random(3500+s)
        history = []
        for batch in range(80):
            values = [rng.uniform(2, 10), rng.uniform(3, 22), rng.uniform(1, 8), rng.uniform(1, 16)]
            lag = [median([p[j] for p in history[-5:]]) for j in range(4)] if history else values
            price = rng.uniform(75, 115)
            lead_time = rng.uniform(5, 25)
            landed = price*1.13+1
            accepted = 100-values[0]
            target = landed*1.15+.75*lead_time+1.8*lag[0]+.65*lag[1]+.9*lag[2]+.4*lag[3]+rng.gauss(0, .5)
            other = max(0, target*accepted-landed*100)
            external = f"WT-{s}-{batch}"
            row = FeedbackRow(external_id=external, supplier_code=code, material_code=material, record_date=datetime.now(UTC).date()-timedelta(days=(81-batch)*7), metrics_available_date=datetime.now(UTC).date()-timedelta(days=(81-batch)*7-1), received_quantity=100, inspected_quantity=100, accepted_quantity=accepted, on_time_quantity=100-values[1], rework_quantity=values[2], response_hours=values[3], lead_time_days=lead_time, unit_price=price, logistics_cost=100, other_cost=other, costs_confirmed=True)
            existing = db.get(SupplyFeedback, key(external))
            if not existing:
                db.add(SupplyFeedback(id=key(external), connector_id=connector_id, external_id=external, supplier_code=code, material_code=material, record_date=row.record_date, source_system="DEMO-WEIGHTS", is_demo=True, payload_json=row.model_dump_json()))
                inserted += 1
            elif "lead_time_days" not in existing.payload_json:
                existing.payload_json = row.model_dump_json()
            history.append(values)
        if not db.get(QuotationRecord, key("quote"+code)):
            quote = QuotationRecord(id=key("quote"+code), quotation_no="DEMO-WT-Q"+str(s+1), supplier_id=code, supplier_name=f"【模拟】权重供应商{s+1}", currency="CNY", delivery_days=10+s*2)
            quote.lines.append(QuotationLineRecord(material_code=material, material_name="【模拟】权重分析零件", quantity=100, unit="件", unit_price=90+s*2, tax_rate=Decimal("0.13"), logistics_cost=100))
            db.add(quote)
            rfq.invitations.append(RFQInvitationRecord(supplier_id=code, supplier_name=quote.supplier_name, quotation_id=quote.id, status="responded"))
            db.add(QuotationReview(quotation_id=quote.id, rfq_id=rfq.id, status="verified", reviewer_id="DEMO-WEIGHTS", note="模拟报价自动标记为已核验"))
        elif not db.get(QuotationReview, key("quote"+code)):
            db.add(QuotationReview(quotation_id=key("quote"+code), rfq_id=rfq.id, status="verified", reviewer_id="DEMO-WEIGHTS", note="模拟报价自动标记为已核验"))
    db.commit()
    return {"inserted": inserted, "rfq_id": rfq.id}


def seed_rfq_demo(db, rfq_id):
    """Create only explicitly marked sample batches for existing quoted materials."""
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.services.rfq_service import rfq_service

    rfq = rfq_service.get(db, rfq_id)
    if not rfq:
        raise HTTPException(404, "未找到询价")
    quotes = [db.get(QuotationRecord, i.quotation_id) for i in rfq.invitations if i.quotation_id]
    quotes = [q for q in quotes if q]
    if not quotes:
        raise HTTPException(409, "尚无供应商回标；请先完成报价，或使用 DEMO-FB-RFQ 演示询价")
    connector_id = str(uuid5(NAMESPACE_URL, "pebs-rfq-context-demo"))
    if not db.get(DataConnectorRecord, connector_id):
        db.add(DataConnectorRecord(id=connector_id, name="【模拟】询价TOC演示批次", connector_type="mes", base_url="", sync_mode="manual", status="active", created_by="DEMO-FEEDBACK"))
    suppliers = list(db.scalars(select(SupplierRecord)))
    inserted = 0
    for index, quote in enumerate(sorted(quotes, key=lambda q: q.id)):
        supplier = next((s for s in suppliers if quote.supplier_id in (s.id, s.code)), None)
        code = supplier.code if supplier else quote.supplier_id
        for line in quote.lines:
            rng = random.Random(f"{rfq_id}-{quote.id}-{line.material_code}")
            for batch in range(18):
                external_id = f"RFQ-DEMO-{uuid5(NAMESPACE_URL, f'{rfq_id}-{quote.id}-{line.material_code}-{batch}')}"
                row_id = str(uuid5(NAMESPACE_URL, external_id))
                existing = db.get(SupplyFeedback, row_id)
                if existing:
                    payload = json.loads(existing.payload_json)
                    payload.setdefault("lead_time_days", quote.delivery_days)
                    payload.setdefault("metrics_available_date", (existing.record_date + timedelta(days=1)).isoformat())
                    existing.payload_json = json.dumps(payload, ensure_ascii=False)
                    continue
                quality = round(min(99.9, max(70, rng.gauss(90+index%3*3, 2))), 2)
                price = round(float(line.unit_price)*rng.uniform(.88, 1.12), 4)
                day = datetime.now(UTC).date()-timedelta(days=(18-batch)*7)
                row = FeedbackRow(external_id=external_id, supplier_code=code, material_code=line.material_code, record_date=day, metrics_available_date=day+timedelta(days=1), currency=quote.currency, unit=line.unit, received_quantity=100, inspected_quantity=100, accepted_quantity=quality, on_time_quantity=95, rework_quantity=round((100-quality)/2, 2), response_hours=round(rng.uniform(1, 12), 2), lead_time_days=quote.delivery_days, unit_price=price, tax_rate=float(line.tax_rate), logistics_cost=100, rework_cost=round(price*rng.uniform(2, 8), 2), delay_cost=round(price*rng.uniform(1, 5), 2), costs_confirmed=True)
                db.add(SupplyFeedback(id=row_id, connector_id=connector_id, external_id=external_id, supplier_code=code, material_code=line.material_code, record_date=row.record_date, source_system="DEMO-RFQ", is_demo=True, payload_json=row.model_dump_json()))
                inserted += 1
    db.commit()
    return {"inserted": inserted, "message": "演示批次已生成；不修改报价、不参与正式定标"}


def seed_feedback_demo(db):
    def key(name):
        return str(uuid5(NAMESPACE_URL, "pebs-feedback-demo-"+name))

    connector = db.get(DataConnectorRecord, key("connector"))
    if not connector:
        connector = DataConnectorRecord(id=key("connector"), name="【模拟】WMS/MES供货反馈", connector_type="mes", base_url="", sync_mode="manual", status="active", created_by="DEMO-FEEDBACK")
        db.add(connector)
    for m in range(1, 3):
        if not db.get(MaterialRecord, key(f"material-{m}")):
            db.add(MaterialRecord(id=key(f"material-{m}"), code=f"DEMO-FB-M{m:03d}", name=f"【模拟】精密零件{m}", unit="件", created_by="DEMO-FEEDBACK"))
    inserted = 0
    rng = random.Random(20260904)
    for s in range(1, 4):
        supplier_code = f"DEMO-FB-S{s}"
        if not db.get(SupplierRecord, key(f"supplier-{s}")):
            db.add(SupplierRecord(id=key(f"supplier-{s}"), code=supplier_code, name=f"【模拟】供货商{s}", status="qualified", email=f"demo{s}@example.invalid", created_by="DEMO-FEEDBACK"))
        for m in range(1, 3):
            for batch in range(24):
                quality = min(100, max(1, rng.gauss([82, 98, 96][s-1], 2)))
                price = [80, 90, 94][s-1]*m + rng.gauss(0, 3)
                day = date(2026, 3, 1)+timedelta(days=batch*7)
                row = FeedbackRow(external_id=f"DEMO-{s}-{m}-{batch}", supplier_code=supplier_code, material_code=f"DEMO-FB-M{m:03d}", record_date=day, metrics_available_date=day+timedelta(days=1), received_quantity=100, inspected_quantity=100, accepted_quantity=round(quality, 2), on_time_quantity=round(min(100, max(0, rng.gauss([82, 97, 95][s-1], 3))), 2), rework_quantity=round((100-quality)/2, 2), response_hours=round(max(0, rng.gauss([12, 3, 5][s-1], 1.2)), 2), lead_time_days=[24, 10, 14][s-1], unit_price=round(price, 2), logistics_cost=100, rework_cost=[500, 30, 80][s-1], delay_cost=[400, 20, 60][s-1], costs_confirmed=True)
                existing = db.get(SupplyFeedback, key(row.external_id))
                if not existing:
                    db.add(SupplyFeedback(id=key(row.external_id), connector_id=connector.id, external_id=row.external_id, supplier_code=row.supplier_code, material_code=row.material_code, record_date=row.record_date, source_system="DEMO-MES-WMS", is_demo=True, payload_json=row.model_dump_json()))
                    inserted += 1
                elif "lead_time_days" not in existing.payload_json:
                    existing.payload_json = row.model_dump_json()
    rfq_id = key("rfq")
    if not db.get(RFQRecord, rfq_id):
        rfq = RFQRecord(id=rfq_id, rfq_no="DEMO-FB-RFQ", title="【模拟】最低价与TOC供货成本对比", currency="CNY", status="published", created_by="DEMO-FEEDBACK")
        for m in range(1, 3):
            rfq.lines.append(RFQLineRecord(material_code=f"DEMO-FB-M{m:03d}", material_name=f"【模拟】精密零件{m}", quantity=100, unit="件"))
        for s in range(1, 4):
            quote = QuotationRecord(id=key(f"quote-{s}"), quotation_no=f"DEMO-FB-Q{s}", supplier_id=f"DEMO-FB-S{s}", supplier_name=f"【模拟】供货商{s}", currency="CNY", created_by="DEMO-FEEDBACK")
            for m in range(1, 3):
                quote.lines.append(QuotationLineRecord(material_code=f"DEMO-FB-M{m:03d}", material_name=f"【模拟】精密零件{m}", quantity=100, unit="件", unit_price=[80,90,94][s-1]*m, tax_rate=Decimal("0.13"), logistics_cost=100, expected_quality_loss=0))
            db.add(quote)
            rfq.invitations.append(RFQInvitationRecord(supplier_id=quote.supplier_id, supplier_name=quote.supplier_name, quotation_id=quote.id, status="responded"))
            db.add(QuotationReview(quotation_id=quote.id, rfq_id=rfq.id, status="verified", reviewer_id="DEMO-FEEDBACK", note="模拟报价自动标记为已核验"))
        db.add(rfq)
    else:
        rfq = db.get(RFQRecord, rfq_id)
        for invitation in rfq.invitations:
            if invitation.quotation_id and not db.get(QuotationReview, invitation.quotation_id):
                db.add(QuotationReview(quotation_id=invitation.quotation_id, rfq_id=rfq.id, status="verified", reviewer_id="DEMO-FEEDBACK", note="模拟报价自动标记为已核验"))
    db.commit()
    return {"inserted": inserted, "rfq_id": rfq_id, "material_codes": ["DEMO-FB-M001", "DEMO-FB-M002"], "message": "模拟数据默认不参与正式统计；分析页勾选包含模拟数据后查看"}

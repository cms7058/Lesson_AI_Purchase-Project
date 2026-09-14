import json
import math
from collections import defaultdict
from statistics import mean, median, stdev

import numpy as np
from fastapi import HTTPException
from scipy import stats
from sqlalchemy import select

from app.domain.persistence import QuotationRecord, SupplierRecord
from app.domain.supplier_portal import QuotationReview
from app.domain.supply_feedback import SupplyFeedback
from app.services.rfq_service import rfq_service
from app.services.toc_weights import build_model, quote_prediction

METRICS = {"quality": "质量合格率(%)", "delivery": "准时交付率(%)", "rework": "返工率(%)", "response": "服务响应时长(小时)"}


def metric_values(row):
    inspected = row.get("inspected_quantity")
    return {
        "quality": 100*row["accepted_quantity"]/inspected if inspected and row.get("accepted_quantity") is not None else None,
        "delivery": 100*row["on_time_quantity"]/row["received_quantity"] if row.get("on_time_quantity") is not None else None,
        "rework": 100*row["rework_quantity"]/inspected if inspected and row.get("rework_quantity") is not None else None,
        "response": row.get("response_hours"),
    }


def observations(db, supplier_code="", material_code="", include_demo=False):
    filters = []
    if supplier_code:
        filters.append(SupplyFeedback.supplier_code == supplier_code)
    if material_code:
        filters.append(SupplyFeedback.material_code == material_code)
    if not include_demo:
        filters.append(SupplyFeedback.is_demo.is_(False))
    records = db.scalars(select(SupplyFeedback).where(*filters).order_by(SupplyFeedback.record_date.desc(), SupplyFeedback.id).limit(5000))
    return [{**json.loads(r.payload_json), "id": r.id, "source_system": r.source_system, "is_demo": r.is_demo} for r in records]


def distribution(values):
    n = len(values)
    if not n:
        return {"n": 0, "median": None, "mean": None, "std": None, "normal_curve": [], "histogram": [], "qq": [], "box": [], "normality": "无有效数据"}
    mu = mean(values)
    sigma = stdev(values) if n > 1 else 0
    q1, med, q3 = map(float, np.quantile(values, [0.25, 0.5, 0.75]))
    result = {"n": n, "mean": mu, "median": med, "std": sigma, "box": [min(values), q1, med, q3, max(values)], "normal_curve": [], "histogram": [], "qq": [], "normality": "样本不足，不能进行正态性检验", "p_value": None}
    counts, edges = np.histogram(values, bins=min(12, max(1, math.ceil(math.sqrt(n)))))
    result["histogram"] = [[float((edges[i]+edges[i+1])/2), float(count/(n*(edges[i+1]-edges[i])))] for i, count in enumerate(counts)]
    if sigma > 1e-12:
        xs = np.linspace(min(min(values), mu-3*sigma), max(max(values), mu+3*sigma), 80)
        result["normal_curve"] = [[float(x), float(stats.norm.pdf(x, mu, sigma))] for x in xs]
        theoretical, ordered = stats.probplot(values, dist="norm", fit=False)
        result["qq"] = [[float(x), float(y)] for x, y in zip(theoretical, ordered, strict=True)]
        if n >= 3:
            p = float(stats.shapiro(values).pvalue)
            result.update(p_value=p, normality="未拒绝正态假设（不等于证明正态）" if p >= 0.05 else "拒绝正态假设，建议采用中位数等稳健统计")
    else:
        result["normality"] = "所有样本相同，无法进行正态性检验"
    return result


def metric_groups(db, material_code="", include_demo=False):
    groups = defaultdict(list)
    for row in observations(db, material_code=material_code, include_demo=include_demo):
        groups[(row["supplier_code"], row["material_code"])].append(row)
    names = {s.code: s.name for s in db.scalars(select(SupplierRecord))}
    output = []
    for (supplier, material), rows in sorted(groups.items()):
        metrics = {}
        for metric in METRICS:
            vals = [metric_values(r)[metric] for r in rows if metric_values(r)[metric] is not None]
            metrics[metric] = {"n": len(vals), "median": median(vals) if vals else None, "mean": mean(vals) if vals else None}
        output.append({"supplier_code": supplier, "supplier_name": names.get(supplier, supplier), "material_code": material, "batches": len(rows), "demo_count": sum(r["is_demo"] for r in rows), "metrics": metrics})
    return output


def cost_profile(rows, currency, unit):
    samples = []
    for row in rows:
        if not row["costs_confirmed"] or row["currency"] != currency or row["unit"] != unit or row.get("accepted_quantity") is None:
            continue
        price = row["unit_price"]*(1+row["tax_rate"])
        extra = row["rework_cost"]+row["delay_cost"]+row["other_cost"]-row["credit"]
        cost = (price*row["received_quantity"]+row["logistics_cost"]+extra)/row["accepted_quantity"] if row["accepted_quantity"] else None
        samples.append({"external_id": row["external_id"], "date": row["record_date"], "price": price, "cost": cost, "yield_rate": row["accepted_quantity"]/row["received_quantity"], "extra": extra/row["received_quantity"], "is_demo": row.get("is_demo", False)})
    result = {"n": len(samples), "samples": samples, "median_yield": median([s["yield_rate"] for s in samples]) if samples else None, "median_extra": median([s["extra"] for s in samples]) if samples else None, "regression": None, "note": "至少5个批次且价格有变化才拟合回归；回归仅用于历史成本诊断，不替代报价与成本明细"}
    finite = [s for s in samples if s["cost"] is not None]
    result["distribution"] = distribution([s["cost"] for s in finite])
    if len(finite) >= 5 and len({s["price"] for s in finite}) > 1:
        fitted = stats.linregress([s["price"] for s in finite], [s["cost"] for s in finite])
        lo, hi = min(s["price"] for s in finite), max(s["price"] for s in finite)
        result["regression"] = {"intercept": float(fitted.intercept), "slope": float(fitted.slope), "r_squared": float(fitted.rvalue**2) if math.isfinite(fitted.rvalue) else None, "line": [[lo, float(fitted.intercept+fitted.slope*lo)], [hi, float(fitted.intercept+fitted.slope*hi)]]}
    return result


def rfq_analysis(db, rfq_id, include_demo=False):
    rfq = rfq_service.get(db, rfq_id)
    if not rfq:
        raise HTTPException(404, "未找到询价项目")
    expected = {line.material_code: line for line in rfq.lines}
    if len(expected) != len(rfq.lines):
        raise HTTPException(409, "询价存在重复物料行，请先按物料合并以进行整体定标")
    suppliers = list(db.scalars(select(SupplierRecord)))
    weight_models = {code: build_model(observations(db, material_code=code, include_demo=include_demo), rfq.currency, requirement.unit) for code, requirement in expected.items()}
    from app.api.routes.doe import DoeRecord, diagnostics

    for material_code, model in weight_models.items():
        expected_factors = [feature["label"] for feature in model["features"]]
        candidates = []
        for record in db.scalars(select(DoeRecord).where(DoeRecord.material_code == material_code)):
            study = json.loads(record.payload)
            if study.get("model_fingerprint") != model["fingerprint"]:
                continue
            diagnostic = diagnostics(study)
            factor_names = [factor["name"] for factor in study.get("factors", [])]
            candidates.append({"id": record.id, "factor_match": factor_names == expected_factors, "study": study, "diagnostics": diagnostic})
        selected = next((item for item in candidates if item["factor_match"] and item["diagnostics"].get("passed")), None)
        selected = selected or next((item for item in reversed(candidates) if item["factor_match"]), None)
        model["doe_validation"] = selected or {
            "factor_match": False,
            "diagnostics": {"status": "尚未建立与当前模型指纹匹配的六因子DOE方案", "passed": False},
        }
        model["pricing_usable"] = bool(model.get("usable") and model["doe_validation"]["diagnostics"].get("passed"))
    rows = []
    for invitation in rfq.invitations:
        if not invitation.quotation_id:
            continue
        quote = db.get(QuotationRecord, invitation.quotation_id)
        if not quote:
            continue
        supplier = next((s for s in suppliers if invitation.supplier_id in [s.id, s.code]), None)
        code = supplier.code if supplier else invitation.supplier_id
        review = db.get(QuotationReview, quote.id)
        review_status = review.status if review else "pending"
        row = {"quotation_id": quote.id, "supplier_name": quote.supplier_name, "supplier_code": code, "quoted_total": 0.0, "tco_total": None, "materials": [], "valid": review_status == "verified", "reason": "" if review_status == "verified" else "报价尚未人工核验，不能参与定标", "review_status": review_status, "demo_count": 0}
        actual = {line.material_code: line for line in quote.lines}
        if set(actual) != set(expected) or len(actual) != len(quote.lines) or quote.currency != rfq.currency:
            row.update(valid=False, reason="报价物料范围或币种不一致")
        for material, requirement in expected.items():
            line = actual.get(material)
            if not line or line.unit != requirement.unit or line.quantity != requirement.quantity:
                row.update(valid=False, reason="报价缺少物料或单位、数量不一致")
                continue
            qty = float(requirement.quantity)
            quoted = float(line.quantity*line.unit_price*(1+line.tax_rate)+line.logistics_cost)
            history = observations(db, code, material, include_demo)
            profile = cost_profile(history, rfq.currency, requirement.unit)
            row["demo_count"] += sum(s["is_demo"] for s in profile["samples"])
            estimate = (quoted+qty*profile["median_extra"])/profile["median_yield"] if profile["n"] >= 3 and profile["median_yield"] else None
            if estimate is not None and estimate < 0:
                estimate = None
            prediction = quote_prediction(weight_models[material], code, quoted/qty, qty, quote.delivery_days)
            row["materials"].append({"material_code": material, "material_name": requirement.material_name, "quantity": qty, "unit": requirement.unit, "quoted": quoted, "tco": estimate, "accounting_tco": estimate, "prediction": prediction, "cost_method": "历史成本核算", "profile": profile})
            row["quoted_total"] += quoted
        if row["valid"] and len(row["materials"]) == len(expected) and all(m["tco"] is not None for m in row["materials"]):
            row["tco_total"] = sum(m["tco"] for m in row["materials"])
        rows.append(row)
    valid = [r for r in rows if r["valid"]]
    # All suppliers for a material use the same method, never mixed comparisons.
    for material in expected:
        candidates = [m for r in valid for m in r["materials"] if m["material_code"] == material]
        if len(candidates) == len(valid) and candidates and all(m["prediction"]["total"] is not None for m in candidates):
            for m in candidates:
                m["tco"] = m["prediction"]["total"]
                m["cost_method"] = "多元回归预测"
    for row in valid:
        row["tco_total"] = sum(m["tco"] for m in row["materials"]) if len(row["materials"]) == len(expected) and all(m["tco"] is not None for m in row["materials"]) else None
    complete = [r for r in valid if r["tco_total"] is not None]
    lowest = min((r["quoted_total"] for r in valid), default=None)
    return {"weight_models": weight_models, "rfq_id": rfq.id, "rfq_no": rfq.rfq_no, "currency": rfq.currency, "items": rows, "include_demo": include_demo, "verified_count": len(valid), "quoted_count": len(rows), "review_ready": bool(rows) and len(valid) == len(rows), "lowest_ids": [r["quotation_id"] for r in valid if lowest is not None and abs(r["quoted_total"]-lowest) < 0.005], "tco_ids": [r["quotation_id"] for r in complete if abs(r["tco_total"]-min(v["tco_total"] for v in complete)) < 0.005] if valid and len(complete) == len(valid) else [], "tco_ready": bool(valid) and len(complete) == len(valid), "doe_ready": bool(weight_models) and all(model["pricing_usable"] for model in weight_models.values()), "formula": "只有当前版本已人工核验通过的报价才能进入比较。六个因子（价格、交期、响应、及时率、合格率、返修率）必须完成与当前模型指纹一致的DOE及交叉验证；任一因子未通过显著性、跨折方向稳定性或系数波动检查时，禁止把多元回归系数用于定价，整项统一回退历史成本核算。归一化权重仅用于解释。最低价=本询价含税货款+报价物流费；历史TOC=(报价合计+询价数量×历史单位收货附加费用中位数)÷历史合格品率中位数。"}

import json
import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.mro_intelligence import (
    MroDemandEventRecord,
    MroLeadTimeRecord,
    MroMaterialProfileRecord,
    MroPlanningRunRecord,
    MroSupplyPositionRecord,
)
from app.domain.persistence import MaterialRecord

ATTRIBUTE_COLORS = {
    "停场关键": "#e5484d",
    "单一来源": "#f97316",
    "长交期": "#7c3aed",
    "高价值": "#d89b00",
    "可修理件": "#1677ff",
    "间歇需求": "#0891b2",
    "高合规": "#db2777",
    "低可替代": "#475569",
}


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    point = (len(ordered) - 1) * probability
    low = math.floor(point)
    high = math.ceil(point)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] * (high - point) + ordered[high] * (point - low))


def diagnostic(values: list[float], unit: str) -> dict:
    cleaned = [
        float(value) for value in values if value is not None and math.isfinite(float(value))
    ]
    if not cleaned:
        return {
            "count": 0,
            "unit": unit,
            "normality": "insufficient",
            "normality_p": None,
            "median": 0,
            "mean": 0,
            "std": 0,
            "q25": 0,
            "q75": 0,
            "q90": 0,
            "outliers": 0,
            "histogram": [],
        }
    avg = mean(cleaned)
    deviation = pstdev(cleaned) if len(cleaned) > 1 else 0.0
    p_value = None
    normality = "insufficient"
    if len(cleaned) >= 8 and deviation > 0:
        skewness = sum(((item - avg) / deviation) ** 3 for item in cleaned) / len(cleaned)
        kurtosis = sum(((item - avg) / deviation) ** 4 for item in cleaned) / len(cleaned)
        jarque_bera = len(cleaned) / 6 * (skewness**2 + (kurtosis - 3) ** 2 / 4)
        p_value = math.exp(-jarque_bera / 2)
        normality = "normal" if p_value >= 0.05 else "non_normal"
    q25, q75 = _quantile(cleaned, 0.25), _quantile(cleaned, 0.75)
    iqr = q75 - q25
    low, high = q25 - 1.5 * iqr, q75 + 1.5 * iqr
    minimum, maximum = min(cleaned), max(cleaned)
    bins = min(8, max(1, round(math.sqrt(len(cleaned)))))
    width = (maximum - minimum) / bins if maximum > minimum else 1
    histogram = []
    for index in range(bins):
        start = minimum + index * width
        end = maximum if index == bins - 1 else minimum + (index + 1) * width
        count = sum(
            1
            for value in cleaned
            if value >= start and (value <= end if index == bins - 1 else value < end)
        )
        histogram.append({"range": f"{start:.1f}–{end:.1f}", "count": count})
    return {
        "count": len(cleaned),
        "unit": unit,
        "normality": normality,
        "normality_p": round(p_value, 4) if p_value is not None else None,
        "median": round(median(cleaned), 2),
        "mean": round(avg, 2),
        "std": round(deviation, 2),
        "q25": round(q25, 2),
        "q75": round(q75, 2),
        "q90": round(_quantile(cleaned, 0.9), 2),
        "outliers": sum(value < low or value > high for value in cleaned),
        "histogram": histogram,
    }


def _month_series(events: list[MroDemandEventRecord], today: date, months: int = 12) -> list[float]:
    totals = defaultdict(float)
    for event in events:
        if event.event_date <= today:
            totals[(event.event_date.year, event.event_date.month)] += (
                event.quantity * event.probability
            )
    values = []
    cursor = date(today.year, today.month, 1)
    for offset in range(months - 1, -1, -1):
        year = cursor.year
        month = cursor.month - offset
        while month <= 0:
            year -= 1
            month += 12
        values.append(round(totals[(year, month)], 3))
    return values


def _croston_sba(series: list[float], alpha: float = 0.2) -> float:
    non_zero = [(index, value) for index, value in enumerate(series) if value > 0]
    if not non_zero:
        return 0.0
    demand = non_zero[0][1]
    interval = max(1, non_zero[0][0] + 1)
    previous_index = non_zero[0][0]
    for index, value in non_zero[1:]:
        demand += alpha * (value - demand)
        gap = index - previous_index
        interval += alpha * (gap - interval)
        previous_index = index
    return (1 - alpha / 2) * demand / max(interval, 0.1)


def _attributes(profile: MroMaterialProfileRecord) -> list[dict]:
    labels = []
    if profile.aircraft_impact >= 4:
        labels.append("停场关键")
    if profile.single_source:
        labels.append("单一来源")
    if profile.long_lead or profile.lead_time_risk >= 4:
        labels.append("长交期")
    if profile.high_value or profile.value_level >= 4:
        labels.append("高价值")
    if profile.repairable or profile.repairability >= 4:
        labels.append("可修理件")
    if profile.demand_characteristic in {"intermittent", "lumpy"}:
        labels.append("间歇需求")
    if profile.compliance_risk >= 4:
        labels.append("高合规")
    if profile.substitutability <= 2:
        labels.append("低可替代")
    return [{"label": label, "color": ATTRIBUTE_COLORS[label]} for label in labels]


def profile_view(row: MroMaterialProfileRecord) -> dict:
    data = {
        key: getattr(row, key)
        for key in (
            "material_code",
            "demand_characteristic",
            "aircraft_impact",
            "supply_risk",
            "lead_time_risk",
            "value_level",
            "substitutability",
            "compliance_risk",
            "repairability",
            "single_source",
            "long_lead",
            "high_value",
            "planned",
            "non_routine",
            "repairable",
            "model_override",
            "evidence",
            "version",
        )
    }
    data["attributes"] = _attributes(row)
    return data


def _default_profile(code: str) -> MroMaterialProfileRecord:
    return MroMaterialProfileRecord(material_code=code)


def _method(profile, demand_diagnostic, future_amos: float) -> tuple[str, str]:
    if profile.model_override:
        return profile.model_override, "采用已审批的人工模型覆盖，并保留覆盖依据"
    if profile.single_source and profile.long_lead and profile.high_value and future_amos > 0:
        return (
            "amos_event_inference",
            "单一来源、长交期、高价值组合：以AMOS维修事件为主，历史非例行消耗作风险修正",
        )
    if profile.demand_characteristic in {"intermittent", "lumpy"}:
        return "croston_sba", "非零需求间隔明显，采用Croston-SBA避免普通均值高估"
    if profile.repairable and profile.value_level >= 4:
        return "repair_turnaround", "高价值可修理件：需求预测叠加修理回转在途抵扣"
    if demand_diagnostic["normality"] == "normal":
        return "normal_service_level", "样本通过正态诊断，采用均值、标准差与服务水平缓冲"
    return "robust_median", "样本非正态或不足，采用中位数与四分位距抑制异常值影响"


def analyze(db: Session, horizon_days: int, material_codes: list[str]) -> dict:
    today = datetime.now(UTC).date()
    horizon_end = today + timedelta(days=horizon_days)
    statement = select(MroMaterialProfileRecord)
    if material_codes:
        statement = statement.where(MroMaterialProfileRecord.material_code.in_(material_codes))
    profiles = list(db.scalars(statement.order_by(MroMaterialProfileRecord.material_code)))
    if not profiles:
        return {
            "generated_at": today.isoformat(),
            "horizon_days": horizon_days,
            "items": [],
            "calendar_events": [],
            "summary": {"materials": 0, "purchase_lines": 0, "purchase_quantity": 0},
        }
    codes = [row.material_code for row in profiles]
    materials = {
        row.code: row
        for row in db.scalars(select(MaterialRecord).where(MaterialRecord.code.in_(codes)))
    }
    demands = list(
        db.scalars(
            select(MroDemandEventRecord).where(MroDemandEventRecord.material_code.in_(codes))
        )
    )
    positions = list(
        db.scalars(
            select(MroSupplyPositionRecord).where(MroSupplyPositionRecord.material_code.in_(codes))
        )
    )
    lead_samples = list(
        db.scalars(select(MroLeadTimeRecord).where(MroLeadTimeRecord.material_code.in_(codes)))
    )
    by_demand, by_position, by_lead = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in demands:
        by_demand[row.material_code].append(row)
    for row in positions:
        by_position[row.material_code].append(row)
    for row in lead_samples:
        by_lead[row.material_code].append(row)

    items, events = [], []
    for profile in profiles:
        code = profile.material_code
        demand_rows = by_demand[code]
        series = _month_series(demand_rows, today)
        demand_diag = diagnostic(series, "月需求量")
        lead_diag = diagnostic([row.days for row in by_lead[code]], "天")
        future_amos = sum(
            row.quantity * row.probability
            for row in demand_rows
            if today <= row.event_date <= horizon_end and row.source_system.upper() == "AMOS"
        )
        method, rationale = _method(profile, demand_diag, future_amos)
        months = horizon_days / 30.4
        if method == "amos_event_inference":
            historical_non_routine = [
                row.quantity * row.probability
                for row in demand_rows
                if row.event_date < today and row.demand_type in {"non_routine", "aog"}
            ]
            forecast = future_amos + (
                median(historical_non_routine) if historical_non_routine else 0
            )
        elif method == "croston_sba":
            forecast = _croston_sba(series) * months
        elif method == "normal_service_level":
            forecast = (demand_diag["mean"] + 1.28 * demand_diag["std"]) * months
        else:
            robust_month = demand_diag["median"] + 0.5 * (demand_diag["q75"] - demand_diag["q25"])
            forecast = robust_month * months
        if method == "repair_turnaround":
            forecast = max(forecast, future_amos)

        inventory_breakdown = defaultdict(float)
        for position in by_position[code]:
            if not position.confirmed or (
                position.available_date and position.available_date > horizon_end
            ):
                continue
            effective = max(
                0.0, position.quantity - position.reserved_quantity - position.quarantined_quantity
            )
            inventory_breakdown[position.position_type] += effective
        available = sum(inventory_breakdown.values())
        net_quantity = max(0, math.ceil(forecast - available))
        lead_days = round(
            (lead_diag["q90"] if profile.supply_risk >= 4 else lead_diag["median"])
            or (180 if profile.long_lead else 30)
        )
        future_dates = sorted(
            row.event_date for row in demand_rows if today <= row.event_date <= horizon_end
        )
        need_date = future_dates[0] if future_dates else horizon_end
        purchase_date = max(today, need_date - timedelta(days=lead_days))
        supply_date = purchase_date + timedelta(days=lead_days)
        historical_dates = sorted({row.event_date for row in demand_rows if row.event_date < today})
        intervals = [
            (historical_dates[index] - historical_dates[index - 1]).days
            for index in range(1, len(historical_dates))
        ]
        interval_diag = diagnostic(intervals, "天")
        review_cycle = int(max(7, min(90, round(interval_diag["median"] or 30))))
        attributes = _attributes(profile)
        primary_color = attributes[0]["color"] if attributes else "#16a34a"
        material = materials.get(code)
        item = {
            "material_code": code,
            "material_name": material.name if material else code,
            "attributes": attributes,
            "forecast_method": method,
            "method_name": {
                "amos_event_inference": "AMOS维修事件推断",
                "croston_sba": "Croston-SBA间歇需求",
                "repair_turnaround": "修理回转修正",
                "normal_service_level": "正态服务水平",
                "robust_median": "稳健中位数",
            }.get(method, method),
            "rationale": rationale,
            "forecast_quantity": round(forecast, 2),
            "available_quantity": round(available, 2),
            "inventory_breakdown": dict(inventory_breakdown),
            "purchase_quantity": net_quantity,
            "purchase_date": purchase_date.isoformat() if net_quantity else None,
            "supply_date": supply_date.isoformat() if net_quantity else None,
            "lead_days": lead_days,
            "review_cycle_days": review_cycle,
            "diagnostics": {
                "demand": demand_diag,
                "lead_time": lead_diag,
                "demand_interval": interval_diag,
            },
        }
        items.append(item)
        if net_quantity:
            base = {
                "material_code": code,
                "material_name": item["material_name"],
                "quantity": net_quantity,
                "attributes": attributes,
                "color": primary_color,
                "method_name": item["method_name"],
            }
            events.extend(
                [
                    base
                    | {
                        "id": f"purchase-{code}",
                        "date": item["purchase_date"],
                        "plan_type": "purchase",
                    },
                    base
                    | {"id": f"supply-{code}", "date": item["supply_date"], "plan_type": "supply"},
                ]
            )
    return {
        "generated_at": today.isoformat(),
        "horizon_days": horizon_days,
        "items": items,
        "calendar_events": events,
        "legend": [{"label": label, "color": color} for label, color in ATTRIBUTE_COLORS.items()],
        "summary": {
            "materials": len(items),
            "purchase_lines": sum(item["purchase_quantity"] > 0 for item in items),
            "purchase_quantity": sum(item["purchase_quantity"] for item in items),
            "amos_models": sum(item["forecast_method"] == "amos_event_inference" for item in items),
            "non_normal_datasets": sum(
                item["diagnostics"]["demand"]["normality"] == "non_normal" for item in items
            ),
        },
    }


def save_run(db: Session, result: dict, material_codes: list[str], actor: str) -> str:
    row = MroPlanningRunRecord(
        horizon_days=result["horizon_days"],
        material_codes_json=json.dumps(material_codes, ensure_ascii=False),
        result_json=json.dumps(result, ensure_ascii=False),
        created_by=actor,
    )
    db.add(row)
    db.commit()
    return row.id

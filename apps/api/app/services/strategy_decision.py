"""Auditable material-level strategy comparisons; no hidden LLM scoring."""

from datetime import UTC, date, datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Candidate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=120)
    source: Literal[
        "oem", "domestic", "alternative", "remanufactured", "shared_stock", "platform"
    ] = "oem"
    supply_mode: Literal["standard", "vmi", "consignment", "framework"] = "standard"
    unit_price: float | None = Field(None, ge=0)
    fees: float | None = Field(None, ge=0)
    holding_cost: float | None = Field(None, ge=0)
    validation_cost: float | None = Field(None, ge=0)
    arrival: date | None = None
    validated: bool | None = None
    reliability: float | None = Field(None, ge=0, le=100)
    agreement_reviewed: bool = False
    supplier_id: str = Field("", max_length=64)
    supplier_name: str = Field("", max_length=200)
    capability_status: Literal["matched", "unmatched", "unverified", "not_required"] = (
        "not_required"
    )
    supplier_aog_247: bool = False
    supplier_response_hours: int | None = Field(None, ge=1, le=720)
    evidence: str = Field("", max_length=2000)
    offer_type: Literal["purchase", "exchange", "loan", "repair"] = "purchase"
    condition: Literal["NEW", "OH", "SV", "AR", "USM"] = "NEW"
    certificate_status: Literal["verified", "missing", "not_required"] = "not_required"
    trace_status: Literal["complete", "incomplete", "not_required"] = "not_required"
    applicability_status: Literal["verified", "not_verified", "not_applicable"] = "not_applicable"
    remaining_life_percent: float | None = Field(None, ge=0, le=100)
    core_charge: float = Field(0, ge=0)
    core_credit: float = Field(0, ge=0)
    repair_cost: float = Field(0, ge=0)
    return_penalty: float = Field(0, ge=0)
    available_quantity: float | None = Field(None, ge=0)
    minimum_order_quantity: float = Field(1, gt=0)
    package_quantity: float = Field(1, gt=0)
    repair_tat_days: int | None = Field(None, ge=0, le=3650)
    repair_success_rate: float | None = Field(None, ge=0, le=100)
    ber_probability: float | None = Field(None, ge=0, le=100)
    shelf_life_required: bool = False
    shelf_life_remaining_days: int | None = Field(None, ge=0, le=36500)


class DecisionInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    quantity: float | None = Field(None, gt=0)
    required_date: date | None = None
    budget: float | None = Field(None, gt=0)
    baseline_price: float | None = Field(None, gt=0)
    premium_limit: float | None = Field(None, ge=0, le=500)
    risk_limit: float | None = Field(None, ge=0, le=100)
    downtime_per_day: float | None = Field(None, ge=0)
    annual_issues: int | None = Field(None, ge=0)
    critical: bool | None = None
    reserve: float | None = Field(None, ge=0)
    available: float | None = Field(None, ge=0)
    inventory_confirmed: bool = False
    owner: str = Field("", max_length=100)
    evidence: str = Field("", max_length=2000)
    simulated: bool = False
    demand_type: Literal["planned", "non_routine", "aog"] = "planned"
    required_within_hours: int | None = Field(None, ge=1, le=8760)
    candidates: list[Candidate] = Field(default_factory=list, max_length=20)


def analyze(p: DecisionInput):
    def record_issue(candidate_name, candidate_issues, kind, detail, solution):
        candidate_issues.append(kind)
        conflicts.append(
            {
                "candidate": candidate_name,
                "type": kind,
                "detail": detail,
                "solution": solution,
                "owner": p.owner or "待指定负责人",
                "status": "待处理",
            }
        )

    labels = {
        "quantity": "本次需求数量",
        "required_date": "必要到货日期",
        "budget": "本次预算",
        "baseline_price": "同口径价格基准",
        "premium_limit": "溢价授权上限",
        "risk_limit": "风险容忍阈值",
        "downtime_per_day": "每日停机损失估计",
        "annual_issues": "年度领用次数",
        "critical": "设备是否关键",
        "reserve": "必要储备量",
        "available": "实际可用库存",
    }
    missing = [
        {"field": k, "label": v, "action": "在需求与约束页补录，并填写数据依据"}
        for k, v in labels.items()
        if getattr(p, k) is None
    ]
    if not p.inventory_confirmed:
        missing.append(
            {
                "field": "inventory_confirmed",
                "label": "库存口径确认",
                "action": "扣除预留、隔离和不可调拨数量后确认可用库存",
            }
        )
    if not p.evidence.strip():
        missing.append(
            {
                "field": "evidence",
                "label": "需求数据来源及统计期间",
                "action": "填写来源单据、统计期间和复核依据",
            }
        )
    if not p.candidates:
        missing.append(
            {
                "field": "candidates",
                "label": "候选采购方案",
                "action": "添加至少一个具备报价和到货承诺的候选方案",
            }
        )
    if p.demand_type == "aog" and p.required_within_hours is None:
        missing.append(
            {
                "field": "required_within_hours",
                "label": "AOG要求响应小时",
                "action": "填写停场需求允许的最长供应响应时间",
            }
        )
    rows = []
    conflicts = []
    net = (
        max(0, p.quantity + p.reserve - p.available)
        if all(v is not None for v in [p.quantity, p.reserve, p.available])
        else None
    )
    for index, c in enumerate(p.candidates):
        cmissing = [
            k
            for k in [
                "unit_price",
                "fees",
                "holding_cost",
                "validation_cost",
                "arrival",
                "validated",
                "reliability",
            ]
            if getattr(c, k) is None
        ]
        if not c.evidence.strip():
            cmissing.append("evidence")
        issues = []

        if cmissing:
            record_issue(
                c.name,
                issues,
                "数据缺失",
                "缺少 " + ", ".join(cmissing),
                "补齐报价、费用、承诺交期、技术状态、履约及时率和来源依据",
            )
        days = max(0, (c.arrival - p.required_date).days) if c.arrival and p.required_date else None
        if days:
            record_issue(
                c.name,
                issues,
                "交期冲突",
                f"预计到货超过必要日期 {days} 天",
                "取得加急承诺，核实借调或拆分需求后重新比较",
            )
        if c.validated is False:
            record_issue(
                c.name,
                issues,
                "技术约束",
                "技术验证尚未放行",
                "由技术负责人完成适配验证并记录放行依据",
            )
        if c.capability_status == "unmatched":
            record_issue(
                c.name,
                issues,
                "供应能力不匹配",
                "未选择供应商，或供应商没有对应的航空MRO能力档案",
                "选择具备相应PN/OEM/维修能力的供应商，完成能力范围维护后重新分析",
            )
        if c.capability_status == "unverified":
            record_issue(
                c.name,
                issues,
                "供应商关系未核实",
                "该供应渠道仅为公开资料参考，尚未完成企业准入与能力核验",
                "完成供应商准入、资质审查和能力范围确认；核实前不得进入定标推荐",
            )
        if p.demand_type == "aog" and not c.supplier_aog_247:
            record_issue(
                c.name,
                issues,
                "AOG能力不足",
                "供应商能力档案未确认24/7 AOG服务",
                "切换至已准入的AOG渠道，或完成紧急授权及备用方案审批",
            )
        if (
            p.demand_type == "aog"
            and p.required_within_hours is not None
            and c.supplier_response_hours is not None
            and c.supplier_response_hours > p.required_within_hours
        ):
            record_issue(
                c.name,
                issues,
                "响应时限冲突",
                f"供应商响应需{c.supplier_response_hours}小时，超过要求的{p.required_within_hours}小时",
                "改选更快渠道，取得可验证的加急承诺，或升级AOG授权",
            )
        if c.certificate_status == "missing":
            record_issue(
                c.name,
                issues,
                "适航证书缺失",
                "未取得或未核验要求的适航放行文件",
                "补充8130-3、EASA Form 1、AAC-038或物料档案指定文件并由质量人员核验",
            )
        if c.trace_status == "incomplete":
            record_issue(
                c.name,
                issues,
                "追溯链不完整",
                "批次、序列号、拆换或维修记录不足",
                "补齐制造/运营/维修来源及连续可追溯文件",
            )
        if c.applicability_status == "not_verified":
            record_issue(
                c.name,
                issues,
                "适用性未确认",
                "尚未确认PN、构型及机型/发动机适配",
                "由工程人员完成IPC/AMM/CMM或批准替代关系核验",
            )
        if c.remaining_life_percent is not None and c.remaining_life_percent < 30:
            record_issue(
                c.name,
                issues,
                "剩余寿命不足",
                f"剩余寿命仅 {c.remaining_life_percent}%",
                "提高最低剩余寿命要求或取得工程与成本联合批准",
            )
        order_quantity = None
        if net is not None:
            order_quantity = max(net, c.minimum_order_quantity)
            order_quantity = ceil(order_quantity / c.package_quantity) * c.package_quantity
        if c.capability_status != "not_required" and c.available_quantity is None:
            record_issue(
                c.name,
                issues,
                "可获得量未确认",
                "供应商现货或可修能力数量尚未确认",
                "取得带时间戳的库存/产能证据并填写可获得数量",
            )
        elif (
            c.available_quantity is not None
            and order_quantity is not None
            and c.available_quantity < order_quantity
        ):
            record_issue(
                c.name,
                issues,
                "可获得量不足",
                f"可获得{c.available_quantity}，按MOQ/包装需下单{order_quantity}",
                "拆单组合供应、核实共享库存，或调整MOQ与包装依据",
            )
        if c.shelf_life_required and c.shelf_life_remaining_days is None:
            record_issue(
                c.name,
                issues,
                "货架寿命未确认",
                "寿控物料未提供交付时的剩余货架寿命",
                "补充制造/失效日期及收货时剩余寿命证据",
            )
        if c.offer_type == "repair":
            if (
                c.repair_tat_days is None
                or c.repair_success_rate is None
                or c.ber_probability is None
            ):
                record_issue(
                    c.name,
                    issues,
                    "维修参数缺失",
                    "送修方案缺少TAT、修复成功率或BER概率",
                    "基于同PN历史维修记录补齐参数及统计期间",
                )
            available_days = (
                max(0, (p.required_date - datetime.now(UTC).date()).days)
                if p.required_date
                else None
            )
            if (
                c.repair_tat_days is not None
                and available_days is not None
                and c.repair_tat_days > available_days
            ):
                record_issue(
                    c.name,
                    issues,
                    "维修周转冲突",
                    f"维修TAT {c.repair_tat_days}天，超过需求窗口{available_days}天",
                    "采用Loan/Exchange过渡，或取得维修加急承诺",
                )
        ber_expected_loss = (
            c.ber_probability / 100 * p.baseline_price * net
            if c.offer_type in ["repair", "exchange"]
            and c.ber_probability is not None
            and p.baseline_price is not None
            and net is not None
            else 0
        )
        parts = {
            "采购货值": c.unit_price * order_quantity
            if c.unit_price is not None and order_quantity is not None
            else None,
            "运输及加急": c.fees,
            "持有成本": c.holding_cost,
            "验证改造": c.validation_cost,
            "维修成本": c.repair_cost,
            "Core占用": max(0, c.core_charge - c.core_credit),
            "旧件归还风险": c.return_penalty,
            "BER预期损失": round(ber_expected_loss, 2),
            "延期损失": days * p.downtime_per_day
            if days is not None and p.downtime_per_day is not None
            else None,
        }
        total = (
            round(sum(parts.values()), 2) if all(v is not None for v in parts.values()) else None
        )
        cash = (
            round(sum(v for k, v in parts.items() if k != "延期损失"), 2)
            if all(parts[k] is not None for k in parts if k != "延期损失")
            else None
        )
        premium = (
            round((c.unit_price / p.baseline_price - 1) * 100, 2)
            if c.unit_price is not None and p.baseline_price
            else None
        )
        if cash is not None and p.budget is not None and cash > p.budget:
            record_issue(
                c.name,
                issues,
                "预算冲突",
                f"支出 {cash:.2f} 元，超预算 {cash - p.budget:.2f} 元",
                "议价、修改方案，或取得预算调整批准后更新预算",
            )
        if premium is not None and p.premium_limit is not None and premium > p.premium_limit:
            record_issue(
                c.name,
                issues,
                "溢价授权",
                f"单价溢价 {premium}% 超授权 {p.premium_limit}%",
                "确认价格口径，重新议价或完成超限授权",
            )
        risk = round(100 - c.reliability, 2) if c.reliability is not None else None
        if risk is not None and p.risk_limit is not None and risk > p.risk_limit:
            record_issue(
                c.name,
                issues,
                "供货风险",
                f"历史未准时率 {risk}% 超阈值 {p.risk_limit}%",
                "增加交付保障、备选供货，并补充可核实的履约证据",
            )
        if c.supply_mode in ["vmi", "consignment"] and not c.agreement_reviewed:
            record_issue(
                c.name,
                issues,
                "供货协议待核验",
                "需确认库存所有权、补货责任和结算触发点",
                "在供应商协议中完成条款评审；当前方案待评审，不视作已可执行",
            )
        eligible = not missing and not issues
        rows.append(
            {
                "id": index,
                "name": c.name,
                "source": c.source,
                "supply_mode": c.supply_mode,
                "supplier_id": c.supplier_id,
                "supplier_name": c.supplier_name,
                "capability_status": c.capability_status,
                "supplier_aog_247": c.supplier_aog_247,
                "supplier_response_hours": c.supplier_response_hours,
                "offer_type": c.offer_type,
                "condition": c.condition,
                "parts": parts,
                "cost": total,
                "cash": cash,
                "delay_days": days,
                "risk": risk,
                "premium": premium,
                "order_quantity": order_quantity,
                "available_quantity": c.available_quantity,
                "eligible": eligible,
                "issues": issues,
                "arrival": c.arrival,
                "evidence": c.evidence,
            }
        )
    longtail = p.annual_issues is not None and p.annual_issues <= 2
    if longtail and p.critical:
        conflicts.append(
            {
                "candidate": "物料整体",
                "type": "长尾与保障",
                "detail": "低频领用但设备关键，不能仅按低频取消储备",
                "solution": "保留经维修评审的必要储备，核实共享库存可达时间",
                "owner": p.owner or "维修负责人",
                "status": "待评审",
            }
        )
    eligible = sorted([r for r in rows if r["eligible"]], key=lambda r: r["cost"])
    recommendation = eligible[0]["name"] if eligible else None
    if net == 0 and not missing:
        recommendation = None
    return {
        "missing": missing,
        "net_quantity": net,
        "candidates": rows,
        "conflicts": conflicts,
        "recommendation": recommendation,
        "status": "需补充数据"
        if missing
        else "库存覆盖需求，请复核后暂停新增采购"
        if net == 0
        else "存在可行方案"
        if recommendation
        else "暂无满足全部约束的方案",
        "conclusion": f"在当前候选方案中，{recommendation} 满足已建模约束且综合成本最低。"
        if recommendation
        else "已确认库存覆盖需求和必要储备，无需新增采购。"
        if net == 0 and not missing
        else "请先处理缺失数据及冲突，再重新计算。",
        "process": [
            {
                "name": "输入完整性",
                "passed": len(missing) == 0,
                "detail": f"{len(missing)} 项待补充",
            },
            {
                "name": "适航硬门槛",
                "passed": any(
                    not any(
                        x in r["issues"]
                        for x in [
                            "供应能力不匹配",
                            "供应商关系未核实",
                            "适航证书缺失",
                            "追溯链不完整",
                            "适用性未确认",
                            "剩余寿命不足",
                            "AOG能力不足",
                            "响应时限冲突",
                            "可获得量未确认",
                            "可获得量不足",
                            "货架寿命未确认",
                            "维修参数缺失",
                            "维修周转冲突",
                        ]
                    )
                    for r in rows
                ),
                "detail": "供应能力、AOG响应、可获得量、证书、追溯、适用性及寿命不能由低价补偿",
            },
            {
                "name": "寻源与价格",
                "passed": any(r["cost"] is not None for r in rows),
                "detail": "统一NEW/USM/Exchange/Loan/Repair费用口径",
            },
            {
                "name": "紧急采购",
                "passed": any(r["delay_days"] == 0 for r in rows),
                "detail": "逐个比较到货承诺与必要日期",
            },
            {
                "name": "差异化供应",
                "passed": any(r["supply_mode"] in ["standard", "framework"] for r in rows),
                "detail": "VMI/寄售必须补充协议评审",
            },
            {
                "name": "长尾治理",
                "passed": p.annual_issues is not None and p.critical is not None,
                "detail": "低频阈值≤2次/年（当前规则）；关键性单独约束储备",
            },
            {
                "name": "联合筛选",
                "passed": bool(eligible),
                "detail": f"{len(rows)}个候选 → {len(eligible)}个可行",
            },
        ],
        "rules": {
            "version": "aviation-strategy-decision-v2",
            "currency": "CNY",
            "quantity": "净采购量=max(0,需求+必要储备−已确认可用库存)",
            "hard_gate": "供应商能力准入、适航证书、连续追溯、适用性和最低剩余寿命任一不通过即淘汰，不能用低价抵消",
            "order_quantity": "下单量=max(净需求,MOQ)，再按包装量向上取整；供应商可获得量不足则淘汰",
            "cost": "综合成本=下单货值+运输加急+持有+验证改造+维修+Core占用+旧件归还风险+BER预期损失+延期停场损失",
            "repair": "送修须验证TAT、历史修复成功率与BER概率；BER预期损失=BER概率×基准单价×净需求",
            "risk": "风险轴=100−历史交付及时率；适航、技术和交期另作硬约束",
            "selection": "先过硬门槛和业务约束，再在可行候选中按综合成本排序",
            "limits": "VMI/寄售、共享库存和Exchange旧件条款仍须人工评审。",
        },
        "simulated": p.simulated,
    }

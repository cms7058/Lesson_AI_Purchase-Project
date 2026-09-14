"""Explicit scenario estimates, not fitted coefficients or guaranteed outcomes."""
def analyze(plan):
    # Transparent starter policy. Criticality is a constraint, never a cost weight.
    max_risk = {'V':plan.risk_limit_v, 'E':plan.risk_limit_e, 'D':plan.risk_limit_d}[plan.ved]
    net = max(0, plan.demand + plan.reserve - plan.available - plan.confirmed_inbound)
    rows = []
    for s in plan.scenarios:
        parts = {'采购支出':round(s.quantity*s.unit_price,2),'订货运输':s.fees,'持有成本':s.holding,'质量损失':s.quality_loss,'停机损失':s.downtime_loss,'应急增量成本':s.emergency_loss,'呆滞淘汰损失':s.obsolescence_loss}
        total = round(sum(parts.values()),2)
        reasons = []
        if s.quantity < net:
            reasons.append('采购数量不能覆盖需求及储备')
        if s.quantity and s.arrival > plan.required_date:
            reasons.append('到货晚于需求日期')
        if s.risk_percent > max_risk:
            reasons.append(f'{plan.ved}类缺货风险超过本计划配置上限{max_risk}%')
        if total > plan.budget:
            reasons.append('计划TOC超预算')
        rows.append({'name':s.name,'quantity':s.quantity,'arrival':s.arrival.isoformat(),'toc':total,'parts':parts,'feasible':not reasons,'reasons':reasons,'evidence':s.evidence})
    feasible = [r for r in rows if r['feasible']]
    best = min(feasible,key=lambda r:r['toc']) if feasible else None
    return {'net_demand':net,'max_risk_percent':max_risk,'recommended':best['name'] if best else None,'scenarios':rows,'policy_version':'scenario-review-v1','warnings':[
        '当前为人工参数驱动的方案测算，不是已训练回归模型。V/E/D风险上限由本计划显式配置，不代表行业标准。',
        'ABC用于价值关注、FSN用于流动性风险提示，本阶段尚未自动生成不同批量和采购周期。',
        '所有费用须为同币种同规划期间、不重叠的预期成本；持有成本及期末剩余价值需按一致口径估计。',
        '外部可用库存与确认在途均须在需求日前有效；本系统不进行库存记账。',
        {'A':'A类：重点复核资金占用与供应方式。','B':'B类：平衡批量与保障成本。','C':'C类：重点检查订货频次和事务成本。'}[plan.abc],
        {'F':'F类：复核高频消耗及交期波动。','S':'S类：复核间歇需求与过量风险。','N':'N类：复核淘汰风险；关键事故件不能仅因低频取消储备。'}[plan.fsn]]}

"""Auditable material-level strategy comparisons; no hidden LLM scoring."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Candidate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=120)
    source: Literal['oem','domestic','alternative','remanufactured','shared_stock','platform'] = 'oem'
    supply_mode: Literal['standard','vmi','consignment','framework'] = 'standard'
    unit_price: float | None = Field(None, ge=0)
    fees: float | None = Field(None, ge=0)
    holding_cost: float | None = Field(None, ge=0)
    validation_cost: float | None = Field(None, ge=0)
    arrival: date | None = None
    validated: bool | None = None
    reliability: float | None = Field(None, ge=0, le=100)
    agreement_reviewed: bool = False
    evidence: str = Field('', max_length=2000)


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
    owner: str = Field('', max_length=100)
    evidence: str = Field('', max_length=2000)
    simulated: bool = False
    candidates: list[Candidate] = Field(default_factory=list, max_length=20)


def analyze(p: DecisionInput):
    labels = {'quantity':'本次需求数量','required_date':'必要到货日期','budget':'本次预算','baseline_price':'同口径价格基准','premium_limit':'溢价授权上限','risk_limit':'风险容忍阈值','downtime_per_day':'每日停机损失估计','annual_issues':'年度领用次数','critical':'设备是否关键','reserve':'必要储备量','available':'实际可用库存'}
    missing = [{'field':k,'label':v,'action':'在需求与约束页补录，并填写数据依据'} for k,v in labels.items() if getattr(p,k) is None]
    if not p.inventory_confirmed: missing.append({'field':'inventory_confirmed','label':'库存口径确认','action':'扣除预留、隔离和不可调拨数量后确认可用库存'})
    if not p.evidence.strip(): missing.append({'field':'evidence','label':'需求数据来源及统计期间','action':'填写来源单据、统计期间和复核依据'})
    if not p.candidates: missing.append({'field':'candidates','label':'候选采购方案','action':'添加至少一个具备报价和到货承诺的候选方案'})
    rows=[]; conflicts=[]
    net = max(0,p.quantity+p.reserve-p.available) if all(v is not None for v in [p.quantity,p.reserve,p.available]) else None
    for index,c in enumerate(p.candidates):
        cmissing=[k for k in ['unit_price','fees','holding_cost','validation_cost','arrival','validated','reliability'] if getattr(c,k) is None]
        if not c.evidence.strip(): cmissing.append('evidence')
        issues=[]
        def issue(kind,detail,solution):
            issues.append(kind); conflicts.append({'candidate':c.name,'type':kind,'detail':detail,'solution':solution,'owner':p.owner or '待指定负责人','status':'待处理'})
        if cmissing: issue('数据缺失','缺少 '+', '.join(cmissing),'补齐报价、费用、承诺交期、技术状态、履约及时率和来源依据')
        days=max(0,(c.arrival-p.required_date).days) if c.arrival and p.required_date else None
        if days: issue('交期冲突',f'预计到货超过必要日期 {days} 天','取得加急承诺，核实借调或拆分需求后重新比较')
        if c.validated is False: issue('技术约束','技术验证尚未放行','由技术负责人完成适配验证并记录放行依据')
        parts={'采购货值':c.unit_price*net if c.unit_price is not None and net is not None else None,'运输及加急':c.fees,'持有成本':c.holding_cost,'验证改造':c.validation_cost,'延期损失':days*p.downtime_per_day if days is not None and p.downtime_per_day is not None else None}
        total=round(sum(parts.values()),2) if all(v is not None for v in parts.values()) else None
        cash=round(sum(v for k,v in parts.items() if k!='延期损失'),2) if all(parts[k] is not None for k in parts if k!='延期损失') else None
        premium=round((c.unit_price/p.baseline_price-1)*100,2) if c.unit_price is not None and p.baseline_price else None
        if cash is not None and p.budget is not None and cash>p.budget: issue('预算冲突',f'支出 {cash:.2f} 元，超预算 {cash-p.budget:.2f} 元','议价、修改方案，或取得预算调整批准后更新预算')
        if premium is not None and p.premium_limit is not None and premium>p.premium_limit: issue('溢价授权',f'单价溢价 {premium}% 超授权 {p.premium_limit}%','确认价格口径，重新议价或完成超限授权')
        risk=round(100-c.reliability,2) if c.reliability is not None else None
        if risk is not None and p.risk_limit is not None and risk>p.risk_limit: issue('供货风险',f'历史未准时率 {risk}% 超阈值 {p.risk_limit}%','增加交付保障、备选供货，并补充可核实的履约证据')
        if c.supply_mode in ['vmi','consignment'] and not c.agreement_reviewed:
            issue('供货协议待核验','需确认库存所有权、补货责任和结算触发点','在供应商协议中完成条款评审；当前方案待评审，不视作已可执行')
        eligible=not missing and not issues
        rows.append({'id':index,'name':c.name,'source':c.source,'supply_mode':c.supply_mode,'parts':parts,'cost':total,'cash':cash,'delay_days':days,'risk':risk,'premium':premium,'eligible':eligible,'issues':issues,'arrival':c.arrival,'evidence':c.evidence})
    longtail = p.annual_issues is not None and p.annual_issues<=2
    if longtail and p.critical:
        conflicts.append({'candidate':'物料整体','type':'长尾与保障','detail':'低频领用但设备关键，不能仅按低频取消储备','solution':'保留经维修评审的必要储备，核实共享库存可达时间','owner':p.owner or '维修负责人','status':'待评审'})
    eligible=sorted([r for r in rows if r['eligible']],key=lambda r:r['cost'])
    recommendation=eligible[0]['name'] if eligible else None
    if net == 0 and not missing: recommendation=None
    return {'missing':missing,'net_quantity':net,'candidates':rows,'conflicts':conflicts,'recommendation':recommendation,
        'status':'需补充数据' if missing else '库存覆盖需求，请复核后暂停新增采购' if net==0 else '存在可行方案' if recommendation else '暂无满足全部约束的方案',
        'conclusion':f'在当前候选方案中，{recommendation} 满足已建模约束且综合成本最低。' if recommendation else '已确认库存覆盖需求和必要储备，无需新增采购。' if net==0 and not missing else '请先处理缺失数据及冲突，再重新计算。',
        'process':[{'name':'输入完整性','passed':len(missing)==0,'detail':f'{len(missing)} 项待补充'}, {'name':'寻源与价格','passed':any(r['cost'] is not None for r in rows),'detail':'同币种、同数量计算货值及各项增量费用'}, {'name':'紧急采购','passed':any(r['delay_days']==0 for r in rows),'detail':'逐个比较到货承诺与必要日期'}, {'name':'差异化供应','passed':any(r['supply_mode'] in ['standard','framework'] for r in rows),'detail':'VMI/寄售必须补充协议评审'}, {'name':'长尾治理','passed':p.annual_issues is not None and p.critical is not None,'detail':'低频阈值≤2次/年（当前规则）；关键性单独约束储备'}, {'name':'联合筛选','passed':bool(eligible),'detail':f'{len(rows)}个候选 → {len(eligible)}个可行'}],
        'rules':{'version':'strategy-decision-v1','currency':'CNY','quantity':'净采购量=max(0,需求+必要储备−已确认可用库存)','cost':'综合成本=货值+运输加急+持有+验证改造+延期天数×每日停机损失','risk':'风险轴=100−历史交付及时率；技术验证和交期另外作为硬约束','selection':'先检查约束，再在可行候选中按综合成本从低到高选择；不是全市场最优','limits':'当前比较完整供货候选方案，不自动拆单；VMI/寄售条款、共享供货承诺须人工评审。'},'simulated':p.simulated}

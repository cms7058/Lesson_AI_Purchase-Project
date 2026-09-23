<template>
  <section class="risk-process" aria-label="TOC与DOE分析过程">
    <h2>TOC 与 DOE · 要素分析过程</h2>
    <el-alert title="教学模拟：展示分析过程，不代表已完成生产试验或历史回归验证。" description="沿用当前设备的指标与数量示例；成本、因素扰动及响应模型为显式假设。TOC 在此沿用系统综合成本口径；模拟分析不覆盖上方原有采购建议。" type="info" :closable="false" show-icon />
    <h3>一、TOC 综合成本分析</h3>
    <div class="process-flow"><span>① 对齐设备与数量口径</span><span>② 归一化风险输入</span><span>③ 枚举采购数量</span><span>④ 比较成本与缺件损失</span></div>
    <div class="cost-inputs">
      <label>采购单价（元/件）<el-input-number v-model="costs.purchase" :min="1" :max="100000" :precision="2" size="small" /></label>
      <label>期末余量持有成本（元/件/周期）<el-input-number v-model="costs.holding" :min="0" :max="100000" :precision="2" size="small" /></label>
      <label>缺件损失（元/件）<el-input-number v-model="costs.shortage" :min="1" :max="1000000" :precision="2" size="small" /></label>
    </div>
    <p class="analysis-copy">同一补库周期：TOC = 采购金额 + 期望余量持有成本 + 期望缺件损失。需求按 80% / 100% / 120% 三种情景，概率为 25% / 50% / 25%；已有库存视为沉没投入。</p>
    <div class="process-charts">
      <el-card shadow="never"><div slot="header"><strong>TOC：数量—成本曲线</strong></div><analysis-chart :option="costChart" /><p>遍历整数采购量，标记当前假设下的最低成本点；它不是生产最优库存的验证结论。</p></el-card>
      <el-card shadow="never"><div slot="header"><strong>TOC：各要素低 / 高水平成本</strong></div><analysis-chart :option="sensitivityChart" /><p>采购量固定为原示例 {{ analysis.currentQuantity }} 件，其他指标固定当前值；逐项改变一个因素，观察综合成本方向。</p></el-card>
    </div>
    <div class="result-summary" data-testid="toc-summary">模型建议量 {{ analysis.current.quantity }} 件；当前量模拟成本 {{ money(analysis.currentCost.total) }} 元。枚举最低点 {{ analysis.best.quantity }} 件 / {{ money(analysis.best.total) }} 元，其中采购 {{ money(analysis.best.purchase) }}、持有 {{ money(analysis.best.holding) }}、缺件损失 {{ money(analysis.best.loss) }} 元。</div>
    <h3>二、DOE 六要素全因子模拟</h3>
    <div class="process-flow"><span>① 定义六因素与水平</span><span>② 生成 2⁶ = 64 组组合</span><span>③ 计算数量响应</span><span>④ 分析主效应与交互</span><span>⑤ 真实试验与独立验证</span></div>
    <el-table :data="analysis.factors" size="small" border>
      <el-table-column prop="name" label="因素" min-width="100" />
      <el-table-column label="当前值"><template slot-scope="s">{{ number(s.row.current) }} {{ s.row.unit }}</template></el-table-column>
      <el-table-column label="低水平（−10%）"><template slot-scope="s">{{ number(s.row.low) }} {{ s.row.unit }}</template></el-table-column>
      <el-table-column label="高水平（+10%）"><template slot-scope="s">{{ number(s.row.high) }} {{ s.row.unit }}</template></el-table-column>
      <el-table-column label="设备风险权重"><template slot-scope="s">{{ s.row.weight === null ? '单独乘数' : (s.row.weight * 100).toFixed(2) + '%' }}</template></el-table-column>
    </el-table>
    <p class="analysis-copy">OEE 高水平上限为 100%。OEE、MTBF、Cp、Cpk 增加降低风险，MTTR 增加提升风险；订单负荷作为独立乘数。权重仅由现有风险贡献演示分数归一化，不是拟合系数。指标相互关联，生产试验应选用可控工艺参数，不能将任意组合视为可执行操作。</p>
    <div class="process-charts">
      <el-card shadow="never"><div slot="header"><strong>DOE：64 组设计矩阵</strong></div><analysis-chart :option="matrixChart" /><p>颜色区分低 / 高水平；拖动底部滑块查看全部组合。编号为设计顺序，真实试验需随机化并安排重复。</p></el-card>
      <el-card shadow="never"><div slot="header"><strong>DOE：主效应（高 − 低）</strong></div><analysis-chart :option="effectsChart" /><p>分别对 32 组高水平、32 组低水平的数量响应求均值并作差。正值增加建议数量，负值降低建议数量。</p></el-card>
      <el-card shadow="never"><div slot="header"><strong>DOE：OEE × 订单负荷交互</strong></div><analysis-chart :option="interactionChart" /><p>每点为其余四因素 16 组组合的平均数量；两条线不平行表示该模拟模型中的交互响应。</p></el-card>
      <el-card shadow="never"><div slot="header"><strong>DOE：64 组数量响应</strong></div><analysis-chart :option="responseChart" /><p>响应来自确定性模型，未加入实测噪声；不计算虚假的显著性、置信区间或实验通过结论。</p></el-card>
    </div>
    <el-collapse><el-collapse-item title="查看响应公式、全部组合与计算明细" name="details">
      <p>R₀ = 1 + 风险调整 / 基础需求 = {{ number(analysis.risk) }}；L₀ = 1 + 订单增量 / (基础需求 × R₀) = {{ number(analysis.load) }}。</p>
      <p>R = max(1, R₀ + Σ wⱼ × sⱼ × (xⱼ / 当前值ⱼ − 1))；MTTR 的 s = +1，其余四项 s = −1。需求 D = 基础需求 × R × 订单负荷；采购量 Q = max(0, 向上取整(D − 库存))。</p>
      <p>此处基础需求 {{ analysis.base }} 件、库存 {{ analysis.stock }} 件来自设备级数量示例，不能与上方各物料采购明细相加或视为同一批采购订单。</p>
      <el-table :data="analysis.runs" height="350" size="small" border><el-table-column prop="id" label="组合" width="65" /><el-table-column v-for="(factor,i) in analysis.factors" :key="factor.name" :label="factor.name" min-width="100"><template slot-scope="s">{{ number(s.row.inputs[i]) }} ({{ s.row.levels[i] ? '高' : '低' }})</template></el-table-column><el-table-column prop="quantity" label="数量响应(件)" width="115" /></el-table>
    </el-collapse-item></el-collapse>
    <div class="result-summary" data-testid="doe-summary">模拟结论：当前扰动范围内，数量主效应绝对值最大的是 {{ strongest.name }}（高 − 低 = {{ number(strongest.effect) }} 件）。下一步采集真实故障、消耗与费用，安排随机化重复试验，再用独立周期验证后更新补库策略。</div>
  </section>
</template>
<script>
import AnalysisChart from './AnalysisChart.vue';
import { analyzeSpareRisk } from '../utils/spareRiskAnalysis.mjs';
const round = value => Number(value.toFixed(2));
const chart = (labels, series, unit) => ({ tooltip: { trigger: 'axis' }, legend: { bottom: 0 }, grid: { left: 75, right: 35, top: 45, bottom: 70 }, xAxis: { type: 'category', data: labels }, yAxis: { type: 'value', name: unit }, series });
export default {
  components: { AnalysisChart }, props: { equipment: { type: Object, required: true } },
  data: () => ({ costs: { purchase: 200, holding: 20, shortage: 1500 } }),
  computed: {
    analysis() { return analyzeSpareRisk(this.equipment, this.costs); },
    strongest() { return this.analysis.effects.reduce((a, b) => Math.abs(b.effect) > Math.abs(a.effect) ? b : a); },
    costChart() { const a = this.analysis; return chart(a.curve.map(r => r.quantity), ['purchase', 'holding', 'loss', 'total'].map((key, i) => ({ name: ['采购', '持有', '缺件损失', '综合成本'][i], type: 'line', showSymbol: false, data: a.curve.map(r => round(r[key])), ...(key === 'total' ? { markPoint: { data: [{ name: '模拟最低点', coord: [a.best.quantity, round(a.best.total)], value: a.best.quantity + '件' }] } } : {}) })), '元 / 周期'); },
    sensitivityChart() { return chart(this.analysis.effects.map(r => r.name), ['lowCost', 'highCost'].map((key, i) => ({ name: ['低水平成本', '高水平成本'][i], type: 'bar', data: this.analysis.effects.map(r => round(r[key])) })), '元 / 周期'); },
    effectsChart() { return chart(this.analysis.effects.map(r => r.name), [{ name: '高 − 低', type: 'bar', label: { show: true, position: 'top' }, data: this.analysis.effects.map(r => ({ value: round(r.effect), itemStyle: { color: r.effect >= 0 ? '#e89343' : '#19a974' } })) }], '数量变化(件)'); },
    matrixChart() { return { tooltip: { formatter: p => `组合 ${p.value[0] + 1} · ${this.analysis.factors[p.value[1]].name}：${p.value[2] ? '高' : '低'}水平` }, grid: { left: 75, right: 20, top: 25, bottom: 90 }, xAxis: { type: 'category', data: this.analysis.runs.map(r => String(r.id)) }, yAxis: { type: 'category', data: this.analysis.factors.map(r => r.name) }, visualMap: { type: 'piecewise', orient: 'horizontal', bottom: 0, left: 'center', pieces: [{ value: 0, label: '低水平', color: '#b8d7f4' }, { value: 1, label: '高水平', color: '#2563eb' }] }, dataZoom: [{ type: 'slider', xAxisIndex: 0, bottom: 35, start: 0, end: 35 }], series: [{ type: 'heatmap', data: this.analysis.runs.flatMap((r, x) => r.levels.map((v, y) => [x, y, v])) }] }; },
    interactionChart() { return chart(['订单负荷低', '订单负荷高'], this.analysis.interaction.map((values, i) => ({ name: i ? 'OEE 高' : 'OEE 低', type: 'line', data: values.map(round) })), '平均数量(件)'); },
    responseChart() { return chart(this.analysis.runs.map(r => r.id), [{ name: '模拟采购量', type: 'line', data: this.analysis.runs.map(r => r.quantity) }], '数量(件)'); }
  },
  methods: { number(value) { return value.toFixed(3); }, money(value) { return value.toFixed(2); } }
};
</script>
<style scoped>
.risk-process{margin-top:24px}.risk-process h2{color:#174e7b}.risk-process h3{margin-top:26px}.process-flow{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}.process-flow span{background:#eaf3fc;border-left:3px solid #3b82f6;padding:12px;color:#24557c}.cost-inputs{display:flex;flex-wrap:wrap;gap:24px;margin:20px 0}.cost-inputs label{display:flex;flex-direction:column;gap:8px;color:#526579;font-size:14px}.analysis-copy,.process-charts p{font-size:14px;line-height:1.8;color:#617286}.process-charts{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;margin:16px 0}.process-charts .el-card{min-width:0}.result-summary{padding:16px;margin:16px 0;background:#eef8f3;border-left:4px solid #19a974;line-height:1.8;color:#24557c}@media(max-width:1100px){.process-charts{grid-template-columns:minmax(0,1fr)}}
</style>

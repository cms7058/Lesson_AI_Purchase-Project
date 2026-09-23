<template>
  <div class="equipment-spare-risk">
    <div class="page-heading">
      <div><p class="eyebrow">EQUIPMENT SPARE · RISK MODEL</p><h1>设备备件风险评估</h1><p>将设备 OEE、MTBF、MTTR、Cp、Cpk 和产品订单负荷转化为可解释的采购数量建议。</p></div>
      <el-tag type="warning">演示数据</el-tag>
    </div>
    <div class="risk-toolbar">
      <span>选择设备</span>
      <el-select v-model="selectedCode" style="width:310px" @change="onEquipmentChange">
        <el-option v-for="item in equipment" :key="item.code" :label="item.code+' · '+item.name" :value="item.code" />
      </el-select>
      <el-button type="primary" @click="calculate">计算</el-button>
      <span class="calculation-note">数据时点：2026-09-22 · 指标均为教学演示数据</span>
    </div>
    <el-alert title="计算口径" description="建议数量 = 基础需求 × 设备风险系数 × 订单负荷系数 − 可用库存；风险系数由 OEE、MTBF、MTTR、Cp、Cpk 归一化后加权得到。" type="info" :closable="false" show-icon />
    <el-alert v-if="!calculated" title="请选择设备后点击“计算”，系统将展示采购风险和数量建议。" type="warning" :closable="false" show-icon class="calculate-hint" />
    <div v-if="calculated" class="metric-grid">
      <div v-for="metric in selected.metrics" :key="metric.key" class="metric-card clickable" role="button" tabindex="0" @click="openHistory(metric.key)" @keyup.enter="openHistory(metric.key)"><span>{{metric.label}}</span><strong>{{metric.value}}{{metric.unit}}</strong><small>{{metric.note}} · 点击查看历史</small></div>
    </div>
    <div v-if="calculated" class="chart-grid">
      <el-card shadow="never"><div slot="header"><strong>指标对采购风险的贡献</strong><span class="header-note">归一化权重</span></div><analysis-chart :option="contributionChart" /></el-card>
      <el-card shadow="never"><div slot="header"><strong>采购数量计算过程</strong><span class="header-note">从基础需求到建议量</span></div><analysis-chart :option="quantityChart" /></el-card>
    </div>
    <el-card v-if="calculated" shadow="never" class="recommendation-card"><div slot="header"><strong>采购建议与计算明细</strong></div>
      <el-table :data="selected.parts" size="small"><el-table-column prop="material" label="备件编码" width="150"/><el-table-column prop="name" label="备件名称" min-width="180"/><el-table-column prop="base" label="基础需求" width="100"/><el-table-column prop="stock" label="可用库存" width="100"/><el-table-column prop="risk" label="风险系数" width="100"/><el-table-column prop="recommended" label="建议采购量" width="110"><template slot-scope="scope"><strong class="recommend-number">{{scope.row.recommended}}</strong></template></el-table-column><el-table-column label="最早/最晚到货" width="180"><template slot-scope="scope">{{scope.row.earliest}} / {{scope.row.latest}}</template></el-table-column></el-table>
      <div class="formula-line">{{selected.formula}}</div>
    </el-card>
    <el-card v-if="calculated" shadow="never" class="explain-card"><strong>分析说明</strong><p>{{selected.explanation}}</p><p>提示：OEE 越低、MTBF 越低、MTTR 越高，风险系数越高；Cp/Cpk 低于 1.33 时增加质量风险，系统建议优先保障关键设备备件。</p></el-card>
    <spare-risk-process v-if="calculated" :key="selectedCode" :equipment="selected" />
    <el-dialog v-if="activeMetric" :title="selected.name+' · '+activeMetric.label+'历史数据'" :visible.sync="historyVisible" width="900px" :close-on-click-modal="false">
      <analysis-chart :option="historyChart" />
      <el-table :data="activeHistory.rows" size="small" stripe>
        <el-table-column prop="date" label="月份" width="140" />
        <el-table-column v-if="activeMetricKey==='capability'" prop="cp" label="Cp" width="140" />
        <el-table-column v-if="activeMetricKey==='capability'" prop="cpk" label="Cpk" width="140" />
        <el-table-column v-else prop="value" :label="activeMetric.label" width="160" />
        <el-table-column prop="source" label="数据来源" min-width="220" />
      </el-table>
      <p class="history-note">演示数据按月汇总；正式环境将由设备、MES/QMS或ERP接口同步。</p>
    </el-dialog>
  </div>
</template>
<script>
import AnalysisChart from '../components/AnalysisChart.vue';
import SpareRiskProcess from '../components/SpareRiskProcess.vue';
const demo = [
  {code:'EXH-WELD-01',name:'排气管焊管一线',metrics:[{key:'oee',label:'OEE',value:'78.4',unit:'%',note:'目标≥85%，存在产能风险'},{key:'mtbf',label:'MTBF',value:'412',unit:' h',note:'近12个月关闭故障样本'},{key:'mttr',label:'MTTR',value:'6.8',unit:' h',note:'平均修复时长'},{key:'capability',label:'Cp / Cpk',value:'1.42 / 1.18',unit:'',note:'Cpk低于1.33，质量风险'}],history:{oee:[['2026-04','81.2'],['2026-05','80.1'],['2026-06','79.5'],['2026-07','78.9'],['2026-08','77.8'],['2026-09','78.4']],mtbf:[['2026-04','536'],['2026-05','498'],['2026-06','471'],['2026-07','452'],['2026-08','428'],['2026-09','412']],mttr:[['2026-04','4.6'],['2026-05','5.1'],['2026-06','5.8'],['2026-07','6.2'],['2026-08','7.1'],['2026-09','6.8']],capability:[['2026-04','1.56','1.34'],['2026-05','1.52','1.29'],['2026-06','1.48','1.25'],['2026-07','1.45','1.21'],['2026-08','1.43','1.19'],['2026-09','1.42','1.18']]},contributions:[62,55,48,34,46,51],quantity:[{name:'基础需求',value:42},{name:'风险调整',value:18},{name:'订单负荷',value:9},{name:'库存抵扣',value:-12},{name:'建议采购',value:57}],parts:[{material:'SP-EXH-001',name:'焊机电极头',base:42,stock:18,risk:'1.43',recommended:42,earliest:'2026-10-02',latest:'2026-10-10'},{material:'SP-EXH-014',name:'气密夹具密封圈',base:18,stock:6,risk:'1.31',recommended:24,earliest:'2026-10-05',latest:'2026-10-14'},{material:'SP-EXH-021',name:'焊管定位销',base:12,stock:4,risk:'1.18',recommended:15,earliest:'2026-10-08',latest:'2026-10-20'}],formula:'42 + 18 + 9 − 12 = 57 件；按设备关键性和供应交期建议分批下单。',explanation:'当前设备订单负荷较高，OEE低于目标且MTTR偏高；焊机电极头优先级最高，建议先覆盖42件安全需求，再按交期锁定补充批次。'},
  {code:'EXH-WELD-02',name:'排气管焊管二线',metrics:[{key:'oee',label:'OEE',value:'86.9',unit:'%',note:'达到目标'},{key:'mtbf',label:'MTBF',value:'688',unit:' h',note:'故障间隔较稳定'},{key:'mttr',label:'MTTR',value:'3.2',unit:' h',note:'平均修复时长'},{key:'capability',label:'Cp / Cpk',value:'1.61 / 1.48',unit:'',note:'过程能力良好'}],history:{oee:[['2026-04','84.7'],['2026-05','85.2'],['2026-06','85.8'],['2026-07','86.1'],['2026-08','86.5'],['2026-09','86.9']],mtbf:[['2026-04','621'],['2026-05','640'],['2026-06','652'],['2026-07','667'],['2026-08','676'],['2026-09','688']],mttr:[['2026-04','4.1'],['2026-05','3.9'],['2026-06','3.7'],['2026-07','3.5'],['2026-08','3.4'],['2026-09','3.2']],capability:[['2026-04','1.48','1.36'],['2026-05','1.51','1.39'],['2026-06','1.54','1.42'],['2026-07','1.57','1.45'],['2026-08','1.59','1.47'],['2026-09','1.61','1.48']]},contributions:[28,31,25,18,19,23],quantity:[{name:'基础需求',value:26},{name:'风险调整',value:6},{name:'订单负荷',value:4},{name:'库存抵扣',value:-10},{name:'建议采购',value:26}],parts:[{material:'SP-EXH-001',name:'焊机电极头',base:26,stock:12,risk:'1.18',recommended:18,earliest:'2026-10-12',latest:'2026-10-22'},{material:'SP-EXH-035',name:'焊枪冷却接头',base:12,stock:8,risk:'1.10',recommended:12,earliest:'2026-10-15',latest:'2026-10-25'}],formula:'26 + 6 + 4 − 10 = 26 件；设备能力稳定，可采用常规补库。',explanation:'设备运行和过程能力均较稳定，建议采用常规安全库存策略，避免因过度备货造成呆滞。'}
];
export default {components:{AnalysisChart,SpareRiskProcess},data:()=>({equipment:demo,selectedCode:demo[0].code,calculated:false,historyVisible:false,activeMetricKey:''}),computed:{selected(){return this.equipment.find(item=>item.code===this.selectedCode)||this.equipment[0];},activeMetric(){return this.selected.metrics.find(item=>item.key===this.activeMetricKey)||null;},activeHistory(){const rows=(this.selected.history?.[this.activeMetricKey]||[]).map(item=>this.activeMetricKey==='capability'?{date:item[0],cp:item[1],cpk:item[2],source:'QMS过程能力月报'}:{date:item[0],value:item[1],source:this.activeMetricKey==='oee'?'MES设备综合效率': '设备维修与故障台账'});return {rows};},contributionChart(){return {tooltip:{trigger:'axis'},grid:{left:55,right:20,bottom:55},xAxis:{type:'category',data:['OEE','MTBF','MTTR','Cp','Cpk','订单负荷']},yAxis:{type:'value',name:'风险贡献'},series:[{type:'bar',data:this.selected.contributions,itemStyle:{color:'#3b82f6'}}]};},quantityChart(){return {tooltip:{trigger:'axis'},grid:{left:55,right:20,bottom:55},xAxis:{type:'category',data:this.selected.quantity.map(item=>item.name)},yAxis:{type:'value',name:'数量(件)'},series:[{type:'bar',data:this.selected.quantity.map(item=>item.value),itemStyle:{color:'#19a974'}}]};},historyChart(){const values=this.selected.history?.[this.activeMetricKey]||[];const capability=this.activeMetricKey==='capability';return {tooltip:{trigger:'axis'},legend:capability?{data:['Cp','Cpk']}:{show:false},grid:{left:55,right:20,bottom:55},xAxis:{type:'category',data:values.map(item=>item[0])},yAxis:{type:'value',name:capability?'过程能力':this.activeMetric?.unit||''},series:capability?[{name:'Cp',type:'line',smooth:true,data:values.map(item=>item[1])},{name:'Cpk',type:'line',smooth:true,data:values.map(item=>item[2])}]:[{name:this.activeMetric?.label,type:'line',smooth:true,areaStyle:{},data:values.map(item=>item[1])}]};}},methods:{calculate(){this.calculated=true;this.$message.success('采购风险与数量建议已计算');},onEquipmentChange(){this.calculated=false;this.historyVisible=false;this.activeMetricKey='';},openHistory(key){this.activeMetricKey=key;this.historyVisible=true;}}};
</script>
<style scoped>
.risk-toolbar{display:flex;align-items:center;gap:12px;margin:16px 0}.risk-toolbar>span:first-child{font-weight:600;color:#456}.calculation-note{color:#8493a3;font-size:12px;margin-left:auto}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:16px 0}.metric-card{padding:16px;border:1px solid #e4ebf3;border-radius:10px;background:linear-gradient(145deg,#fff,#f5f9fd)}.metric-card span,.metric-card small{display:block;color:#718096}.metric-card strong{display:block;color:#174e7b;font-size:24px;margin:8px 0}.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}.header-note{float:right;color:#98a6b5;font-size:12px}.formula-line{margin-top:14px;padding:12px;background:#f5f9fd;border-radius:6px;color:#24557c;font-weight:600}.recommend-number{color:#14966b}.explain-card{margin-top:16px}.explain-card p{color:#617286;line-height:1.7}@media(max-width:1000px){.metric-grid{grid-template-columns:repeat(2,1fr)}.chart-grid{grid-template-columns:1fr}.calculation-note{display:none}}
.clickable{cursor:pointer;transition:transform .18s,box-shadow .18s}.clickable:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(36,85,124,.12)}.calculate-hint{margin-top:16px}.history-note{color:#8493a3;font-size:12px;margin:14px 0 0}
</style>

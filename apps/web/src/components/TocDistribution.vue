<template>
  <section class="toc-distribution" v-loading="loading">
    <h3>供货数据正态分析</h3>
    <div class="table-toolbar">
      <el-select v-model="supplier" placeholder="供应商"><el-option v-for="s in suppliers" :key="s.quotation_id" :value="s.quotation_id" :label="s.supplier_name"/></el-select>
      <el-select v-model="material" placeholder="物料编码"><el-option v-for="m in materials" :key="m.material_code" :value="m.material_code" :label="m.material_code+' · '+m.material_name"/></el-select>
      <el-select v-model="metric" placeholder="分析指标"><el-option v-for="(label,key) in labels" :key="key" :value="key" :label="label"/></el-select>
    </div>
    <p v-if="includeDemo">当前包含模拟批次，仅供演示，不作为正式定标依据。</p>
    <template v-if="analysis.statistics">
      <p>有效样本 {{stats.n}} 批 · 模拟 {{analysis.demo_count}} 批 · 中位数 {{num(stats.median)}} · 均值 {{num(stats.mean)}} · 标准差 {{num(stats.std)}} <span v-if="metric==='cost'">（{{currency}} / {{selectedMaterial.unit}}）</span></p>
      <el-alert :title="stats.normality+'；Shapiro-Wilk p='+num(stats.p_value)+'。正态曲线仅是参考，不代表数据一定服从正态分布。'" type="info" :closable="false"/>
      <div class="chart-grid">
        <div class="chart-card"><h4>实际分布与正态参考曲线</h4><ExplainableChart :option="normalChart" title="实际分布与正态参考曲线" interpretation="柱形表示实际批次落在各区间的密度，曲线是按样本均值和标准差生成的正态参考。两者越贴合，只说明分布形态更接近正态；中位线用于观察中心位置与偏态。" principle="直方图对样本分箱；正态参考密度由样本均值和标准差计算。Shapiro-Wilk检验用于识别偏离正态的证据，p值不能证明数据一定正态。"/></div>
        <div class="chart-card"><h4>中位数与四分位数箱线图</h4><ExplainableChart :option="medianChart" title="中位数与四分位数箱线图" interpretation="箱体中线是中位数，箱体上下沿分别是Q1和Q3，箱体越高表示中间50%的批次波动越大。与均值相比，中位数不易被极端批次拉动。" principle="箱线图基于排序后的分位数概括分布位置与离散程度；四分位距IQR用于观察波动和潜在异常，但异常点仍需结合业务原因核查。"/></div>
      </div>
      <el-collapse><el-collapse-item title="查看正态 Q-Q 图和原始批次数据" name="details"><ExplainableChart :option="qqChart" title="正态Q-Q图" interpretation="散点越接近一条直线，残差或指标分布越接近正态；两端系统性弯曲通常提示偏态、厚尾或异常批次。" principle="将实际样本分位数与理论正态分位数逐点比较。Q-Q图是诊断工具，不是通过/不通过的单一判据。"/><el-table :data="analysis.items" border><el-table-column prop="external_id" label="批次编号" min-width="200"/><el-table-column prop="record_date" label="日期"/><el-table-column :label="labels[metric]"><template slot-scope="s">{{num(s.row.value)}}</template></el-table-column><el-table-column label="数据类型"><template slot-scope="s">{{s.row.is_demo?'模拟数据':'实际反馈'}}</template></el-table-column></el-table><el-pagination layout="total,prev,pager,next" :total="analysis.total" :page-size="10" :current-page.sync="page" @current-change="load"/></el-collapse-item></el-collapse>
    </template><el-empty v-else description="暂无可分析数据"/>
  </section>
</template>
<script>
import {api} from '../api/client';
import ExplainableChart from './ExplainableChart.vue';
export default {
  components:{ExplainableChart},props:{suppliers:{type:Array,default:()=>[]},includeDemo:Boolean,currency:String},
  data:()=>({supplier:'',material:'',metric:'cost',page:1,analysis:{},loading:false,requestId:0,labels:{cost:'单位合格品综合成本',quality:'质量合格率(%)',delivery:'准时交付率(%)',rework:'返工率(%)',response:'响应时长(小时)'}}),
  computed:{selectedSupplier(){return this.suppliers.find(s=>s.quotation_id===this.supplier)||{};},materials(){return this.selectedSupplier.materials||[];},selectedMaterial(){return this.materials.find(m=>m.material_code===this.material)||{};},stats(){return this.analysis.statistics||{};},normalChart(){return {tooltip:{trigger:'axis'},legend:{data:['实际密度','正态参考']},grid:{left:65,right:20,bottom:50,top:45},xAxis:{type:'value',scale:true},yAxis:{type:'value',name:'概率密度'},series:[{name:'实际密度',type:'bar',barWidth:20,data:this.stats.histogram||[]},{name:'正态参考',type:'line',showSymbol:false,data:this.stats.normal_curve||[],markLine:{symbol:'none',data:this.stats.n?[{xAxis:this.stats.median,name:'中位数',label:{formatter:'中位数'}}]:[]}}]};},medianChart(){return {tooltip:{trigger:'item'},grid:{left:65,right:20,bottom:50,top:45},xAxis:{type:'category',data:['最小 / Q1 / 中位数 / Q3 / 最大']},yAxis:{type:'value',scale:true},series:[{type:'boxplot',data:this.stats.n?[this.stats.box]:[]}]};},qqChart(){return {title:{text:'正态 Q-Q 图'},tooltip:{},xAxis:{type:'value',name:'理论正态分位'},yAxis:{type:'value',name:'实际分位',scale:true},series:[{type:'scatter',data:this.stats.qq||[]}]};}},
  watch:{suppliers:{immediate:true,handler(){if(!this.suppliers.some(s=>s.quotation_id===this.supplier))this.supplier=this.suppliers[0]?.quotation_id||'';this.selectMaterial();}},supplier(){this.selectMaterial();},material(){this.refresh();},metric(){this.refresh();},includeDemo(){this.refresh();}},
  methods:{num(v){return v===undefined||v===null?'—':Number(v).toFixed(3);},selectMaterial(){if(!this.materials.some(m=>m.material_code===this.material))this.material=this.materials[0]?.material_code||'';this.refresh();},refresh(){this.page=1;this.load();},async load(){const id=++this.requestId;this.analysis={};if(!this.material||!this.supplier){this.loading=false;return;}this.loading=true;try{let result;if(this.metric==='cost'){const p=this.selectedMaterial.profile||{};const rows=(p.samples||[]).map(s=>({...s,record_date:s.date,value:s.cost}));result={statistics:p.distribution,items:rows.slice((this.page-1)*10,this.page*10),total:rows.length,demo_count:rows.filter(s=>s.is_demo).length};}else{result=(await api.get('/supplier-metrics/statistics',{params:{supplier_code:this.selectedSupplier.supplier_code,material_code:this.material,metric:this.metric,include_demo:this.includeDemo,page:this.page,page_size:10}})).data;}if(id===this.requestId)this.analysis=result;}catch(e){if(id===this.requestId)this.$message.error(e.response?.data?.detail||'正态分析加载失败');}finally{if(id===this.requestId)this.loading=false;}}}
};
</script>

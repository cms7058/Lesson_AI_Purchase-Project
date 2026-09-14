<template>
  <div class="cockpit" v-loading="loading">
    <div class="hero-row"><div><p class="eyebrow">采购运营 · 实时洞察</p><h1>采购驾驶舱</h1><p>点击状态、供应商、采购员或趋势图，联动查看采购指标和订单明细。</p></div><el-button @click="reset">重置筛选</el-button></div>
    <div class="cockpit-filters"><el-date-picker v-model="dates" type="daterange" value-format="yyyy-MM-dd" start-placeholder="创建开始日期" end-placeholder="创建结束日期" @change="refresh"/><el-select v-model="currency" style="width:120px" @change="refresh"><el-option v-for="c in data.currencies || ['CNY']" :key="c" :value="c" :label="c"/></el-select><el-tag v-if="status" closable @close="status='';refresh()">状态：{{ statusLabel }}</el-tag><el-tag v-if="supplier" closable @close="supplier='';refresh()">{{ supplier }}</el-tag><el-tag v-if="buyer" closable @close="buyer='';refresh()">采购员：{{ buyerLabel }}</el-tag><el-button icon="el-icon-refresh" @click="load">刷新</el-button></div>
    <p class="muted">统计口径：所选创建日期、币种及图表条件；排除已取消订单。金额为订单行税前金额，非实际支出；不跨币种相加。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false"/>
    <div class="metric-grid"><div v-for="m in metrics" :key="m.label" class="metric-card"><span>{{ m.label }}</span><strong>{{ m.value }}</strong><small>当前筛选范围</small></div></div>
    <div class="chart-card"><h3>采购金额月度趋势 · {{ currency }}</h3><AnalysisChart :option="trendOption" @select="selectMonth"/><el-empty v-if="!data.trend || !data.trend.length" description="暂无匹配订单" :image-size="50"/></div>
    <div class="cockpit-filters"><strong>时间联动：</strong><el-select v-model="selectedMonth" clearable placeholder="全部所选时间" @change="refresh"><el-option v-for="m in overview.trend || []" :key="m.name" :value="m.name" :label="m.name+' · '+currency+' '+money(m.value)"/></el-select><strong>{{ selectedMonth || '所选日期范围' }} 采购总额：{{ currency }} {{ money(monthData.kpis && monthData.kpis.purchase_amount) }}</strong><el-select v-model="buyer" clearable filterable placeholder="全部采购员" @change="chooseBuyer"><el-option v-for="b in overview.buyer_stats || []" :key="b.key" :value="b.key" :label="b.name"/></el-select></div>
    <div class="chart-grid"><div class="chart-card"><h3>采购员采购金额占比 · {{ selectedMonth || '所选时间' }}</h3><AnalysisChart :option="buyerPie" @select="selectBuyerPie"/></div><div class="chart-card"><h3>物料分类采购金额占比 · {{ selectedMonth || '所选时间' }}</h3><el-button size="mini" :disabled="!categoryPath.length" @click="categoryPath.pop()">返回上级</el-button><span> 一级分类 {{ categoryPath.map(c=>' / '+c.name).join('') }}</span><AnalysisChart :option="materialPie" @select="drillCategory"/><p class="muted">点击分类逐层查看二级、三级采购金额；未建立分类的物料计入“未分类”。</p></div></div>
    <div class="chart-card"><h3>物料分类采购趋势与分析</h3><AnalysisChart :option="categoryTrend"/><p>{{ categoryAnalysis }}</p></div>
    <div class="chart-card"><h3>采购员 × 时间 × 订单金额</h3><p class="muted">拖动旋转、滚轮缩放；点击柱体选中采购员。显示选中月份和采购员的数据。</p><BuyerTimeline3D :rows="buyerTimeline" :currency="currency" :buyer="buyer" @select="chooseBuyer3D"/></div>
    <div class="chart-card"><h3>{{ buyerLabel || '全部采购员' }} · 月度趋势与分析</h3><AnalysisChart :option="buyerTrend"/><p>{{ buyerAnalysis }}</p></div>
    <div class="chart-grid"><div class="chart-card"><h3>订单状态 · 点击联动</h3><AnalysisChart :option="statusOption" @select="selectStatus"/></div><div class="chart-card"><h3>供应商采购金额 TOP 8 · {{ currency }}</h3><AnalysisChart :option="supplierOption" @select="selectSupplier"/></div></div>

    <div class="chart-card"><h3>采购员责任分析 · 点击柱形联动订单</h3><p class="muted">按明确指定的订单责任采购员统计；历史未指定订单单列“未分配采购员”，不将创建人默认认定为负责人。</p><AnalysisChart :option="buyerOption" @select="selectBuyer"/></div>
    <div class="chart-card"><h3>采购员负责订单的供应商准时交付率</h3><p class="muted">准时批次 / 可评价已收货批次。以实际收货日期对比订单物料承诺日期；不包含未到货、缺交期或同物料存在多个交期的批次，暂无数据不按0%计。ERP/MES/WMS反馈未关联订单的指标不归属个人。</p><AnalysisChart :option="deliveryOption" @select="selectBuyer"/>
     <el-table :data="data.buyer_stats || []" size="small"><el-table-column prop="name" label="责任采购员" min-width="180"/><el-table-column prop="order_count" label="订单数量"/><el-table-column prop="amount" :label="'采购金额 '+currency"/><el-table-column prop="supplier_count" label="供应商数"/><el-table-column prop="receipt_count" label="已收货批次"/><el-table-column prop="eligible_receipts" label="可评价批次"/><el-table-column label="及时率"><template slot-scope="s">{{ rate(s.row.on_time_rate) }}</template></el-table-column></el-table>
     <el-collapse><el-collapse-item title="展开采购员—供应商交付明细"><el-table :data="(data.buyer_supplier_delivery || []).slice((deliveryPage-1)*10,deliveryPage*10)" stripe><el-table-column prop="buyer" label="采购员"/><el-table-column prop="supplier" label="供应商"/><el-table-column prop="receipt_count" label="已收货批次"/><el-table-column prop="eligible_receipts" label="可评价批次"/><el-table-column prop="on_time_receipts" label="准时批次"/><el-table-column label="及时率"><template slot-scope="s">{{ rate(s.row.on_time_rate) }}</template></el-table-column></el-table><el-pagination :current-page.sync="deliveryPage" :page-size="10" :total="(data.buyer_supplier_delivery||[]).length" layout="total, prev, pager, next"/></el-collapse-item></el-collapse>
    </div>
    <div class="chart-card"><div class="section-heading"><h3>联动订单明细（{{ data.total || 0 }} 条）</h3><router-link to="/orders">进入订单管理 →</router-link></div><el-table :data="data.rows || []" stripe><el-table-column prop="order_no" label="订单号" min-width="160"/><el-table-column prop="supplier_name" label="供应商" min-width="180"/><el-table-column prop="status" label="采购状态"/><el-table-column prop="buyer_name" label="责任采购员" min-width="150"/><el-table-column label="归属管理" width="120"><template slot-scope="s"><OrderBuyerAssign :order="s.row" @saved="load"/></template></el-table-column><el-table-column prop="created_at" label="创建时间" min-width="170"/><el-table-column label="税前金额" min-width="140"><template slot-scope="s">{{ currency }} {{ money(s.row.amount) }}</template></el-table-column></el-table><el-pagination :current-page="page" :page-size="10" :total="data.total || 0" layout="total, prev, pager, next" @current-change="page=$event;load()"/></div>
  </div>
</template>
<script>
import { api } from '../api/client';
import AnalysisChart from '../components/AnalysisChart.vue';
import BuyerTimeline3D from '../components/BuyerTimeline3D.vue';
import OrderBuyerAssign from '../components/OrderBuyerAssign.vue';
export default {
  components:{AnalysisChart,OrderBuyerAssign,BuyerTimeline3D},
  data:()=>({data:{},overview:{},monthData:{},categoryPath:[],selectedMonth:'',dates:[],currency:'CNY',status:'',statusLabel:'',supplier:'',buyer:'',buyerLabel:'',deliveryPage:1,page:1,loading:false,error:'',requestId:0}),
  computed:{
    buyerPie(){return this.pie((this.monthData.buyer_stats||[]).map(b=>({name:b.name,value:b.amount,key:b.key})));},
    materialPie(){return this.pie(this.categoryRows);},
    categoryRows(){const parent=this.categoryPath[this.categoryPath.length-1];return (this.monthData.category_amount||[]).filter(r=>parent?(parent.level===3||parent.key==='unclassified'?r.key===parent.key:r.parent_id===parent.key):r.level===1);},
    selectedCategories(){const parent=this.categoryPath[this.categoryPath.length-1];return parent?(this.overview.category_amount||[]).filter(r=>r.key===parent.key):(this.overview.category_amount||[]).filter(r=>r.level===1);},
    categoryTrend(){const rows=this.selectedCategories;const months=(this.overview.trend||[]).map(m=>m.name);return {tooltip:{trigger:'axis'},legend:{type:'scroll'},grid:{left:80,right:25,bottom:40},xAxis:{type:'category',data:months},yAxis:{type:'value'},series:rows.map(r=>({name:r.name,type:'line',data:months.map(m=>r.trend.find(t=>t.name===m)?.value||0)}))};},
    categoryAnalysis(){const rows=this.categoryRows;const total=rows.reduce((s,r)=>s+r.value,0);if(!rows.length)return '该分类暂无下级采购数据。';const top=[...rows].sort((a,b)=>b.value-a.value)[0];return '当前层级合计 '+this.currency+' '+this.money(total)+'，金额最高为 '+top.name+'，占比 '+(total?top.value/total*100:0).toFixed(1)+'%。趋势图显示日期范围内该分类的月度变化。';},
    buyerTimeline(){return (this.monthData.buyer_timeline||[]).filter(r=>!this.buyer||r.buyer_id===this.buyer);},
    buyerTrend(){const rows=(this.overview.buyer_timeline||[]).filter(r=>!this.buyer||r.buyer_id===this.buyer);const months=(this.overview.trend||[]).map(m=>m.name);return {tooltip:{trigger:'axis'},grid:{left:80,right:25,bottom:40},xAxis:{type:'category',data:months},yAxis:{type:'value'},series:[{type:'line',data:months.map(m=>rows.filter(r=>r.month===m).reduce((s,r)=>s+r.amount,0))}]};},
    buyerAnalysis(){const rows=(this.monthData.buyer_stats||[]).filter(r=>!this.buyer||r.key===this.buyer);return (this.buyerLabel||'全部采购员')+'：所选月份负责 '+rows.reduce((s,r)=>s+r.order_count,0)+' 笔订单，金额 '+this.currency+' '+this.money(rows.reduce((s,r)=>s+r.amount,0))+'。';},
    buyerOption(){const rows=this.data.buyer_stats||[];return {tooltip:{trigger:'axis'},legend:{data:['订单数量','采购金额']},grid:{left:70,right:90,bottom:90},xAxis:{type:'category',data:rows.map(x=>x.name),axisLabel:{rotate:20}},yAxis:[{type:'value',name:'订单数量',minInterval:1},{type:'value',name:this.currency}],series:[{name:'订单数量',type:'bar',data:rows.map(x=>x.order_count)},{name:'采购金额',type:'bar',yAxisIndex:1,data:rows.map(x=>x.amount)}]};},
    deliveryOption(){const rows=this.data.buyer_stats||[];return {tooltip:{trigger:'axis'},grid:{left:70,right:30,bottom:90},xAxis:{type:'category',data:rows.map(x=>x.name),axisLabel:{rotate:20}},yAxis:{type:'value',min:0,max:100,axisLabel:{formatter:'{value}%'}},series:[{type:'bar',data:rows.map(x=>x.on_time_rate),label:{show:true,position:'top',formatter:p=>p.value+'%'},itemStyle:{color:'#28b49b'}}]};},
    metrics(){const k=this.data.kpis||{};return [{label:'采购订单',value:k.order_count||0},{label:'采购金额 · '+this.currency,value:this.money(k.purchase_amount)},{label:'交易供应商',value:k.supplier_count||0},{label:'已完成订单',value:k.completed_count||0}];},
    statusOption(){return {tooltip:{trigger:'item'},series:[{type:'pie',radius:['38%','65%'],data:this.data.order_status||[],label:{formatter:'{b}: {c}'}}]};},
    supplierOption(){const rows=this.data.supplier_amount||[];return {tooltip:{trigger:'axis'},grid:{left:170,right:30,bottom:35},xAxis:{type:'value'},yAxis:{type:'category',inverse:true,data:rows.map(x=>x.name),axisLabel:{width:150,overflow:'truncate'}},series:[{type:'bar',data:rows.map(x=>x.value),itemStyle:{color:'#2878ff'}}]};},
    trendOption(){const rows=this.overview.trend||[];return {tooltip:{trigger:'axis'},grid:{left:80,right:30,bottom:35},xAxis:{type:'category',data:rows.map(x=>x.name)},yAxis:{type:'value'},series:[{type:'line',symbolSize:12,areaStyle:{opacity:.12},data:rows.map(x=>x.value)}]};}
  },
  created(){this.load();},
  methods:{
    drillCategory(e){const row=e.data;if(this.categoryPath.some(c=>c.key===row.key))return;this.categoryPath.push(row);},
    pie(rows){return {tooltip:{trigger:'item',valueFormatter:v=>this.currency+' '+this.money(v)},legend:{type:'scroll',bottom:0},series:[{type:'pie',radius:['30%','62%'],center:['50%','43%'],data:rows,label:{formatter:'{b}: {d}%'}}]};},
    selectBuyerPie(e){this.chooseBuyer3D({key:e.data.key,name:e.name});},
    chooseBuyer(){this.buyerLabel=(this.overview.buyer_stats||[]).find(b=>b.key===this.buyer)?.name||'';this.refresh();},
    chooseBuyer3D(b){this.buyer=b.key;this.buyerLabel=b.name;this.refresh();},

    rate(value){return value===null||value===undefined?'暂无数据':value+'%';},
    selectBuyer(e){const row=(this.data.buyer_stats||[])[e.dataIndex];if(!row)return;this.buyer=row.key;this.buyerLabel=row.name;this.refresh();},
    money(n){return Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:2});},
    refresh(){this.deliveryPage=1;this.page=1;this.load();},
    reset(){this.categoryPath=[];this.selectedMonth='';this.dates=[];this.status='';this.supplier='';this.buyer='';this.refresh();},
    selectStatus(e){this.status=e.data.code;this.statusLabel=e.name;this.refresh();},
    selectSupplier(e){this.supplier=e.name;this.refresh();},
    selectMonth(e){if(/^\d{4}-\d{2}$/.test(e.name)){this.selectedMonth=e.name;this.refresh();}},
    async load(){const id=++this.requestId;this.loading=true;this.error='';try{
      const common={currency:this.currency,start:this.dates&&this.dates[0]||undefined,end:this.dates&&this.dates[1]||undefined,status:this.status,supplier:this.supplier,page_size:10};
      const overview=(await api.get('/analytics/cockpit',{params:common})).data;
      if(id!==this.requestId)return;
      if(this.selectedMonth&&!(overview.trend||[]).some(m=>m.name===this.selectedMonth))this.selectedMonth='';
      const detail={...common,buyer:this.buyer,page:this.page};
      if(this.selectedMonth){const [year,month]=this.selectedMonth.split('-').map(Number);const first=this.selectedMonth+'-01',last=this.selectedMonth+'-'+new Date(year,month,0).getDate();detail.start=common.start&&common.start>first?common.start:first;detail.end=common.end&&common.end<last?common.end:last;}
      const [r,m]=await Promise.all([api.get('/analytics/cockpit',{params:detail}),api.get('/analytics/cockpit',{params:{...detail,buyer:''}})]);if(id===this.requestId){this.overview=overview;this.data=r.data;this.monthData=m.data;}
    }catch(e){if(id===this.requestId){this.data={};this.overview={};this.error=e.response?.data?.detail||'驾驶舱加载失败，请重试';}}finally{if(id===this.requestId)this.loading=false;}}
  }
};
</script>

<template>
 <div class="cockpit" v-loading="loading">
  <div class="hero-row"><div><p class="eyebrow">项目运营 · 实时洞察</p><h1>项目驾驶舱</h1><p>点击项目状态、负责人或计划月份，联动查看指标与项目明细。</p></div><el-button @click="reset">重置筛选</el-button></div>
  <div class="cockpit-filters"><el-select v-model="currency" @change="refresh"><el-option v-for="c in data.currencies||['CNY']" :key="c" :value="c" :label="c"/></el-select><el-tag v-if="status" closable @close="status='';refresh()">{{labels[status]}}</el-tag><el-tag v-if="manager" closable @close="manager='';refresh()">负责人：{{managerLabel}}</el-tag><el-tag v-if="month" closable @close="month='';refresh()">计划完成月份：{{month}}</el-tag><el-button @click="load">刷新</el-button><router-link to="/projects">管理项目 →</router-link></div>
  <p class="muted">预算按币种汇总，不代表实际采购支出；月份按任务计划结束日期筛选项目，预算为匹配项目的完整预算，不是该月发生额。任务数不含工作包。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <div class="metric-grid"><div v-for="m in metrics" :key="m.name" class="metric-card"><span>{{m.name}}</span><strong>{{m.value}}</strong><small>当前筛选范围</small></div></div>
  <div class="chart-card"><h3>任务计划完成月份分布</h3><AnalysisChart :option="trend" @select="selectMonth"/></div>
  <div class="chart-grid"><div class="chart-card"><h3>项目状态分布</h3><AnalysisChart :option="statusChart" @select="selectStatus"/></div><div class="chart-card"><h3>项目经理负责项目数</h3><AnalysisChart :option="managerChart" @select="selectManager"/></div></div>
  <div class="chart-card"><h3>联动项目明细</h3><el-table :data="data.rows||[]"><el-table-column prop="code" label="编号"/><el-table-column prop="name" label="项目"/><el-table-column prop="manager_name" label="项目经理"/><el-table-column label="状态"><template slot-scope="s">{{labels[s.row.status]}}</template></el-table-column><el-table-column prop="budget" :label="'预算 · '+currency"/><el-table-column label="操作"><template slot-scope="s"><el-button type="text" @click="$router.push({path:'/projects',query:{project:s.row.id}})">查看计划</el-button></template></el-table-column></el-table><el-pagination :current-page="page" :total="data.total||0" :page-size="10" layout="total,prev,pager,next" @current-change="page=$event;load()"/></div>
 </div>
</template>
<script>
import {api} from '../api/client';
import AnalysisChart from '../components/AnalysisChart.vue';
export default {
 components:{AnalysisChart},data:()=>({data:{},loading:false,error:'',currency:'CNY',status:'',manager:'',managerLabel:'',month:'',page:1,requestId:0,labels:{draft:'草稿',active:'执行中',completed:'已完成',archived:'已归档'}}),
 computed:{metrics(){return [{name:'项目数',value:this.data.project_count||0},{name:'项目预算 · '+this.currency,value:Number(this.data.budget||0).toFixed(2)},{name:'任务 / 已完成',value:(this.data.tasks||0)+' / '+(this.data.completed||0)},{name:'执行中项目逾期任务',value:this.data.overdue||0}];},statusChart(){return this.pie((this.data.statuses||[]).map(r=>({...r,name:this.labels[r.key]})));},managerChart(){return this.pie(this.data.managers||[]);},trend(){return {tooltip:{trigger:'axis'},xAxis:{type:'category',data:(this.data.trend||[]).map(r=>r.name)},yAxis:{type:'value',minInterval:1},series:[{type:'bar',data:(this.data.trend||[]).map(r=>r.value),itemStyle:{color:'#2878ff'}}]};}},
 created(){this.load();},methods:{pie(data){return {tooltip:{trigger:'item'},legend:{bottom:0},series:[{type:'pie',radius:['38%','65%'],data}]};},selectMonth(p){this.month=p.name;this.refresh();},selectStatus(p){this.status=p.data.key;this.refresh();},selectManager(p){this.manager=p.data.key;this.managerLabel=p.name;this.refresh();},refresh(){this.page=1;this.load();},reset(){this.currency='CNY';this.status='';this.manager='';this.month='';this.refresh();},async load(){const id=++this.requestId;this.loading=true;this.error='';try{const r=await api.get('/projects/dashboard',{params:{currency:this.currency,status:this.status,manager_id:this.manager,month:this.month,page:this.page}});if(id===this.requestId)this.data=r.data;}catch(e){if(id===this.requestId)this.error=e.response?.data?.detail||'项目驾驶舱加载失败';}finally{if(id===this.requestId)this.loading=false;}}}
};
</script>

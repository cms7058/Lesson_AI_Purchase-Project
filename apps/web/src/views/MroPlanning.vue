<template>
  <div class="mro-plan-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">SELLER-LED MRO · AMOS · SAP · SMART INVENTORY</p>
        <h1>MRO预测与采购供货计划</h1>
        <p>按物料属性组合选择预测方法，汇总自有、寄售、VMI与修理回转库存，形成可解释的采购与供货日历。</p>
      </div>
      <div><el-button @click="$router.push('/data-sources?setup=mro')">配置数据接口</el-button><el-button type="primary" :loading="seeding" @click="seedDemo">加入演示数据</el-button></div>
    </div>
    <div class="process-strip"><span>多维画像</span><i>→</i><span>AMOS/SAP/WMS数据</span><i>→</i><span>正态与中位数诊断</span><i>→</i><span>模型路由</span><i>→</i><span>采购/供货日历</span></div>
    <el-card shadow="never" class="control-card">
      <el-form inline>
        <el-form-item label="计划周期（天）"><el-input-number v-model="horizon" :min="30" :max="730" :step="30" controls-position="right" style="width:150px"/></el-form-item>
        <el-form-item><el-button-group><el-button v-for="days in [90,180,365]" :key="days" size="small" :type="horizon===days?'primary':''" @click="horizon=days">{{ days }}天</el-button></el-button-group></el-form-item>
        <el-form-item label="指定物料"><el-select v-model="selectedCodes" multiple filterable collapse-tags clearable placeholder="留空分析全部画像物料" style="width:360px"><el-option v-for="item in profiles" :key="item.material_code" :label="`${item.material_code} · ${item.material_name}`" :value="item.material_code"/></el-select></el-form-item>
        <el-form-item><el-button type="primary" :loading="loading" @click="runAnalysis">生成采购与供货计划</el-button></el-form-item>
      </el-form>
      <el-alert title="统计口径" description="样本≥8时进行正态性检验；通过时采用均值+标准差服务水平，不通过时采用中位数+四分位距。单一来源、长交期、高价值组合优先采用AMOS维修事件推断。" type="info" :closable="false" show-icon/>
    </el-card>

    <template v-if="result">
      <div class="metric-grid">
        <div class="metric-card"><span>画像物料</span><strong>{{ result.summary.materials }}</strong><small>多属性可叠加</small></div>
        <div class="metric-card"><span>需采购物料</span><strong>{{ result.summary.purchase_lines }}</strong><small>已抵扣全部库存形态</small></div>
        <div class="metric-card"><span>建议采购数量</span><strong>{{ result.summary.purchase_quantity }}</strong><small>按计划周期汇总</small></div>
        <div class="metric-card"><span>AMOS事件模型</span><strong>{{ result.summary.amos_models }}</strong><small>关键属性组合自动路由</small></div>
      </div>
      <el-tabs v-model="active" type="card" @tab-click="tabChanged">
        <el-tab-pane label="采购与供货日历" name="calendar"/>
        <el-tab-pane label="模型与数据诊断" name="diagnostics"/>
        <el-tab-pane label="计划明细" name="details"/>
      </el-tabs>

      <section v-if="active==='calendar'" class="calendar-layout">
        <div class="calendar-main">
          <el-tabs v-model="activeMonth" type="card" class="month-tabs" @tab-click="monthChanged">
            <el-tab-pane v-for="month in calendarMonths" :key="month.key" :name="month.key" :label="`${month.label}（${month.count}）`"/>
          </el-tabs>
          <div class="legend"><strong>物料属性颜色：</strong><i v-for="item in result.legend" :key="item.label" :style="{borderColor:item.color,color:item.color,background:item.color+'14'}"><b :style="{background:item.color}"></b>{{ item.label }}</i><em>日历任务显示该物料的首要属性；点击日期可查看全部属性。</em></div>
          <div ref="calendar" class="calendar-host"></div>
        </div>
        <el-card shadow="never" class="day-panel">
          <div slot="header"><strong>{{ selectedDate || '点击日历日期' }}</strong><span> · 当日计划</span></div>
          <el-empty v-if="!dayEvents.length" description="当日暂无采购或供货计划" :image-size="70"/>
          <div v-for="event in dayEvents" :key="event.id" class="day-event">
            <h4><span>{{ event.plan_type==='purchase'?'采购':'供货' }}</span>{{ event.material_code }}</h4>
            <p>{{ event.material_name }} · 数量 {{ event.quantity }}</p>
            <div><span v-for="tag in event.attributes" :key="tag.label" class="attribute-tag" :style="{borderColor:tag.color,color:tag.color,background:tag.color+'12'}">{{ tag.label }}</span></div>
            <small>{{ event.method_name }}</small>
            <template v-if="event.plan_type==='purchase'">
              <div v-if="inventoryFor(event).positions" class="inventory-block">
                <div class="inventory-summary"><strong>各库库存</strong><span>当前可用 {{ inventoryFor(event).available_quantity || 0 }}</span></div>
                <div v-for="position in inventoryFor(event).positions" :key="position.id" class="position-row">
                  <span>{{ position.warehouse_code }} · {{ position.position_name }}</span>
                  <button class="inventory-link" type="button" @click="openInventory(event,position)">账面 {{ position.quantity }} / 预留 {{ position.reserved_quantity }} / 隔离 {{ position.quarantined_quantity }} / 可用 {{ position.effective_quantity }} <i>查看明细</i></button>
                </div>
                <el-alert class="action-guide" :title="actionGuide(event)" :type="actionGuideType(event)" :closable="false" show-icon/>
                <div class="execution-actions">
                  <el-button v-if="Number(inventoryFor(event).available_quantity)>0" size="mini" type="success" :loading="actionLoading===event.id+':activate_supply'" :disabled="hasExecution(event,'activate_supply')" @click="execute(event,'activate_supply')">{{hasExecution(event,'activate_supply')?'已下发检货':'步骤1 · 激活现有库存供货'}}</el-button>
                  <el-button v-if="Number(inventoryFor(event).available_quantity)<Number(event.quantity)" size="mini" type="primary" :loading="actionLoading===event.id+':create_order'" :disabled="hasExecution(event,'create_order')" @click="execute(event,'create_order')">{{hasExecution(event,'create_order')?'采购订单已生成':Number(inventoryFor(event).available_quantity)>0?'步骤2 · 采购剩余缺口':'生成采购订单'}}</el-button>
                </div>
                <p v-for="done in executionsFor(event)" :key="done.id" class="execution-ref">{{done.action_type==='activate_supply'?'检货任务':'采购订单'}}：{{done.reference_no}}</p>
              </div>
              <el-skeleton v-else :rows="2" animated/>
            </template>
          </div>
        </el-card>
      </section>

      <section v-if="active==='diagnostics'">
        <el-card shadow="never" class="diagnostic-selector"><span>选择物料：</span><el-select v-model="diagnosticCode" filterable style="width:320px"><el-option v-for="item in result.items" :key="item.material_code" :label="`${item.material_code} · ${item.material_name}`" :value="item.material_code"/></el-select></el-card>
        <template v-if="diagnosticItem">
          <div class="explain-card"><div><strong>{{ diagnosticItem.method_name }}</strong><p>{{ diagnosticItem.rationale }}</p></div><div class="formula">预测 {{ diagnosticItem.forecast_quantity }} − 有效库存 {{ diagnosticItem.available_quantity }} = 建议采购 {{ diagnosticItem.purchase_quantity }}</div></div>
          <div class="chart-grid"><el-card shadow="never"><AnalysisChart :option="demandChart"/></el-card><el-card shadow="never"><AnalysisChart :option="leadChart"/></el-card></div>
          <el-table :data="diagnosticRows" class="data-table"><el-table-column prop="name" label="诊断对象"/><el-table-column prop="count" label="样本数" width="90"/><el-table-column prop="normality" label="正态结论" width="120"><template slot-scope="s"><el-tag :type="s.row.normality==='normal'?'success':s.row.normality==='non_normal'?'warning':'info'">{{ normalityName(s.row.normality) }}</el-tag></template></el-table-column><el-table-column prop="p" label="P值" width="90"/><el-table-column prop="mean" label="均值"/><el-table-column prop="median" label="中位数"/><el-table-column prop="q90" label="P90"/><el-table-column prop="outliers" label="异常值"/></el-table>
        </template>
      </section>

      <section v-if="active==='details'">
        <el-table :data="result.items" class="data-table" row-key="material_code">
          <el-table-column prop="material_code" label="物料编码" width="145" fixed/><el-table-column prop="material_name" label="物料名称" min-width="170"/><el-table-column label="属性组合" min-width="250"><template slot-scope="s"><span v-for="tag in s.row.attributes" :key="tag.label" class="attribute-tag" :style="{borderColor:tag.color,color:tag.color,background:tag.color+'12'}">{{ tag.label }}</span></template></el-table-column><el-table-column prop="method_name" label="预测方法" min-width="160"/><el-table-column prop="forecast_quantity" label="预测需求" width="100"/><el-table-column prop="available_quantity" label="有效库存" width="100"/><el-table-column prop="purchase_quantity" label="建议采购" width="100"/><el-table-column prop="purchase_date" label="采购日期" width="120"/><el-table-column prop="supply_date" label="供货日期" width="120"/><el-table-column prop="review_cycle_days" label="复核周期" width="100"><template slot-scope="s">{{ s.row.review_cycle_days }}天</template></el-table-column>
        </el-table>
      </section>

    </template>

    <el-dialog :title="`${inventoryDetail.event ? inventoryDetail.event.material_code : ''} 库存明细`" :visible.sync="inventoryVisible" width="760px" append-to-body>
      <el-alert v-if="inventoryDetail.event" :title="`${inventoryDetail.event.material_name} · 计划数量 ${inventoryDetail.event.quantity} · 当前有效库存 ${inventoryFor(inventoryDetail.event).available_quantity || 0}`" type="info" :closable="false"/>
      <el-table v-if="inventoryDetail.event" :data="inventoryFor(inventoryDetail.event).positions || []" class="data-table" style="margin-top:14px" :row-class-name="inventoryRowClass">
        <el-table-column prop="warehouse_code" label="仓库"/>
        <el-table-column prop="position_name" label="库存形态"/>
        <el-table-column prop="quantity" label="账面"/>
        <el-table-column prop="reserved_quantity" label="预留"/>
        <el-table-column prop="quarantined_quantity" label="隔离"/>
        <el-table-column prop="effective_quantity" label="有效可用"/>
        <el-table-column prop="available_date" label="可用日期"/>
        <el-table-column prop="source_system" label="来源系统"/>
      </el-table>
      <span slot="footer"><el-button @click="$router.push('/warehouse')">进入仓储管理</el-button><el-button type="primary" @click="inventoryVisible=false">关闭</el-button></span>
    </el-dialog>
  </div>
</template>

<script>
import { Calendar, CALENDAR_EVENT_TYPE } from "@visactor/vtable-calendar";
import { api } from "../api/client";
import AnalysisChart from "../components/AnalysisChart.vue";

export default {
  components:{AnalysisChart},
  data:()=>({profiles:[],selectedCodes:[],horizon:180,loading:false,seeding:false,result:null,active:"calendar",calendar:null,selectedDate:"",activeMonth:"",diagnosticCode:"",inventoryMap:{},actionLoading:"",inventoryVisible:false,inventoryDetail:{event:null,position:null}}),
  computed:{
    dayEvents(){return this.result?this.result.calendar_events.filter(item=>item.date===this.selectedDate):[];},
    calendarMonths(){if(!this.result)return[];const base=new Date(`${this.result.generated_at}T12:00:00`);const count=Math.max(1,Math.ceil(this.result.horizon_days/30));return Array.from({length:count},(_,index)=>{const start=this.addDays(base,index*30);const end=this.addDays(base,Math.min((index+1)*30-1,this.result.horizon_days-1));const startKey=this.formatDate(start);const endKey=this.formatDate(end);const events=this.result.calendar_events.filter(item=>item.date>=startKey&&item.date<=endKey);return{key:String(index),start,end,startKey,endKey,label:`第${index+1}月 ${String(start.getMonth()+1).padStart(2,"0")}/${String(start.getDate()).padStart(2,"0")}–${String(end.getMonth()+1).padStart(2,"0")}/${String(end.getDate()).padStart(2,"0")}`,count:events.length};});},
    activePeriod(){return this.calendarMonths.find(item=>item.key===this.activeMonth)||null;},
    monthEvents(){return this.result&&this.activePeriod?this.result.calendar_events.filter(item=>item.date>=this.activePeriod.startKey&&item.date<=this.activePeriod.endKey):[];},
    diagnosticItem(){return this.result?.items.find(item=>item.material_code===this.diagnosticCode)||null;},
    diagnosticRows(){if(!this.diagnosticItem)return[];const d=this.diagnosticItem.diagnostics;return [["需求（月）",d.demand],["交期",d.lead_time],["需求间隔",d.demand_interval]].map(([name,row])=>({name,count:row.count,normality:row.normality,p:row.normality_p??"-",mean:row.mean,median:row.median,q90:row.q90,outliers:row.outliers}));},
    demandChart(){return this.histogramOption(this.diagnosticItem?.diagnostics.demand,"需求量分布与中位数");},
    leadChart(){return this.histogramOption(this.diagnosticItem?.diagnostics.lead_time,"交期分布与中位数");}
  },
  async created(){await this.loadProfiles();},
  beforeDestroy(){this.releaseCalendar();},
  methods:{
    error(e){this.$message.error(e.response?.data?.detail||e.message||"操作失败");},
    normalityName(v){return {normal:"通过正态检验",non_normal:"非正态",insufficient:"样本不足"}[v]||v;},
    async loadProfiles(){try{this.profiles=(await api.get("/mro-intelligence/profiles",{params:{page:1,page_size:100}})).data.items;}catch(e){this.error(e);}},
    async seedDemo(){this.seeding=true;try{await api.post("/mro-intelligence/demo");await this.loadProfiles();this.$message.success("MRO预测演示数据已加入");await this.runAnalysis();}catch(e){this.error(e);}finally{this.seeding=false;}},
    async runAnalysis(){this.loading=true;try{this.result=(await api.post("/mro-intelligence/analyze",{horizon_days:this.horizon,material_codes:this.selectedCodes,save:true})).data;this.diagnosticCode=this.result.items[0]?.material_code||"";this.activeMonth="0";const first=this.monthEvents.find(item=>item.plan_type==="purchase")||this.monthEvents[0];this.selectedDate=first?.date||this.result.generated_at;this.inventoryMap={};this.active="calendar";await this.loadDayInventory();this.$nextTick(this.renderCalendar);if(!this.result.items.length)this.$message.warning("尚无MRO画像，请先加入演示数据或在物料画像中配置");}catch(e){this.error(e);}finally{this.loading=false;}},
    tabChanged(){if(this.active==="calendar")this.$nextTick(this.renderCalendar);else this.releaseCalendar();},
    monthChanged(){const first=this.monthEvents.find(item=>item.plan_type==="purchase")||this.monthEvents[0];this.selectedDate=first?.date||this.activePeriod?.startKey||this.result.generated_at;this.loadDayInventory();this.$nextTick(this.renderCalendar);},
    addDays(value,days){const result=new Date(value);result.setDate(result.getDate()+days);return result;},
    formatDate(value){const d=new Date(value);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;},
    releaseCalendar(){if(this.calendar){this.calendar.release();this.calendar=null;}},
    renderCalendar(){if(!this.result||!this.$refs.calendar||!this.activePeriod)return;this.releaseCalendar();const periodStart=this.activePeriod.start;const periodEnd=this.activePeriod.end;const start=new Date(periodStart.getFullYear(),periodStart.getMonth(),1);const end=new Date(periodEnd.getFullYear(),periodEnd.getMonth()+1,0);const calendarEnd=new Date(periodEnd.getFullYear(),periodEnd.getMonth()+2,0);const selected=new Date(`${this.selectedDate}T12:00:00`);const current=selected>=periodStart&&selected<=periodEnd?selected:periodStart;const events=this.monthEvents.map(item=>{const eventDate=new Date(`${item.date}T12:00:00`);const primary=(item.attributes&&item.attributes[0])||{};const eventColor=primary.color||item.color||"#1677ff";return{type:"bar",id:item.id,startDate:eventDate,endDate:eventDate,text:`${primary.label?`[【${primary.label}】] `:""}${item.plan_type==="purchase"?"采购":"供货"} ${item.material_code} × ${item.quantity}`,color:"#fff",bgColor:eventColor,customInfo:item};});this.calendar=new Calendar(this.$refs.calendar,{startDate:start,endDate:calendarEnd,currentDate:current,dayTitles:["周日","周一","周二","周三","周四","周五","周六"],customEvents:events,showTitle:true,customEventOptions:{fontSize:11,contentHeight:20,barHeight:18,barCornerRadius:5}});const updateMonthStyle=this.calendar._updateMonthCustomStyle.bind(this.calendar);this.calendar._updateMonthCustomStyle=(year,month)=>{const requested=new Date(year,month,1);const bounded=requested<start?start:requested>end?end:requested;updateMonthStyle(bounded.getFullYear(),bounded.getMonth());};const selectDate=({date})=>{this.selectedDate=this.formatDate(date);this.loadDayInventory();};this.calendar.on(CALENDAR_EVENT_TYPE.CALENDAR_DATE_CLICK,selectDate);this.calendar.on(CALENDAR_EVENT_TYPE.CALENDAR_CUSTOM_EVENT_CLICK,selectDate);},
    inventoryFor(event){return this.inventoryMap[event.material_code]||{};},
    executionsFor(event){return (this.inventoryFor(event).executions||[]).filter(item=>item.plan_event_id===event.id);},
    hasExecution(event,type){return (this.inventoryFor(event).executions||[]).some(item=>item.plan_event_id===event.id&&item.action_type===type);},
    actionGuide(event){const available=Number(this.inventoryFor(event).available_quantity||0);const required=Number(event.quantity);if(available<=0)return `当前没有可用库存，需要生成采购订单 ${required} 件。`;if(available>=required)return `现有库存可满足全部 ${required} 件需求，只需点击“激活现有库存供货”，无需生成采购订单。`;return `现有库存只能满足 ${available}/${required} 件：先激活库存供货，再对剩余 ${required-available} 件生成采购订单；两个步骤都需要执行。`;},
    actionGuideType(event){const available=Number(this.inventoryFor(event).available_quantity||0);const required=Number(event.quantity);return available<=0?"error":available>=required?"success":"warning";},
    openInventory(event,position){this.inventoryDetail={event,position};this.inventoryVisible=true;},
    inventoryRowClass({row}){return this.inventoryDetail.position&&row.id===this.inventoryDetail.position.id?"selected-inventory-row":"";},
    async loadDayInventory(){const codes=[...new Set(this.dayEvents.filter(item=>item.plan_type==="purchase").map(item=>item.material_code))];if(!codes.length)return;try{const rows=(await api.post("/mro-intelligence/inventory-status",{material_codes:codes,plan_run_id:this.result.run_id||""})).data.items;this.inventoryMap={...this.inventoryMap,...Object.fromEntries(rows.map(row=>[row.material_code,row]))};}catch(e){this.error(e);}},
    async execute(event,actionType){this.actionLoading=event.id+":"+actionType;try{const status=this.inventoryFor(event);const quantity=actionType==="create_order"?Math.max(1,Number(event.quantity)-Number(status.available_quantity||0)):Math.min(Number(event.quantity),Number(status.available_quantity||0));const response=(await api.post("/mro-intelligence/execute",{plan_run_id:this.result.run_id||"",plan_event_id:event.id,material_code:event.material_code,material_name:event.material_name,quantity,plan_date:event.date,action_type:actionType})).data;this.$message.success(`${actionType==="activate_supply"?"检货任务已下发":"采购订单已生成"}：${response.execution.reference_no}`);await this.loadDayInventory();}catch(e){this.error(e);}finally{this.actionLoading="";}},
    histogramOption(diag,title){const row=diag||{histogram:[],median:0,mean:0,unit:""};return{title:{text:title,left:12,textStyle:{fontSize:15}},tooltip:{trigger:"axis"},grid:{top:52,left:50,right:25,bottom:55},xAxis:{type:"category",data:row.histogram.map(x=>x.range),axisLabel:{rotate:25}},yAxis:{type:"value",name:"样本数"},series:[{type:"bar",data:row.histogram.map(x=>x.count),itemStyle:{color:"#1677ff"},markLine:{symbol:"none",label:{formatter:`中位数 ${row.median}${row.unit}`},data:[{yAxis:0,lineStyle:{color:"#f59e0b"}}]}}]};}
  }
};
</script>

<style scoped>
.process-strip{display:flex;align-items:center;gap:12px;padding:12px 18px;margin-bottom:16px;background:#eef6ff;border:1px solid #d7e8ff;border-radius:10px;color:#31577d}.process-strip i{color:#8aa8c6}.control-card{margin-bottom:16px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:16px 0}.metric-card{padding:17px;border:1px solid #e6edf5;border-radius:10px;background:linear-gradient(145deg,#fff,#f6faff)}.metric-card span,.metric-card small{display:block;color:#6b7d90}.metric-card strong{display:block;font-size:28px;margin:8px 0;color:#12395d}.calendar-layout{display:grid;grid-template-columns:minmax(0,1fr) 430px;gap:16px}.calendar-main{min-width:0;background:#fff;border:1px solid #e6edf5;border-radius:8px;padding:12px}.month-tabs{margin-bottom:10px}.calendar-host{height:720px;width:100%}.legend{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:5px 4px 13px;color:#657789;font-size:12px}.legend strong{color:#34495e}.legend i{display:inline-flex;align-items:center;padding:4px 8px;border:1px solid;border-radius:12px;font-style:normal;font-weight:600}.legend b{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.legend em{width:100%;font-style:normal;color:#718096}.day-panel{height:max-content}.day-event{border-bottom:1px solid #edf1f5;padding:12px 0}.day-event:last-child{border:0}.day-event h4{margin:0 0 6px}.day-event h4 span{font-size:11px;background:#edf5ff;color:#1677ff;border-radius:4px;padding:2px 5px;margin-right:7px}.day-event p{margin:5px 0;color:#56677a}.day-event small{display:block;margin-top:7px;color:#8291a1}.attribute-tag{display:inline-block;border:1px solid;border-radius:12px;padding:2px 7px;margin:2px 5px 2px 0;font-size:11px}.inventory-block{margin-top:10px;padding:10px;background:#f7f9fc;border:1px solid #e3eaf2;border-radius:7px}.inventory-summary{display:flex;justify-content:space-between;margin-bottom:7px;color:#31577d}.position-row{padding:6px 0;border-top:1px dashed #dce4ed;font-size:12px}.position-row span{display:block}.inventory-link{display:block;width:100%;padding:4px 0;border:0;background:transparent;text-align:left;color:#526f8e;cursor:pointer}.inventory-link:hover{color:#1677ff;text-decoration:underline}.inventory-link i{float:right;font-style:normal;color:#1677ff}.action-guide{margin-top:10px}.execution-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.execution-ref{font-size:12px;color:#1677ff!important;word-break:break-all}.diagnostic-selector{margin-bottom:14px}.explain-card{display:flex;justify-content:space-between;align-items:center;background:#f6f9fd;border:1px solid #e4ebf3;border-radius:9px;padding:16px;margin-bottom:14px}.explain-card p{margin:6px 0 0;color:#66788a}.formula{font-weight:600;color:#164e7a}.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}:deep(.selected-inventory-row){background:#eef7ff!important}@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(2,1fr)}.calendar-layout,.chart-grid{grid-template-columns:1fr}.calendar-host{height:650px}}
</style>

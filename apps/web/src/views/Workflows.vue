<template>
  <div>
    <div class="page-heading">
      <div><p class="eyebrow">PROCUREMENT AUTOMATION</p><h1>自动化工作流</h1><p>编排报价、订单、合同与付款流程，统一管理审批、文档生成及邮件通知。</p></div>
      <el-button type="primary" @click="openCreate">新建工作流</el-button>
    </div>
    <div class="process-strip"><span>业务触发</span><i>→</i><span>审批与动作</span><i>→</i><span>邮件通知</span><i>→</i><span>运行审计</span></div>
    <el-tabs v-model="activeTab" @tab-click="loadActive">
      <el-tab-pane label="流程定义" name="definitions">
        <el-table v-loading="loading" :data="workflows" class="data-table" empty-text="暂无工作流">
          <el-table-column prop="name" label="流程名称" min-width="190"/>
          <el-table-column label="业务对象" width="110"><template slot-scope="scope">{{businessName(scope.row.business_type)}}</template></el-table-column>
          <el-table-column label="触发方式" width="110"><template slot-scope="scope">{{triggerName(scope.row.trigger_type)}}</template></el-table-column>
          <el-table-column label="流程步骤" min-width="220"><template slot-scope="scope"><el-tag v-for="(step,index) in scope.row.steps" :key="index" size="mini" class="step-tag">{{index+1}}. {{step.name}}</el-tag></template></el-table-column>
          <el-table-column label="状态" width="90"><template slot-scope="scope"><el-tag :type="statusType(scope.row.status)">{{statusName(scope.row.status)}}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="250" fixed="right"><template slot-scope="scope"><el-button type="text" @click="openEdit(scope.row)">编辑</el-button><el-button type="text" @click="toggle(scope.row)">{{scope.row.status==='active'?'停用':'启用'}}</el-button><el-button type="text" :disabled="scope.row.status!=='active'" @click="openExecute(scope.row)">运行</el-button><el-button type="text" class="danger-link" @click="remove(scope.row)">删除</el-button></template></el-table-column>
        </el-table>
        <pager :pagination="workflowPage" @page="changeWorkflowPage" @size="changeWorkflowSize"/>
      </el-tab-pane>
      <el-tab-pane label="运行记录" name="runs">
        <el-table v-loading="loading" :data="runs" class="data-table" empty-text="暂无运行记录">
          <el-table-column prop="workflow_name" label="工作流" min-width="180"/><el-table-column prop="business_id" label="业务单号" min-width="150"/><el-table-column label="执行结果" min-width="230"><template slot-scope="scope"><span v-for="(step,index) in scope.row.result.steps" :key="index" class="run-step">{{step.name}}：{{stepStatus(step.status)}}</span></template></el-table-column><el-table-column prop="started_at" label="开始时间" width="180"/><el-table-column label="状态" width="120"><template slot-scope="scope"><el-tag :type="runType(scope.row.status)">{{runStatus(scope.row.status)}}</el-tag></template></el-table-column><el-table-column label="操作" width="100" fixed="right"><template slot-scope="scope"><el-button v-if="scope.row.status==='awaiting_approval'" type="text" @click="approve(scope.row)">审批通过</el-button><span v-else>-</span></template></el-table-column>
        </el-table>
        <pager :pagination="runPage" @page="changeRunPage" @size="changeRunSize"/>
      </el-tab-pane>
      <el-tab-pane label="邮件通知" name="outbox">
        <el-alert title="邮件先进入发件箱，配置 SMTP 后由授权用户确认发送；未配置时不会向外部发送。" type="info" :closable="false" show-icon/>
        <el-table v-loading="loading" :data="outbox" class="data-table outbox-table" empty-text="暂无邮件通知">
          <el-table-column prop="recipient" label="收件人" min-width="180"/><el-table-column prop="subject" label="主题" min-width="190"/><el-table-column prop="body" label="内容" min-width="240" show-overflow-tooltip/><el-table-column prop="created_at" label="创建时间" width="180"/><el-table-column label="状态" width="100"><template slot-scope="scope"><el-tag :type="scope.row.status==='sent'?'success':scope.row.status==='failed'?'danger':'warning'">{{mailStatus(scope.row.status)}}</el-tag></template></el-table-column><el-table-column label="操作" width="90" fixed="right"><template slot-scope="scope"><el-button type="text" :disabled="scope.row.status==='sent'" @click="dispatch(scope.row)">发送</el-button></template></el-table-column>
        </el-table>
        <pager :pagination="outboxPage" @page="changeOutboxPage" @size="changeOutboxSize"/>
      </el-tab-pane>
    </el-tabs>

    <el-dialog :title="editingId?'编辑工作流':'新建工作流'" :visible.sync="formVisible" width="820px" :close-on-click-modal="false">
      <el-form ref="form" :model="form" :rules="rules" label-width="90px">
        <el-row :gutter="16"><el-col :span="12"><el-form-item label="流程名称" prop="name"><el-input v-model.trim="form.name" placeholder="例如：订单审批与通知"/></el-form-item></el-col><el-col :span="6"><el-form-item label="业务对象"><el-select v-model="form.business_type" style="width:100%"><el-option v-for="item in businessOptions" :key="item.value" :label="item.label" :value="item.value"/></el-select></el-form-item></el-col><el-col :span="6"><el-form-item label="触发方式"><el-select v-model="form.trigger_type" style="width:100%"><el-option label="手动触发" value="manual"/><el-option label="状态变化" value="status_change"/><el-option label="定时执行" value="scheduled"/></el-select></el-form-item></el-col></el-row>
        <div class="dialog-section-title"><div><strong>流程步骤</strong><small>按顺序配置审批、通知和业务动作</small></div><el-button size="mini" icon="el-icon-plus" @click="addStep">添加步骤</el-button></div>
        <div v-for="(step,index) in form.steps" :key="index" class="workflow-step-card">
          <span class="step-index">{{index+1}}</span><el-input v-model.trim="step.name" placeholder="步骤名称"/><el-select v-model="step.action" @change="resetStep(step)"><el-option v-for="item in actionOptions" :key="item.value" :label="item.label" :value="item.value"/></el-select><el-button type="text" class="danger-link" :disabled="form.steps.length===1" @click="form.steps.splice(index,1)">移除</el-button>
          <div v-if="step.action==='email'" class="email-step-fields"><el-input v-model.trim="step.recipient" placeholder="收件邮箱"/><el-input v-model.trim="step.subject" placeholder="邮件主题"/><el-input v-model="step.content" type="textarea" :rows="2" :placeholder="'正文支持 {{business_id}} 业务单号变量'"/></div>
        </div>
      </el-form>
      <span slot="footer"><el-button @click="formVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存工作流</el-button></span>
    </el-dialog>
    <el-dialog title="运行工作流" :visible.sync="executeVisible" width="520px"><el-alert :title="`将运行：${selected?selected.name:''}`" type="info" :closable="false"/><el-form label-width="90px" class="dialog-form-spaced"><el-form-item label="业务单号"><el-input v-model.trim="businessId" placeholder="请输入订单、报价或合同编号"/></el-form-item></el-form><span slot="footer"><el-button @click="executeVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="execute">确认运行</el-button></span></el-dialog>
  </div>
</template>

<script>
import { approveWorkflowRun, createWorkflow, deleteWorkflow, dispatchNotification, executeWorkflow, fetchNotificationOutbox, fetchWorkflowRuns, fetchWorkflows, updateWorkflow } from "../api/client";

const emptyStep=()=>({name:"",action:"approval",recipient:null,subject:"",content:""});
const emptyForm=()=>({name:"",business_type:"order",trigger_type:"manual",steps:[emptyStep()]});
import Pager from "../components/Pager.vue";

export default {
  components:{Pager},
  data:()=>({activeTab:"definitions",loading:false,saving:false,formVisible:false,executeVisible:false,editingId:"",selected:null,businessId:"",workflows:[],runs:[],outbox:[],workflowPage:{page:1,page_size:10,total:0},runPage:{page:1,page_size:10,total:0},outboxPage:{page:1,page_size:10,total:0},form:emptyForm(),rules:{name:[{required:true,message:"请输入流程名称",trigger:"blur"}]},businessOptions:[{label:"报价",value:"quotation"},{label:"订单",value:"order"},{label:"合同",value:"contract"},{label:"采购申请",value:"requisition"},{label:"付款",value:"payment"}],actionOptions:[{label:"审批",value:"approval"},{label:"邮件通知",value:"email"},{label:"更新状态",value:"update_status"},{label:"生成文档",value:"create_document"},{label:"调用 Webhook",value:"webhook"}]}),
  created(){this.loadWorkflows();},
  methods:{
    businessName(value){const item=this.businessOptions.find(option=>option.value===value);return item?item.label:value;},triggerName(value){return {manual:"手动触发",status_change:"状态变化",scheduled:"定时执行"}[value]||value;},statusName(value){return {draft:"草稿",active:"已启用",disabled:"已停用"}[value]||value;},statusType(value){return {draft:"info",active:"success",disabled:"danger"}[value]||"";},runStatus(value){return {awaiting_approval:"等待审批",completed:"已完成",failed:"失败"}[value]||value;},runType(value){return {awaiting_approval:"warning",completed:"success",failed:"danger"}[value]||"";},stepStatus(value){return {waiting:"待审批",approved:"已批准",completed:"已完成"}[value]||value;},mailStatus(value){return {pending:"待发送",sent:"已发送",failed:"发送失败"}[value]||value;},
    async loadWorkflows(){this.loading=true;try{const result=await fetchWorkflows(this.workflowPage);this.workflows=result.items;this.workflowPage.total=result.total;}catch(_){this.$message.error("工作流加载失败");}finally{this.loading=false;}},async loadRuns(){this.loading=true;try{const result=await fetchWorkflowRuns(this.runPage);this.runs=result.items;this.runPage.total=result.total;}catch(_){this.$message.error("运行记录加载失败");}finally{this.loading=false;}},async loadOutbox(){this.loading=true;try{const result=await fetchNotificationOutbox(this.outboxPage);this.outbox=result.items;this.outboxPage.total=result.total;}catch(_){this.$message.error("通知记录加载失败");}finally{this.loading=false;}},loadActive(){if(this.activeTab==="definitions")this.loadWorkflows();else if(this.activeTab==="runs")this.loadRuns();else this.loadOutbox();},
    changeWorkflowPage(page){this.workflowPage.page=page;this.loadWorkflows();},changeWorkflowSize(size){this.workflowPage.page_size=size;this.workflowPage.page=1;this.loadWorkflows();},changeRunPage(page){this.runPage.page=page;this.loadRuns();},changeRunSize(size){this.runPage.page_size=size;this.runPage.page=1;this.loadRuns();},changeOutboxPage(page){this.outboxPage.page=page;this.loadOutbox();},changeOutboxSize(size){this.outboxPage.page_size=size;this.outboxPage.page=1;this.loadOutbox();},
    openCreate(){this.editingId="";this.form=emptyForm();this.formVisible=true;},openEdit(item){this.editingId=item.id;this.form={name:item.name,business_type:item.business_type,trigger_type:item.trigger_type,steps:item.steps.map(step=>({...step}))};this.formVisible=true;},addStep(){this.form.steps.push(emptyStep());},resetStep(step){if(step.action!=="email"){step.recipient=null;step.subject="";step.content="";}},
    save(){this.$refs.form.validate(async valid=>{if(!valid)return;if(this.form.steps.some(step=>!step.name))return this.$message.warning("请填写全部步骤名称");if(this.form.steps.some(step=>step.action==="email"&&!step.recipient))return this.$message.warning("请填写邮件步骤的收件邮箱");this.saving=true;try{if(this.editingId)await updateWorkflow(this.editingId,this.form);else await createWorkflow(this.form);this.$message.success("工作流已保存");this.formVisible=false;await this.loadWorkflows();}catch(error){this.$message.error(error.response&&error.response.data&&error.response.data.detail||"保存失败");}finally{this.saving=false;}});},
    async toggle(item){try{await updateWorkflow(item.id,{status:item.status==="active"?"disabled":"active"});this.$message.success(item.status==="active"?"工作流已停用":"工作流已启用");await this.loadWorkflows();}catch(_){this.$message.error("状态更新失败");}},openExecute(item){this.selected=item;this.businessId="";this.executeVisible=true;},async execute(){if(!this.businessId)return this.$message.warning("请输入业务单号");this.saving=true;try{await executeWorkflow(this.selected.id,{business_id:this.businessId});this.$message.success("工作流已开始运行");this.executeVisible=false;this.activeTab="runs";await this.loadRuns();}catch(error){this.$message.error(error.response&&error.response.data&&error.response.data.detail||"运行失败");}finally{this.saving=false;}},
    async approve(item){try{await this.$confirm(`确认批准工作流 ${item.workflow_name}？`,"流程审批",{type:"warning"});await approveWorkflowRun(item.id);this.$message.success("流程已批准并完成");await this.loadRuns();}catch(error){if(error!=="cancel")this.$message.error("审批失败");}},async dispatch(item){try{await this.$confirm(`确认向 ${item.recipient} 发送邮件？`,"发送确认",{type:"warning"});await dispatchNotification(item.id);this.$message.success("邮件已发送");await this.loadOutbox();}catch(error){if(error!=="cancel")this.$message.error(error.response&&error.response.data&&error.response.data.detail||"发送失败");}},async remove(item){try{await this.$confirm(`确定删除工作流 ${item.name} 吗？`,"删除确认",{type:"warning"});await deleteWorkflow(item.id);this.$message.success("工作流已删除");await this.loadWorkflows();}catch(error){if(error!=="cancel")this.$message.error("删除失败");}}
  }
};
</script>

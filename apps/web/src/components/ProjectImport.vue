<template>
 <div>
  <el-button @click="visible=true">邮件 / 合同导入</el-button>
  <el-dialog title="项目资料识别与草案预览" :visible.sync="visible" width="1000px" append-to-body :close-on-click-modal="false">
   <el-alert title="PDF会传输至系统管理员配置的MinerU服务进行解析，失败时仅对可检索PDF进行本地回退。请勿向未经批准的外部服务上传敏感合同；导入只生成草稿。" :closable="false"/>
   <el-tabs v-model="mode"><el-tab-pane label="粘贴合同 / 邮件文本" name="text"><el-input v-model="text" type="textarea" :rows="6" maxlength="20000" show-word-limit placeholder="粘贴项目资料，例如：项目名称：装配线改造；交付：2026年12月01日完成设备交付"/></el-tab-pane><el-tab-pane label="上传PDF / 邮件 / Word" name="file"><input ref="file" type="file" accept=".pdf,.eml,.docx,.txt" @change="file=$event.target.files[0]||null"/><p>支持PDF、EML、DOCX、UTF-8 TXT，最多5MB。扫描PDF需要启用MinerU服务。</p><el-button type="text" @click="$router.push('/data-sources?setup=mineru');visible=false">配置MinerU PDF解析接口 →</el-button></el-tab-pane></el-tabs>
   <el-button type="primary" :loading="busy" @click="recognize">识别并预览</el-button><el-alert v-if="error" :title="error" type="error" :closable="false"/>
   <div v-if="result"><h3>项目名称候选：{{result.draft.name}}</h3><el-alert v-for="w in result.warnings" :key="w" :title="w" type="warning" :closable="false"/><el-alert v-if="result.existing_projects.length" :title="'发现相同文本已用于项目：'+result.existing_projects.map(p=>p.code).join('、')+'。本次只创建新草稿，不合并或覆盖原项目。'" type="warning" :closable="false"/>
    <el-table :data="result.draft.tasks" max-height="300"><el-table-column prop="name" label="任务候选" min-width="220"/><el-table-column prop="finish" label="结束日期候选" width="130"/><el-table-column prop="source" label="来源依据" min-width="260"/></el-table>
    <el-collapse><el-collapse-item title="查看提取原文"><pre style="white-space:pre-wrap;max-height:220px;overflow:auto">{{result.draft.import_evidence.source_text}}</pre></el-collapse-item></el-collapse>
    <el-checkbox v-model="confirmed">我已核对来源和候选项，将继续完善草稿，不直接发布。</el-checkbox>
   </div>
   <span slot="footer"><el-button :disabled="busy" @click="visible=false">关闭</el-button><el-button type="primary" :disabled="!result||!confirmed||busy" @click="apply">使用草稿并完善</el-button></span>
  </el-dialog>
 </div>
</template>
<script>
import {api} from '../api/client';
export default {data:()=>({visible:false,mode:'text',text:'',file:null,result:null,confirmed:false,error:'',busy:false}),watch:{text(){this.result=null;this.confirmed=false;},file(){this.result=null;this.confirmed=false;},mode(){this.result=null;this.confirmed=false;}},methods:{async recognize(){this.result=null;this.confirmed=false;this.error='';this.busy=true;try{if(this.mode==='text'){this.result=(await api.post('/projects/import-text',{text:this.text})).data;}else{if(!this.file||this.file.size>5*1024*1024)throw Error('请选择不超过5MB的文件');const f=new FormData();f.append('file',this.file);this.result=(await api.post('/projects/import-file',f,{timeout:130000})).data;}}catch(e){const d=e.response?.data?.detail;this.error=typeof d==='string'?d:e.message||'识别失败';}finally{this.busy=false;}},apply(){this.$emit('draft',this.result.draft);this.visible=false;}}};
</script>

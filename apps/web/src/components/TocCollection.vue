<template>
  <div class="toc-collection">
    <div class="chart-grid">
      <div class="chart-card"><h3>方式一：模板采集与导入</h3><p>下载包含全部采集字段的 CSV 模板，填写实际批次数据后导入。支持 UTF-8 / BOM、最多1000行、5MB；整批校验，不会部分写入。</p><el-button @click="download">下载采集模板</el-button><el-button type="primary" @click="openImport">导入采集数据</el-button></div>
      <div class="chart-card"><h3>方式二：来源系统 API 接入</h3><p>前往系统配置建立 ERP / MES / WMS 等连接器，启用后生成专用令牌。当前支持外部系统按统一字段主动推送 JSON，不自动拉取第三方接口。</p><el-button @click="$router.push({path:'/data-sources',query:{setup:'toc-api'}})">配置来源系统 API</el-button></div>
    </div>
    <el-dialog title="导入 TOC 采集数据" :visible.sync="visible" width="760px" append-to-body :close-on-click-modal="false" :before-close="close">
      <el-form label-width="120px">
        <el-form-item label="数据来源"><el-radio-group v-model="mode" :disabled="busy"><el-radio label="existing">已有连接器</el-radio><el-radio label="new">新建人工采集来源</el-radio></el-radio-group></el-form-item>
        <el-form-item v-if="mode==='existing'" label="连接器"><el-select v-model="connectorId" filterable remote :remote-method="search" :loading="loading" :disabled="busy" placeholder="搜索并选择已启用连接器" style="width:100%"><el-option v-for="c in connectors" :key="c.id" :label="c.name+' · '+c.connector_type+(c.status==='active'?'':'（未启用）')" :value="c.id" :disabled="c.status!=='active'"/></el-select></el-form-item>
        <template v-else><el-form-item label="来源名称"><el-input v-model.trim="sourceName" maxlength="120" :disabled="busy" placeholder="例如：工厂一 MES 人工采集"/></el-form-item><el-form-item label="来源系统"><el-select v-model="sourceType" :disabled="busy"><el-option v-for="t in ['erp','mes','wms','qms','srm','custom_api']" :key="t" :label="t.toUpperCase()" :value="t"/></el-select></el-form-item></template>
        <el-form-item label="采集文件"><input ref="file" type="file" accept=".csv" :disabled="busy" @change="file=$event.target.files[0] || null"/></el-form-item>
      </el-form>
      <p>供应商和物料编码必须已存在；空白指标不按0处理。请提供 metrics_available_date（指标实际可用日期），否则多元模型只能用于诊断。来源、原始批次和审计记录会保留。</p>
      <el-alert v-if="failure" :title="failure" type="error" :closable="false" show-icon/>
      <el-alert v-if="result" :title="`导入成功：新增 ${result.inserted} 条，重复跳过 ${result.skipped} 条。分析已请求刷新。`" type="success" :closable="false" show-icon/>
      <span slot="footer"><el-button :disabled="busy" @click="visible=false">关闭</el-button><el-button type="primary" :loading="busy" @click="upload">校验并导入</el-button></span>
    </el-dialog>
  </div>
</template>
<script>
import {api} from '../api/client';
export default {
  data:()=>({visible:false,mode:'existing',connectorId:'',connectors:[],loading:false,busy:false,sourceName:'',sourceType:'mes',file:null,result:null,failure:'',searchId:0}),
  methods:{
    close(done){if(!this.busy)done();},
    async search(keyword=''){const id=++this.searchId;this.loading=true;try{const r=await api.get('/data-connectors',{params:{keyword,page:1,page_size:100}});if(id===this.searchId)this.connectors=r.data.items;}catch(e){this.$message.error('连接器加载失败，请重试');}finally{if(id===this.searchId)this.loading=false;}},
    openImport(){this.visible=true;this.result=null;this.failure='';this.search();},
    async download(){try{const r=await api.get('/supply-feedback/template',{responseType:'blob'});const u=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=u;a.download='toc-feedback-template.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}catch(e){this.$message.error('模板下载失败，请检查权限');}},
    async upload(){
      this.result=null;this.failure='';
      if(!this.file||!this.file.name.toLowerCase().endsWith('.csv')||this.file.size>5*1024*1024){this.failure='请选择不超过5MB的CSV文件';return;}
      if(this.mode==='existing'&&!this.connectorId){this.failure='请选择已启用的连接器';return;}
      if(this.mode==='new'&&this.sourceName.length<2){this.failure='来源名称至少2个字符';return;}
      this.busy=true;
      try{
        if(this.mode==='new'){
          const r=await api.post('/data-connectors',{name:this.sourceName,connector_type:this.sourceType,sync_mode:'manual'});
          this.connectorId=r.data.id;this.mode='existing';await this.search();
          await api.patch(`/data-connectors/${this.connectorId}`,{status:'active'});await this.search();
        }
        const f=new FormData();f.append('file',this.file);
        this.result=(await api.post(`/data-connectors/${this.connectorId}/feedback-import`,f)).data;
        this.file=null;this.$refs.file.value='';this.$emit('imported');
      }catch(e){const d=e.response?.data?.detail;this.failure=typeof d==='string'?d:'导入失败，请检查权限、来源状态及文件内容';}finally{this.busy=false;}
    }
  }
};
</script>

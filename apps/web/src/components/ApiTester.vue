<template>
 <div>
  <el-alert title="仅测试并预览，不导入业务数据。配置和凭据仅保留在当前弹窗，关闭即清除。支持公网HTTPS 443，不跟随重定向；私有ERP请通过受控网关接入。" :closable="false"/>
  <el-form label-width="140px" style="margin-top:16px" :disabled="busy">
   <el-form-item label="API 地址"><el-input v-model.trim="form.url" placeholder="https://api.example.com/items?page=1"/></el-form-item>
   <el-form-item label="请求方式"><el-radio-group v-model="form.method"><el-radio label="GET"/><el-radio label="POST"/></el-radio-group></el-form-item>
   <el-form-item v-if="form.method==='POST'" label="JSON 请求体"><el-input type="textarea" :rows="4" v-model="body"/></el-form-item>
   <el-form-item label="Token（可选）"><el-select v-model="form.auth"><el-option label="无需认证" value="none"/><el-option label="手动 Bearer Token" value="manual"/><el-option label="从认证接口获取" value="endpoint"/></el-select></el-form-item>
   <el-form-item v-if="form.auth==='manual'" label="Bearer Token"><el-input v-model="form.token" show-password autocomplete="off"/></el-form-item>
   <template v-if="form.auth==='endpoint'">
    <el-form-item label="Token 获取地址"><el-input v-model.trim="form.token_url" placeholder="https://api.example.com/oauth/token"/></el-form-item>
    <el-form-item label="POST 编码"><el-radio-group v-model="form.token_format"><el-radio label="json">JSON</el-radio><el-radio label="form">表单</el-radio></el-radio-group></el-form-item>
    <el-form-item label="认证参数 JSON"><el-input type="textarea" :rows="4" v-model="tokenBody" placeholder='{"grant_type":"client_credentials","client_id":"...","client_secret":"..."}'/><small>也可按接口文档填写 username / password。这里包含敏感信息，请勿分享截图。</small></el-form-item>
    <el-form-item label="Token 字段路径"><el-input v-model.trim="form.token_path" placeholder="access_token 或 data.access_token"/></el-form-item>
   </template>
  </el-form>
  <el-button type="primary" :loading="busy" @click="run">{{form.auth==='endpoint'?'获取Token并测试':'测试接口'}}</el-button>
  <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-top:12px"/>
  <template v-if="result"><p>HTTP {{result.status}} · {{result.elapsed_ms}} ms · {{result.bytes}} 字节 {{result.token_acquired?'· Token获取成功（不显示明文）':''}}</p><el-alert v-if="!result.is_json" title="接口返回的不是可预览JSON，请检查地址及请求参数。" type="warning" :closable="false"/><pre v-else style="max-height:360px;overflow:auto;white-space:pre-wrap;word-break:break-all;background:#f4f7fa;padding:16px">{{JSON.stringify(result.data,null,2)}}</pre></template>
 </div>
</template>
<script>
import {api} from '../api/client';
export default {
 props:{url:{type:String,default:''}},data(){return {busy:false,error:'',result:null,body:'{}',tokenBody:'{}',form:{url:this.url,method:'GET',auth:'none',token:'',token_url:'',token_format:'json',token_path:'access_token'}};},
 methods:{async run(){this.error='';this.result=null;try{
  const parse=s=>{const v=JSON.parse(s);if(!v||Array.isArray(v)||typeof v!=='object')throw Error('请求参数必须是JSON对象');return v;};
  const payload={...this.form,body:this.form.method==='POST'?parse(this.body):{},token_body:this.form.auth==='endpoint'?parse(this.tokenBody):{}};
  if(this.form.method==='POST')await this.$confirm('POST测试可能在外部系统创建或修改数据，请确认这是允许调用的测试接口。','请求确认');
  this.busy=true;this.$emit('busy',true);this.result=(await api.post('/data-connectors/test-api',payload,{timeout:60000})).data;
 }catch(e){if(e!=='cancel'&&e!=='close'){const detail=e.response?.data?.detail;this.error=typeof detail==='string'?detail:Array.isArray(detail)?'请检查API地址、Token和请求参数':e.message||'测试失败';}}finally{this.busy=false;this.$emit('busy',false);}}}
};
</script>

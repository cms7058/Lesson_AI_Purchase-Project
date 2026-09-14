<template>
  <div><div class="page-heading"><div><h1>邮件发送设置</h1><p>配置后可在询价发布时自动发送邀请；附件由供应商登录后下载。</p></div></div>
    <el-alert title="授权码加密保存，不回显。自动发送仅作用于新发布询价；历史询价请在项目中点击发送/重试邮件。" type="info" :closable="false" />
    <el-form :model="form" label-width="150px" style="max-width:760px;margin-top:24px" v-loading="loading">
      <el-form-item label="SMTP服务器"><el-input v-model.trim="form.host" placeholder="例如 smtp.example.com" /></el-form-item>
      <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
      <el-form-item label="传输加密"><el-select v-model="form.security"><el-option label="STARTTLS（通常587）" value="starttls"/><el-option label="SSL/TLS（通常465）" value="ssl"/></el-select></el-form-item>
      <el-form-item label="登录账号"><el-input v-model.trim="form.username" autocomplete="off" /></el-form-item>
      <el-form-item label="密码/授权码"><el-input v-model="form.password" show-password autocomplete="new-password" :placeholder="form.password_set?'已保存，留空保持不变':'请输入邮箱授权码'" /></el-form-item>
      <el-form-item label="发件邮箱"><el-input v-model.trim="form.from_email" /></el-form-item>
      <el-form-item label="供应商门户地址"><el-input v-model.trim="form.portal_url"/><small>须为供应商可访问的 HTTPS 地址；localhost 仅供本机演示。</small></el-form-item>
      <el-form-item label="发布后自动发送"><el-switch v-model="form.auto_send" /></el-form-item>
      <el-form-item><el-button type="primary" :loading="saving" @click="save">保存配置</el-button></el-form-item>
    </el-form>
  </div>
</template>
<script>
import {api} from '../api/client';
export default {data:()=>({form:{},loading:false,saving:false}),async created(){this.loading=true;try{this.form=(await api.get('/mail-settings')).data;}catch(e){this.error(e);}finally{this.loading=false;}},methods:{error(e){const d=e.response?.data?.detail;this.$message.error(typeof d==='string'?d:'配置操作失败，请检查输入');},async save(){this.saving=true;try{this.form=(await api.put('/mail-settings',this.form)).data;this.$message.success('邮件设置已保存');}catch(e){this.error(e);}finally{this.saving=false;}}}};
</script>

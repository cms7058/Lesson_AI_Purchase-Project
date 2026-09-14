<template><div class="floating-assistant"><el-button class="ai-fab" type="primary" round icon="el-icon-chat-dot-round" @click="open">AI助力助手</el-button><el-dialog title="AI助力助手 · 对话查数" :visible.sync="visible" width="min(940px, 95vw)" top="4vh" append-to-body :close-on-click-modal="false" custom-class="assistant-dialog"><AssistantChat v-if="scope" :key="scope" :supplier-mode="!!$route.meta.supplierPortal"/></el-dialog></div></template>
<script>
import AssistantChat from './AssistantChat.vue';
export default {components:{AssistantChat},data:()=>({visible:false,scope:''}),watch:{'$route'(){this.visible=false;}},methods:{open(){this.scope=this.$route.meta.supplierPortal?'supplier-'+(sessionStorage.getItem('supplier_token')||'anonymous'):'staff';this.visible=true;}}};
</script>

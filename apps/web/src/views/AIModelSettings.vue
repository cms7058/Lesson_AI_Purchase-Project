<template>
  <div>
    <div class="page-heading">
      <div>
        <h1>AI模型设置</h1>
        <p>
          分别配置采购助手与项目助手的OpenAI兼容模型；两个助手共用对话入口，但底层模型和训练数据相互隔离。
        </p>
      </div>
    </div>
    <el-alert
      title="API密钥加密保存且不回显；模型配置仅对采购经理和管理员开放。请确认所选模型支持图片输入。"
      type="info"
      :closable="false"
    />
    <el-tabs
      v-model="domain"
      style="max-width: 780px; margin-top: 18px"
      @tab-click="load"
    >
      <el-tab-pane label="采购助手模型" name="procurement" />
      <el-tab-pane label="项目助手模型" name="project" />
    </el-tabs>
    <el-alert
      :title="
        domain === 'project'
          ? '项目模型用于进度、任务、成本预警与项目跟踪，可填写项目专有微调模型ID。'
          : '采购模型用于询价、订单、供应商、物料、TOC与库存分析，可填写采购专有微调模型ID。'
      "
      type="warning"
      :closable="false"
      style="max-width: 780px"
    />
    <el-form
      :model="form"
      label-width="150px"
      style="max-width: 780px; margin-top: 24px"
      v-loading="loading"
    >
      <el-form-item label="启用AI模型"
        ><el-switch v-model="form.enabled"
      /></el-form-item>
      <el-form-item label="接口协议"
        ><el-select v-model="form.provider"
          ><el-option
            label="OpenAI兼容接口"
            value="openai_compatible" /></el-select
      ></el-form-item>
      <el-form-item label="API基础地址"
        ><el-input
          v-model.trim="form.base_url"
          placeholder="例如 https://example.com/v1"
        /><small
          >系统会调用
          {基础地址}/chat/completions，请勿填写到具体接口路径。</small
        ></el-form-item
      >
      <el-form-item label="专有模型名称"
        ><el-input
          v-model.trim="form.model"
          placeholder="填写服务商提供的视觉模型ID"
      /></el-form-item>
      <el-form-item label="API密钥"
        ><el-input
          v-model="form.api_key"
          show-password
          autocomplete="new-password"
          :placeholder="
            form.api_key_set ? '已保存，留空保持不变' : '请输入API密钥'
          "
      /></el-form-item>
      <el-form-item
        ><el-button type="primary" :loading="saving" @click="save"
          >保存配置</el-button
        ><el-button :loading="testing" @click="testConnection"
          >测试连接</el-button
        ></el-form-item
      >
    </el-form>
  </div>
</template>
<script>
import { api } from "../api/client";
export default {
  data: () => ({
    domain: "procurement",
    form: {
      enabled: false,
      provider: "openai_compatible",
      base_url: "",
      model: "",
      api_key: "",
      api_key_set: false,
    },
    loading: false,
    saving: false,
    testing: false,
  }),
  created() {
    this.load();
  },
  methods: {
    async load() {
      this.loading = true;
      try {
        this.form = {
          enabled: false,
          provider: "openai_compatible",
          base_url: "",
          model: "",
          api_key_set: false,
          ...(
            await api.get("/ai-model-settings", {
              params: { domain: this.domain },
            })
          ).data,
          api_key: "",
        };
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    error(e) {
      const d = e.response?.data?.detail;
      const message = Array.isArray(d)
        ? d.map((item) => item.msg).join("；")
        : d;
      this.$message.error(
        typeof message === "string" ? message : "操作失败，请检查配置"
      );
    },
    async save() {
      this.saving = true;
      try {
        const result = (
          await api.put("/ai-model-settings", this.form, {
            params: { domain: this.domain },
          })
        ).data;
        this.form = { ...this.form, ...result, api_key: "" };
        this.$message.success("AI模型设置已保存");
      } catch (e) {
        this.error(e);
      } finally {
        this.saving = false;
      }
    },
    async testConnection() {
      this.testing = true;
      try {
        const r = (
          await api.post("/ai-model-settings/test", null, {
            params: { domain: this.domain },
          })
        ).data;
        this.$message.success(`连接成功：${r.model} · ${r.message}`);
      } catch (e) {
        this.error(e);
      } finally {
        this.testing = false;
      }
    },
  },
};
</script>

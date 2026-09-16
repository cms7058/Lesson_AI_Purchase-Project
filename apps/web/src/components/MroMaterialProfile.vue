<template>
  <div v-loading="loading" class="mro-profile-editor">
    <el-alert
      :title="`${material.code} · ${material.name}`"
      description="画像是MRO预测模型的主数据输入；属性可以叠加，系统将据此选择AMOS事件推断、间歇需求或统计预测方法。"
      type="info"
      :closable="false"
      show-icon
    />
    <div class="attribute-preview">
      <strong>当前属性：</strong>
      <span
        v-for="tag in attributes"
        :key="tag.label"
        :style="{ borderColor: tag.color, color: tag.color, background: tag.color + '12' }"
      >{{ tag.label }}</span>
      <em v-if="!attributes.length">一般备件</em>
    </div>
    <el-form label-width="115px">
      <el-row :gutter="14">
        <el-col :span="12">
          <el-form-item label="需求特性">
            <el-select v-model="form.demand_characteristic" style="width:100%">
              <el-option label="稳定需求" value="stable" />
              <el-option label="间歇需求" value="intermittent" />
              <el-option label="块状需求" value="lumpy" />
              <el-option label="计划需求" value="planned" />
              <el-option label="非例行需求" value="non_routine" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="模型覆盖">
            <el-input v-model.trim="form.model_override" placeholder="留空由系统自动选择" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="14">
        <el-col v-for="field in scoreFields" :key="field.key" :span="12">
          <el-form-item :label="field.label">
            <el-rate v-model="form[field.key]" :max="5" show-score />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="组合属性">
        <el-checkbox v-model="form.single_source">单一来源</el-checkbox>
        <el-checkbox v-model="form.long_lead">长交期</el-checkbox>
        <el-checkbox v-model="form.high_value">高价值</el-checkbox>
        <el-checkbox v-model="form.repairable">可修理</el-checkbox>
        <el-checkbox v-model="form.planned">计划需求</el-checkbox>
        <el-checkbox v-model="form.non_routine">非例行需求</el-checkbox>
      </el-form-item>
      <el-form-item label="数据依据">
        <el-input v-model.trim="form.evidence" type="textarea" :rows="3" maxlength="2000" show-word-limit />
      </el-form-item>
    </el-form>
    <div class="editor-actions">
      <el-button type="primary" :loading="saving" @click="save">保存MRO画像</el-button>
    </div>
  </div>
</template>

<script>
import { api } from "../api/client";

const blank = () => ({
  demand_characteristic: "stable",
  aircraft_impact: 3,
  supply_risk: 3,
  lead_time_risk: 3,
  value_level: 3,
  substitutability: 3,
  compliance_risk: 3,
  repairability: 1,
  single_source: false,
  long_lead: false,
  high_value: false,
  planned: true,
  non_routine: false,
  repairable: false,
  model_override: "",
  evidence: "",
});

const colors = {
  停场关键: "#e5484d",
  单一来源: "#f97316",
  长交期: "#7c3aed",
  高价值: "#d89b00",
  可修理件: "#1677ff",
  间歇需求: "#0891b2",
  高合规: "#db2777",
  低可替代: "#475569",
};

export default {
  props: { material: { type: Object, required: true } },
  data: () => ({
    loading: false,
    saving: false,
    form: blank(),
    scoreFields: [
      { key: "aircraft_impact", label: "飞机影响" },
      { key: "supply_risk", label: "供应风险" },
      { key: "lead_time_risk", label: "交期风险" },
      { key: "value_level", label: "价值等级" },
      { key: "substitutability", label: "可替代性" },
      { key: "compliance_risk", label: "合规风险" },
      { key: "repairability", label: "Repair属性" },
    ],
  }),
  computed: {
    attributes() {
      const labels = [];
      if (this.form.aircraft_impact >= 4) labels.push("停场关键");
      if (this.form.single_source) labels.push("单一来源");
      if (this.form.long_lead || this.form.lead_time_risk >= 4) labels.push("长交期");
      if (this.form.high_value || this.form.value_level >= 4) labels.push("高价值");
      if (this.form.repairable || this.form.repairability >= 4) labels.push("可修理件");
      if (["intermittent", "lumpy"].includes(this.form.demand_characteristic)) labels.push("间歇需求");
      if (this.form.compliance_risk >= 4) labels.push("高合规");
      if (this.form.substitutability <= 2) labels.push("低可替代");
      return labels.map(label => ({ label, color: colors[label] }));
    },
  },
  created() { this.load(); },
  methods: {
    async load() {
      this.loading = true;
      try {
        const { data } = await api.get(`/mro-intelligence/profiles/${encodeURIComponent(this.material.code)}`);
        this.form = data ? { ...blank(), ...data } : blank();
      } catch (error) {
        this.$message.error(error.response?.data?.detail || "MRO画像加载失败");
      } finally {
        this.loading = false;
      }
    },
    async save() {
      this.saving = true;
      try {
        const payload = { ...this.form };
        delete payload.material_code;
        delete payload.attributes;
        delete payload.version;
        await api.put(`/mro-intelligence/profiles/${encodeURIComponent(this.material.code)}`, payload);
        this.$message.success("MRO物料画像已保存");
        this.$emit("saved");
      } catch (error) {
        this.$message.error(error.response?.data?.detail || "MRO画像保存失败");
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<style scoped>
.attribute-preview{margin:14px 0;padding:12px;background:#f7f9fc;border:1px solid #e8edf4;border-radius:8px}.attribute-preview span{display:inline-block;margin:2px 5px;padding:2px 8px;border:1px solid;border-radius:12px;font-size:12px}.attribute-preview em{font-style:normal;color:#8190a0}.editor-actions{text-align:right;border-top:1px solid #edf0f4;padding-top:14px}
</style>

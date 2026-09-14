<template>
  <div>
    <el-alert
      v-if="template && template.engine === 'docx_v1'"
      :title="`当前Word模板识别到 ${template.placeholders.length} 个表达式，仅显示该模板使用的自定义字段。`"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else
      title="尚未选择Word模板，显示全部已启用自定义字段。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-empty
      v-if="!visibleFields.length"
      description="当前模板没有使用自定义字段，可前往业务模板中心配置"
      :image-size="70"
    />
    <el-row v-else :gutter="16" class="dynamic-fields">
      <el-col
        v-for="field in visibleFields"
        :key="field.id"
        :span="field.data_type === 'textarea' ? 24 : 12"
      >
        <el-form-item :label="field.name" :required="field.required">
          <el-input
            v-if="field.data_type === 'text'"
            :value="localValues[field.code]"
            @input="setValue(field.code, $event)"
            :placeholder="
              field.source_path === 'manual'
                ? '请输入'
                : '数据来源：' + field.source_path
            "
          />
          <el-input
            v-else-if="field.data_type === 'textarea'"
            :value="localValues[field.code]"
            @input="setValue(field.code, $event)"
            type="textarea"
            :rows="3"
          />
          <el-input-number
            v-else-if="
              field.data_type === 'number' || field.data_type === 'amount'
            "
            :value="localValues[field.code]"
            @input="setValue(field.code, $event)"
            :precision="field.data_type === 'amount' ? 2 : 0"
            controls-position="right"
            style="width: 100%"
          />
          <el-date-picker
            v-else-if="field.data_type === 'date'"
            :value="localValues[field.code]"
            @input="setValue(field.code, $event)"
            type="date"
            value-format="yyyy-MM-dd"
            style="width: 100%"
          />
          <el-select
            v-else-if="field.data_type === 'select'"
            :value="localValues[field.code]"
            @input="setValue(field.code, $event)"
            style="width: 100%"
            ><el-option
              v-for="option in field.options"
              :key="option"
              :label="option"
              :value="option"
          /></el-select>
          <el-switch
            v-else-if="field.data_type === 'boolean'"
            :value="localValues[field.code]"
            @input="setValue(field.code, $event)"
          />
          <div class="field-meta">
            <code>{{ placeholder(field.code) }}</code
            ><span>{{ field.source_path || "manual" }}</span>
          </div>
        </el-form-item>
      </el-col>
    </el-row>
  </div>
</template>
<script>
import { fetchContractFields, fetchTemplates } from "../api/client";
export default {
  props: {
    value: { type: Object, required: true },
    templateId: { type: String, default: "" },
  },
  data() {
    return { fields: [], templates: [], localValues: { ...this.value } };
  },
  computed: {
    template() {
      return this.templates.find((item) => item.id === this.templateId) || null;
    },
    visibleFields() {
      if (!this.template || this.template.engine !== "docx_v1")
        return this.fields;
      const placeholders = this.template.placeholders || [];
      return this.fields.filter((field) => placeholders.includes(field.code));
    },
  },
  watch: {
    visibleFields: {
      immediate: true,
      handler(fields) {
        fields.forEach((field) => {
          if (this.localValues[field.code] === undefined)
            this.setValue(field.code, this.initialValue(field));
        });
      },
    },
  },
  async created() {
    const [fields, templates] = await Promise.all([
      fetchContractFields({ page: 1, page_size: 100, active: true }),
      fetchTemplates({ page: 1, page_size: 100, unfiltered: true }),
    ]);
    this.fields = fields.items;
    this.templates = templates.items;
  },
  methods: {
    placeholder(code) {
      return "{{ " + code + " }}";
    },
    setValue(code, value) {
      this.$set(this.localValues, code, value);
      this.$emit("input", { ...this.localValues });
    },
    initialValue(field) {
      if (field.data_type === "number" || field.data_type === "amount")
        return Number(field.default_value || 0);
      if (field.data_type === "boolean")
        return ["true", "1", "是"].includes(
          String(field.default_value).toLowerCase()
        );
      return field.default_value || "";
    },
  },
};
</script>
<style scoped>
.dynamic-fields {
  margin-top: 18px;
}
.field-meta {
  display: flex;
  justify-content: space-between;
  color: #94a3b8;
  font-size: 12px;
  line-height: 20px;
}
.field-meta code {
  color: #2563eb;
}
</style>

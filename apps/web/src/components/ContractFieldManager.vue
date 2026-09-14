<template>
  <div>
    <div class="field-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索字段编码或名称"
        @keyup.enter.native="load"
      /><el-button icon="el-icon-search" @click="load">查询</el-button
      ><el-button type="success" @click="generateTemplate"
        >按启用字段生成Word模板</el-button
      ><el-button type="primary" @click="openCreate">新增字段</el-button>
    </div>
    <el-alert
      :title="'字段编码就是Word占位符，例如字段编码 delivery_contact 对应 {{ delivery_contact }}。字段变化后，系统生成型模板会自动同步。'"
      type="info"
      :closable="false"
      show-icon
    />
    <el-table
      :data="items"
      size="mini"
      class="dialog-form-spaced"
      max-height="430"
    >
      <el-table-column
        prop="name"
        label="字段名称"
        min-width="130"
      /><el-table-column prop="code" label="字段编码" min-width="140"
        ><template slot-scope="s"
          ><code>{{ s.row.code }}</code></template
        ></el-table-column
      ><el-table-column
        prop="category"
        label="分组"
        width="100"
      /><el-table-column label="类型" width="90"
        ><template slot-scope="s">{{
          typeName(s.row.data_type)
        }}</template></el-table-column
      ><el-table-column
        prop="source_path"
        label="数据来源"
        min-width="130"
      /><el-table-column label="必填" width="65"
        ><template slot-scope="s">{{
          s.row.required ? "是" : "否"
        }}</template></el-table-column
      ><el-table-column label="状态" width="80"
        ><template slot-scope="s"
          ><el-tag size="mini" :type="s.row.active ? 'success' : 'info'">{{
            s.row.active ? "启用" : "停用"
          }}</el-tag></template
        ></el-table-column
      ><el-table-column label="操作" width="145"
        ><template slot-scope="s"
          ><el-button type="text" @click="edit(s.row)">编辑</el-button
          ><el-button
            v-if="s.row.active"
            type="text"
            class="danger-link"
            @click="deactivate(s.row)"
            >停用</el-button
          ><el-button v-else type="text" @click="enable(s.row)"
            >启用</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <div class="pagination-row">
      <span>共 {{ total }} 条</span
      ><el-pagination
        small
        layout="prev,pager,next"
        :page-size="20"
        :total="total"
        @current-change="changePage"
      />
    </div>
    <el-dialog
      :title="editingId ? '编辑合同字段' : '新增合同字段'"
      :visible.sync="editVisible"
      width="650px"
      append-to-body
      :close-on-click-modal="false"
      ><el-form :model="form" label-width="100px"
        ><el-row :gutter="12"
          ><el-col :span="12"
            ><el-form-item label="字段名称" required
              ><el-input v-model.trim="form.name" /></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="字段编码" required
              ><el-input
                v-model.trim="form.code"
                :disabled="Boolean(editingId)"
                placeholder="英文小写及下划线" /></el-form-item></el-col></el-row
        ><el-row :gutter="12"
          ><el-col :span="12"
            ><el-form-item label="字段分组"
              ><el-input v-model.trim="form.category" /></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="字段类型"
              ><el-select v-model="form.data_type" style="width: 100%"
                ><el-option
                  v-for="item in typeOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="
                    item.value
                  " /></el-select></el-form-item></el-col></el-row
        ><el-row :gutter="12"
          ><el-col :span="12"
            ><el-form-item label="数据来源"
              ><el-input
                v-model.trim="form.source_path"
                placeholder="manual 或 supplier.contact" /></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="排序"
              ><el-input-number
                v-model="form.sort_order"
                :min="0"
                style="width: 100%" /></el-form-item></el-col></el-row
        ><el-form-item v-if="form.data_type === 'select'" label="下拉选项"
          ><el-input
            v-model="optionsText"
            placeholder="多个选项用逗号分隔" /></el-form-item
        ><el-form-item label="默认值"
          ><el-input v-model="form.default_value" /></el-form-item
        ><el-form-item label="设置"
          ><el-checkbox v-model="form.required">必填字段</el-checkbox
          ><el-checkbox v-model="form.active">启用</el-checkbox></el-form-item
        ></el-form
      ><span slot="footer"
        ><el-button @click="editVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存字段</el-button
        ></span
      ></el-dialog
    >
  </div>
</template>
<script>
import {
  createContractField,
  deactivateContractField,
  fetchContractFields,
  generateManagedContractTemplate,
  updateContractField,
} from "../api/client";
const empty = () => ({
  name: "",
  code: "",
  category: "其他要素",
  data_type: "text",
  source_path: "manual",
  default_value: "",
  required: false,
  active: true,
  sort_order: 100,
  options: [],
});
export default {
  data: () => ({
    items: [],
    total: 0,
    page: 1,
    keyword: "",
    editVisible: false,
    editingId: "",
    form: empty(),
    optionsText: "",
    saving: false,
    typeOptions: [
      { label: "单行文本", value: "text" },
      { label: "多行文本", value: "textarea" },
      { label: "数字", value: "number" },
      { label: "金额", value: "amount" },
      { label: "日期", value: "date" },
      { label: "下拉选项", value: "select" },
      { label: "是/否", value: "boolean" },
    ],
  }),
  created() {
    this.load();
  },
  methods: {
    typeName(value) {
      return (
        this.typeOptions.find((item) => item.value === value)?.label || value
      );
    },
    async load() {
      const result = await fetchContractFields({
        page: this.page,
        page_size: 20,
        keyword: this.keyword,
      });
      this.items = result.items;
      this.total = result.total;
    },
    changePage(page) {
      this.page = page;
      this.load();
    },
    openCreate() {
      this.editingId = "";
      this.form = empty();
      this.optionsText = "";
      this.editVisible = true;
    },
    edit(row) {
      this.editingId = row.id;
      this.form = { ...row };
      this.optionsText = (row.options || []).join(",");
      this.editVisible = true;
    },
    async save() {
      if (!this.form.name || !this.form.code)
        return this.$message.warning("请填写字段名称和编码");
      this.saving = true;
      try {
        const payload = {
          ...this.form,
          options: this.optionsText
            .split(/[,，]/)
            .map((v) => v.trim())
            .filter(Boolean),
        };
        if (this.editingId) {
          delete payload.code;
          await updateContractField(this.editingId, payload);
        } else await createContractField(payload);
        this.$message.success("字段已保存，相关模板已重新校验");
        this.editVisible = false;
        await this.load();
        this.$emit("changed");
      } catch (error) {
        this.$message.error(error.response?.data?.detail || "字段保存失败");
      } finally {
        this.saving = false;
      }
    },
    async deactivate(row) {
      await this.$confirm(
        `停用字段 ${row.name} 后，引用它的模板将标记为待修正，是否继续？`,
        "停用字段",
        { type: "warning" }
      );
      await deactivateContractField(row.id);
      await this.load();
      this.$emit("changed");
    },
    async enable(row) {
      await updateContractField(row.id, { active: true });
      await this.load();
      this.$emit("changed");
    },
    async generateTemplate() {
      try {
        const { value } = await this.$prompt(
          "请输入新模板名称",
          "按启用字段生成Word模板",
          {
            inputValue: "自定义采购合同模板",
            inputValidator: (value) => value.length >= 2 || "至少输入2个字符",
          }
        );
        await generateManagedContractTemplate({
          name: value,
          version: "1.0",
          field_ids: this.items
            .filter((item) => item.active)
            .map((item) => item.id),
        });
        this.$message.success("标准Word模板已生成，后续字段修改会自动同步");
        this.$emit("changed");
      } catch (error) {
        if (error !== "cancel")
          this.$message.error(error.response?.data?.detail || "模板生成失败");
      }
    },
  },
};
</script>
<style scoped>
.field-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.field-toolbar .el-input {
  max-width: 260px;
}
</style>

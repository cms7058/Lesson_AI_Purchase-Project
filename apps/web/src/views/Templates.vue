<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">文档自动化</p>
        <h1>业务模板中心</h1>
        <p>
          维护文本模板和企业Word合同模板，校验字段后基于结构化业务数据生成正式文件。
        </p>
      </div>
      <div>
        <el-button
          type="primary"
          plain
          @click="fieldManagerVisible = true"
          >合同字段配置</el-button
        ><el-button @click="fieldVisible = true">合同字段字典</el-button
        ><el-button @click="openCompany">公司标识</el-button
        ><el-button
          type="success"
          icon="el-icon-upload2"
          @click="wordVisible = true"
          >上传Word合同模板</el-button
        ><el-button type="primary" @click="openCreate">新建文本模板</el-button>
      </div>
    </div>
    <div class="template-note">
      <strong>订单可用字段</strong><code v-pre>{{ order_no }}</code
      ><code v-pre>{{ supplier_name }}</code
      ><code v-pre>{{ factory_code }}</code
      ><code v-pre>{{ material_name }}</code
      ><code v-pre>{{ quantity }}</code
      ><code v-pre>{{ unit_price }}</code>
    </div>
    <el-table :data="templates" class="data-table" empty-text="还没有业务模板">
      <el-table-column prop="name" label="模板名称" min-width="180" />
      <el-table-column prop="template_type" label="类型" width="120"
        ><template slot-scope="scope"
          ><el-tag>{{ typeName(scope.row.template_type) }}</el-tag></template
        ></el-table-column
      >
      <el-table-column prop="version" label="版本" width="90" /><el-table-column
        label="模板引擎"
        width="120"
        ><template slot-scope="scope"
          ><el-tag
            size="mini"
            :type="scope.row.engine === 'docx_v1' ? 'success' : 'info'"
            >{{
              scope.row.engine === "docx_v1" ? "Word模板" : "文本模板"
            }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column label="校验" width="100"
        ><template slot-scope="scope"
          ><span v-if="scope.row.engine === 'text_v1'">—</span
          ><el-tag
            v-else
            size="mini"
            :type="
              scope.row.validation_status === 'validated' ? 'success' : 'danger'
            "
            >{{
              scope.row.validation_status === "validated" ? "已通过" : "未通过"
            }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column prop="created_by" label="维护人" width="130" />
      <el-table-column label="操作" width="300"
        ><template slot-scope="scope"
          ><template v-if="scope.row.engine === 'docx_v1'"
            ><el-button type="text" @click="showValidation(scope.row)"
              >校验报告</el-button
            ><el-button type="text" @click="downloadWord(scope.row)"
              >下载原件</el-button
            ></template
          ><el-button
            v-else
            type="text"
            :disabled="scope.row.template_type !== 'order'"
            @click="openRender(scope.row)"
            >订单填充</el-button
          ><el-button
            v-if="scope.row.engine === 'text_v1'"
            type="text"
            @click="edit(scope.row)"
            >编辑</el-button
          ><el-button type="text" class="danger-link" @click="remove(scope.row)"
            >删除</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <div class="pagination-row">
      <span>共 {{ pagination.total }} 条</span
      ><el-pagination
        background
        layout="sizes, prev, pager, next"
        :page-sizes="[10, 20, 50]"
        :current-page="pagination.page"
        :page-size="pagination.page_size"
        :total="pagination.total"
        @current-change="changePage"
        @size-change="changeSize"
      />
    </div>
    <el-dialog
      :title="editingId ? '编辑业务模板' : '新建业务模板'"
      :visible.sync="dialogVisible"
      width="680px"
      ><el-form :model="form" label-width="90px"
        ><el-form-item label="模板名称"
          ><el-input v-model="form.name" /></el-form-item
        ><el-row :gutter="14"
          ><el-col :span="12"
            ><el-form-item label="类型"
              ><el-select
                v-model="form.template_type"
                :disabled="Boolean(editingId)"
                style="width: 100%"
                ><el-option label="订单模板" value="order" /><el-option
                  label="报价单模板"
                  value="quotation" /><el-option
                  label="合同模板"
                  value="contract" /></el-select></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="版本"
              ><el-input
                v-model="form.version" /></el-form-item></el-col></el-row
        ><el-form-item label="模板正文"
          ><el-input
            v-model="form.content"
            type="textarea"
            :rows="9"
            placeholder="输入模板正文，可使用上方订单字段" /></el-form-item></el-form
      ><span slot="footer"
        ><el-button @click="dialogVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save">{{
          editingId ? "保存修改" : "保存模板"
        }}</el-button></span
      ></el-dialog
    >
    <el-dialog
      title="上传Word合同模板"
      :visible.sync="wordVisible"
      width="650px"
      :close-on-click-modal="false"
      ><el-alert
        title="仅支持未加密的DOCX；系统会检查宏、嵌入对象、外部链接和模板字段。"
        type="info"
        :closable="false"
        show-icon
      /><el-form
        :model="wordForm"
        label-width="100px"
        class="dialog-form-spaced"
        ><el-form-item label="模板名称" required
          ><el-input
            v-model.trim="wordForm.name"
            placeholder="例如：设备采购合同标准版" /></el-form-item
        ><el-form-item label="版本" required
          ><el-input v-model.trim="wordForm.version" /></el-form-item
        ><el-form-item label="Word文件" required
          ><el-upload
            action="#"
            :auto-upload="false"
            :limit="1"
            accept=".docx"
            :on-change="selectWord"
            :on-remove="removeWord"
            ><el-button icon="el-icon-document-add">选择DOCX文件</el-button>
            <div slot="tip" class="el-upload__tip">
              建议先下载字段字典，并在Word表格中设置明细循环行。
            </div></el-upload
          ></el-form-item
        ></el-form
      ><span slot="footer"
        ><el-button @click="wordVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="uploadWord"
          >上传并校验</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="Word模板校验报告"
      :visible.sync="validationVisible"
      width="720px"
      ><div v-if="validationReport">
        <el-alert
          :title="
            validationReport.valid ? '模板结构校验通过' : '模板校验未通过'
          "
          :type="validationReport.valid ? 'success' : 'error'"
          :closable="false"
          show-icon
        />
        <h4>识别字段（{{ validationReport.placeholders.length }}）</h4>
        <div class="template-note">
          <code v-for="field in validationReport.placeholders" :key="field">{{
            field
          }}</code
          ><span v-if="!validationReport.placeholders.length">未识别字段</span>
        </div>
        <el-alert
          v-if="validationReport.unknown_placeholders.length"
          title="非标准字段"
          type="warning"
          :description="validationReport.unknown_placeholders.join('、')"
          :closable="false"
        />
        <ul v-if="validationReport.warnings.length">
          <li v-for="item in validationReport.warnings" :key="item">
            {{ item }}
          </li>
        </ul>
      </div></el-dialog
    >
    <el-dialog
      title="合同Word模板字段字典"
      :visible.sync="fieldVisible"
      width="820px"
      ><el-alert
        :title="'简单字段写作 {{ 字段名 }}；物料明细请使用示例模板中的表格循环控制行。'"
        type="info"
        :closable="false"
        show-icon
      /><el-table :data="contractFields" size="mini" class="dialog-form-spaced"
        ><el-table-column
          prop="category"
          label="分类"
          width="120" /><el-table-column
          prop="field"
          label="模板字段"
          width="230"
          ><template slot-scope="s"
            ><code>{{ s.row.field }}</code></template
          ></el-table-column
        ><el-table-column prop="description" label="说明" /></el-table
      ><span slot="footer"
        ><el-button @click="downloadSample">下载标准示例模板</el-button
        ><el-button type="primary" @click="fieldVisible = false"
          >关闭</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="合同字段配置"
      :visible.sync="fieldManagerVisible"
      width="1050px"
      top="4vh"
      :close-on-click-modal="false"
      ><contract-field-manager v-if="fieldManagerVisible" @changed="load"
    /></el-dialog>
    <el-dialog
      title="公司名称与 Logo"
      :visible.sync="companyVisible"
      width="540px"
      ><el-form :model="company" label-width="100px"
        ><el-form-item label="公司名称"
          ><el-input v-model="company.company_name" /></el-form-item
        ><el-form-item label="简称"
          ><el-input v-model="company.short_name" /></el-form-item
        ><el-form-item label="地址"
          ><el-input v-model="company.address" /></el-form-item
        ><el-form-item label="联系方式"
          ><el-input v-model="company.contact" /></el-form-item
        ><el-form-item label="Logo"
          ><el-upload
            action="#"
            :show-file-list="false"
            :http-request="uploadLogo"
            accept="image/png,image/jpeg"
            ><el-button size="small">上传 PNG/JPEG</el-button></el-upload
          ><img
            v-if="company.logo_path"
            :src="company.logo_path"
            class="company-logo" /></el-form-item></el-form
      ><span slot="footer"
        ><el-button @click="companyVisible = false">取消</el-button
        ><el-button type="primary" @click="saveCompany"
          >保存公司标识</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="生成订单文档预览"
      :visible.sync="renderVisible"
      width="760px"
      ><div v-if="rendering" class="preview-empty">正在填充模板…</div>
      <div v-else-if="rendered" class="document-preview">
        <div class="preview-meta">
          <el-tag type="success">{{ rendered.template_name }}</el-tag
          ><span
            >已替换 {{ rendered.placeholders_replaced.length }} 个字段</span
          >
        </div>
        <pre>{{ rendered.content }}</pre>
        <el-alert
          v-if="rendered.placeholders_unresolved.length"
          title="以下字段没有匹配到订单数据"
          type="warning"
          :closable="false"
          :description="rendered.placeholders_unresolved.join(', ')"
        />
      </div>
      <div v-else class="render-selector">
        <p>选择要填充的采购订单：</p>
        <el-select
          v-model="selectedOrderId"
          placeholder="选择订单"
          style="width: 100%"
          ><el-option
            v-for="order in orders"
            :key="order.id"
            :label="`${order.order_no} · ${order.supplier_name}`"
            :value="order.id" /></el-select
        ><el-button type="primary" :disabled="!selectedOrderId" @click="render"
          >生成预览</el-button
        >
      </div></el-dialog
    >
  </div>
</template>

<script>
import {
  createTemplate,
  deleteTemplate,
  fetchCompanyProfile,
  fetchOrders,
  fetchTemplates,
  fetchTemplateValidation,
  renderOrderTemplate,
  updateCompanyProfile,
  updateTemplate,
  uploadCompanyLogo,
  uploadWordContractTemplate,
} from "../api/client";
const emptyForm = () => ({
  name: "",
  template_type: "order",
  version: "1.0",
  content:
    "采购订单 {{order_no}}\n供应商：{{supplier_name}}\n收货工厂：{{factory_code}}\n物料：{{material_name}}\n数量：{{quantity}} {{unit}}\n单价：{{unit_price}}",
});
export default {
  data: () => ({
    templates: [],
    orders: [],
    form: emptyForm(),
    dialogVisible: false,
    saving: false,
    renderVisible: false,
    templateForRender: null,
    selectedOrderId: "",
    rendered: null,
    rendering: false,
    fieldHint: "{{field}}",
    editingId: "",
    pagination: { page: 1, page_size: 10, total: 0 },
    companyVisible: false,
    company: {
      company_name: "",
      short_name: "",
      address: "",
      contact: "",
      logo_path: "",
    },
    wordVisible: false,
    wordForm: { name: "", version: "1.0", file: null },
    validationVisible: false,
    validationReport: null,
    fieldVisible: false,
    fieldManagerVisible: false,
    contractFields: [
      { category: "合同", field: "{{ contract_no }}", description: "合同编号" },
      {
        category: "合同",
        field: "{{ contract_title }}",
        description: "合同名称",
      },
      {
        category: "主体",
        field: "{{ buyer.company_name }}",
        description: "采购方公司名称",
      },
      {
        category: "主体",
        field: "{{ supplier.company_name }}",
        description: "供应商名称",
      },
      { category: "商务", field: "{{ currency }}", description: "币种" },
      {
        category: "商务",
        field: "{{ total_amount }}",
        description: "后端核算的含税总额",
      },
      {
        category: "交付",
        field: "{{ delivery_address }}",
        description: "交货地点",
      },
      {
        category: "商务",
        field: "{{ payment_terms }}",
        description: "付款条件",
      },
      {
        category: "物料循环",
        field: "{%tr for item in items %}",
        description: "明细循环开始控制行",
      },
      {
        category: "物料循环",
        field: "{{ item.material_code }}",
        description: "物料编码",
      },
      {
        category: "物料循环",
        field: "{{ item.line_total }}",
        description: "明细含税金额",
      },
      {
        category: "物料循环",
        field: "{%tr endfor %}",
        description: "明细循环结束控制行",
      },
    ],
  }),
  async created() {
    await Promise.all([this.load(), this.loadOrders()]);
  },
  methods: {
    typeName(type) {
      return (
        { order: "订单", quotation: "报价单", contract: "合同" }[type] || type
      );
    },
    async load() {
      try {
        const result = await fetchTemplates({
          page: this.pagination.page,
          page_size: this.pagination.page_size,
        });
        this.templates = result.items;
        this.pagination.total = result.total;
      } catch (_) {
        this.$message.warning("请先启动后端API");
      }
    },
    async loadOrders() {
      const result = await fetchOrders({
        page: 1,
        page_size: 100,
        unfiltered: true,
      });
      this.orders = result.items;
    },
    changePage(page) {
      this.pagination.page = page;
      this.load();
    },
    changeSize(size) {
      this.pagination.page_size = size;
      this.pagination.page = 1;
      this.load();
    },
    openCreate() {
      this.editingId = "";
      this.form = emptyForm();
      this.dialogVisible = true;
    },
    edit(template) {
      this.editingId = template.id;
      this.form = {
        name: template.name,
        template_type: template.template_type,
        version: template.version,
        content: template.content,
      };
      this.dialogVisible = true;
    },
    async remove(template) {
      try {
        await this.$confirm(`确定删除模板 ${template.name} 吗？`, "删除确认", {
          type: "warning",
        });
        await deleteTemplate(template.id);
        this.$message.success("模板已删除");
        await this.load();
      } catch (error) {
        if (error !== "cancel")
          this.$message.error(error.response?.data?.detail || "模板删除失败");
      }
    },
    async save() {
      this.saving = true;
      try {
        if (this.editingId)
          await updateTemplate(this.editingId, {
            name: this.form.name,
            version: this.form.version,
            content: this.form.content,
          });
        else await createTemplate(this.form);
        this.$message.success(this.editingId ? "模板已更新" : "模板已发布");
        this.dialogVisible = false;
        this.form = emptyForm();
        this.editingId = "";
        await this.load();
      } catch (error) {
        this.$message.error(
          error.response?.data?.detail?.[0]?.msg || "模板保存失败"
        );
      } finally {
        this.saving = false;
      }
    },
    selectWord(file) {
      this.wordForm.file = file.raw;
      if (!this.wordForm.name)
        this.wordForm.name = file.name.replace(/\.docx$/i, "");
    },
    removeWord() {
      this.wordForm.file = null;
    },
    async uploadWord() {
      if (!this.wordForm.name || !this.wordForm.file)
        return this.$message.warning("请填写模板名称并选择DOCX文件");
      this.saving = true;
      try {
        const result = await uploadWordContractTemplate(this.wordForm);
        this.$message.success("Word模板上传并校验通过");
        this.wordVisible = false;
        this.wordForm = { name: "", version: "1.0", file: null };
        await this.load();
        await this.showValidation(result);
      } catch (error) {
        this.$message.error(error.response?.data?.detail || "Word模板上传失败");
      } finally {
        this.saving = false;
      }
    },
    async showValidation(template) {
      try {
        this.validationReport = await fetchTemplateValidation(template.id);
        this.validationVisible = true;
      } catch (error) {
        this.$message.error(error.response?.data?.detail || "读取校验报告失败");
      }
    },
    downloadWord(template) {
      window.open(
        `${process.env.VUE_APP_API_BASE_URL || "/api/v1"}/templates/${
          template.id
        }/file`,
        "_blank",
        "noopener"
      );
    },
    downloadSample() {
      window.open(
        `${
          process.env.VUE_APP_API_BASE_URL || "/api/v1"
        }/templates/word-contract/sample`,
        "_blank",
        "noopener"
      );
    },
    async openCompany() {
      this.company = await fetchCompanyProfile();
      this.companyVisible = true;
    },
    async saveCompany() {
      this.company = await updateCompanyProfile(this.company);
      this.$message.success("公司标识已保存");
      this.companyVisible = false;
    },
    async uploadLogo({ file }) {
      try {
        this.company = await uploadCompanyLogo(file);
        this.$message.success("Logo 已上传");
      } catch (_) {
        this.$message.error("Logo 上传失败");
      }
    },
    openRender(template) {
      this.templateForRender = template;
      this.selectedOrderId = this.orders[0]?.id || "";
      this.rendered = null;
      this.renderVisible = true;
    },
    async render() {
      this.rendering = true;
      try {
        this.rendered = await renderOrderTemplate(
          this.templateForRender.id,
          this.selectedOrderId
        );
      } catch (error) {
        this.$message.error(error.response?.data?.detail || "文档生成失败");
      } finally {
        this.rendering = false;
      }
    },
  },
};
</script>

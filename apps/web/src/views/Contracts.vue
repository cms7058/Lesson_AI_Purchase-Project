<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">CONTRACT LIFECYCLE</p>
        <h1>合同管理</h1>
        <p>
          从合同起草、模板套用、审批生效，到文件生成与履约终止形成完整闭环。
        </p>
      </div>
      <el-button type="primary" @click="openCreate">新建合同</el-button>
    </div>
    <div class="process-strip">
      <span>1. 合同起草</span><i>→</i><span>2. 套用企业模板</span><i>→</i
      ><span>3. 审批生效</span><i>→</i><span>4. 文件导出与履约</span>
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索合同编号、名称或供应商"
        @keyup.enter.native="search"
        @clear="search"
      /><el-select
        v-model="statusFilter"
        clearable
        placeholder="全部状态"
        @change="search"
        ><el-option
          v-for="item in statusOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value" /></el-select
      ><el-button icon="el-icon-search" @click="search">查询</el-button
      ><el-button @click="reset">重置</el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="contracts"
      class="data-table"
      empty-text="尚无合同"
    >
      <el-table-column
        prop="contract_no"
        label="合同编号"
        width="145"
      /><el-table-column
        prop="title"
        label="合同名称"
        min-width="180"
      /><el-table-column
        prop="supplier_name"
        label="供应商"
        min-width="150"
      /><el-table-column prop="amount" label="合同金额" width="140"
        ><template slot-scope="scope"
          >{{ scope.row.currency }} {{ money(scope.row.amount) }}</template
        ></el-table-column
      ><el-table-column label="有效期" width="190"
        ><template slot-scope="scope"
          >{{ scope.row.effective_date || "-" }} 至
          {{ scope.row.expiry_date || "-" }}</template
        ></el-table-column
      ><el-table-column label="模板" width="100"
        ><template slot-scope="scope"
          ><el-tag
            size="mini"
            :type="scope.row.template_id ? 'success' : 'info'"
            >{{ scope.row.template_id ? "已关联" : "未关联" }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column label="状态" width="100"
        ><template slot-scope="scope"
          ><el-tag :type="statusType(scope.row.status)">{{
            statusName(scope.row.status)
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="操作" width="380" fixed="right"
        ><template slot-scope="scope"
          ><el-button type="text" @click="openReview(scope.row)"
            >AI审查</el-button
          ><el-button
            v-if="scope.row.status === 'draft'"
            type="text"
            @click="edit(scope.row)"
            >编辑</el-button
          ><el-button
            v-if="scope.row.status === 'draft'"
            type="text"
            @click="submit(scope.row)"
            >提交审批</el-button
          ><el-button
            v-if="scope.row.status === 'pending_approval'"
            type="text"
            @click="openDecision(scope.row)"
            >审批</el-button
          ><el-button
            v-if="scope.row.template_id"
            type="text"
            @click="openExport(scope.row)"
            >生成文件</el-button
          ><el-button type="text" @click="openHistory(scope.row)"
            >生成记录</el-button
          ><el-button
            v-if="scope.row.status === 'active'"
            type="text"
            class="danger-link"
            @click="terminate(scope.row)"
            >终止</el-button
          ><el-button
            v-if="scope.row.status === 'draft'"
            type="text"
            class="danger-link"
            @click="remove(scope.row)"
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
      :title="editingId ? '编辑合同要素' : '新建合同要素'"
      :visible.sync="dialogVisible"
      width="1080px"
      top="3vh"
      :close-on-click-modal="false"
      ><el-form ref="form" :model="form" :rules="rules" label-width="105px"
        ><el-tabs v-model="formTab"
          ><el-tab-pane label="基本与主体" name="base"
            ><el-form-item label="合同名称" prop="title"
              ><el-input v-model.trim="form.title" /></el-form-item
            ><el-row :gutter="14"
              ><el-col :span="12"
                ><el-form-item label="供应商名称" prop="supplier_name"
                  ><el-input
                    v-model.trim="form.supplier_name" /></el-form-item></el-col
              ><el-col :span="12"
                ><el-form-item label="供应商编码" prop="supplier_id"
                  ><el-input
                    v-model.trim="
                      form.supplier_id
                    " /></el-form-item></el-col></el-row
            ><el-row :gutter="14"
              ><el-col :span="8"
                ><el-form-item label="合同类型"
                  ><el-select
                    v-model="form.elements.contract_type"
                    style="width: 100%"
                    ><el-option label="采购合同" value="purchase" /><el-option
                      label="框架协议"
                      value="framework" /><el-option
                      label="服务合同"
                      value="service" /></el-select></el-form-item></el-col
              ><el-col :span="8"
                ><el-form-item label="所属项目"
                  ><el-input
                    v-model.trim="
                      form.elements.project_name
                    " /></el-form-item></el-col
              ><el-col :span="8"
                ><el-form-item label="合同模板"
                  ><el-select
                    v-model="form.template_id"
                    clearable
                    style="width: 100%"
                    placeholder="选择已校验模板"
                    ><el-option
                      v-for="item in contractTemplates"
                      :key="item.id"
                      :label="`${item.name} v${item.version}${
                        item.engine === 'docx_v1' ? ' · Word' : ''
                      }`"
                      :value="
                        item.id
                      " /></el-select></el-form-item></el-col></el-row
            ><el-row :gutter="14"
              ><el-col :span="8"
                ><el-form-item label="生效日期"
                  ><el-date-picker
                    v-model="form.effective_date"
                    type="date"
                    value-format="yyyy-MM-dd"
                    style="width: 100%" /></el-form-item></el-col
              ><el-col :span="8"
                ><el-form-item label="失效日期"
                  ><el-date-picker
                    v-model="form.expiry_date"
                    type="date"
                    value-format="yyyy-MM-dd"
                    style="width: 100%" /></el-form-item></el-col
              ><el-col :span="8"
                ><el-form-item label="签署日期"
                  ><el-date-picker
                    v-model="form.elements.signing_date"
                    type="date"
                    value-format="yyyy-MM-dd"
                    style="
                      width: 100%;
                    " /></el-form-item></el-col></el-row></el-tab-pane
          ><el-tab-pane label="采购明细" name="items"
            ><div class="contract-items-head">
              <el-alert
                title="含税合同总额由系统按数量、未税单价和税率重新核算。"
                type="info"
                :closable="false"
                show-icon
              /><el-button
                type="primary"
                plain
                icon="el-icon-plus"
                @click="addItem"
                >添加物料</el-button
              >
            </div>
            <el-table :data="form.items" border size="mini"
              ><el-table-column label="物料编码" min-width="125"
                ><template slot-scope="s"
                  ><el-input
                    v-model.trim="
                      s.row.material_code
                    " /></template></el-table-column
              ><el-table-column label="名称" min-width="130"
                ><template slot-scope="s"
                  ><el-input
                    v-model.trim="
                      s.row.material_name
                    " /></template></el-table-column
              ><el-table-column label="规格" min-width="110"
                ><template slot-scope="s"
                  ><el-input
                    v-model.trim="
                      s.row.specification
                    " /></template></el-table-column
              ><el-table-column label="数量" width="105"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.quantity"
                    :min="0"
                    :precision="2"
                    :controls="false"
                    style="width: 100%"
                    @change="recalculate" /></template></el-table-column
              ><el-table-column label="单位" width="75"
                ><template slot-scope="s"
                  ><el-input
                    v-model.trim="s.row.unit" /></template></el-table-column
              ><el-table-column label="未税单价" width="120"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.unit_price"
                    :min="0"
                    :precision="2"
                    :controls="false"
                    style="width: 100%"
                    @change="recalculate" /></template></el-table-column
              ><el-table-column label="税率%" width="95"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.tax_rate"
                    :min="0"
                    :max="100"
                    :controls="false"
                    style="width: 100%"
                    @change="recalculate" /></template></el-table-column
              ><el-table-column label="操作" width="60"
                ><template slot-scope="s"
                  ><el-button
                    type="text"
                    class="danger-link"
                    @click="removeItem(s.$index)"
                    >删除</el-button
                  ></template
                ></el-table-column
              ></el-table
            >
            <div class="contract-total">
              系统核算含税总额：<strong>{{ money(form.amount) }}</strong>
              {{ form.currency }}
            </div></el-tab-pane
          ><el-tab-pane label="交付与商务" name="delivery"
            ><el-row :gutter="14"
              ><el-col :span="12"
                ><el-form-item label="交货地点"
                  ><el-input
                    v-model.trim="
                      form.elements.delivery_address
                    " /></el-form-item></el-col
              ><el-col :span="12"
                ><el-form-item label="运输方式"
                  ><el-input
                    v-model.trim="
                      form.elements.transport_method
                    " /></el-form-item></el-col></el-row
            ><el-form-item label="验收标准"
              ><el-input
                v-model="form.elements.acceptance_standard"
                type="textarea"
                :rows="2" /></el-form-item
            ><el-row :gutter="14"
              ><el-col :span="12"
                ><el-form-item label="付款条件"
                  ><el-input
                    v-model.trim="
                      form.elements.payment_terms
                    " /></el-form-item></el-col
              ><el-col :span="12"
                ><el-form-item label="发票类型"
                  ><el-input
                    v-model.trim="
                      form.elements.invoice_type
                    " /></el-form-item></el-col></el-row
            ><el-form-item label="质量标准"
              ><el-input
                v-model="form.elements.quality_standard"
                type="textarea"
                :rows="2" /></el-form-item
            ><el-form-item label="质保与服务"
              ><el-input
                v-model="form.elements.warranty_period"
                type="textarea"
                :rows="2" /></el-form-item></el-tab-pane
          ><el-tab-pane label="自定义要素" name="custom"
            ><contract-dynamic-fields
              v-model="form.elements"
              :template-id="form.template_id || ''" /></el-tab-pane
          ><el-tab-pane label="法律与其他" name="legal"
            ><el-form-item label="违约责任"
              ><el-input
                v-model="form.elements.breach_liability"
                type="textarea"
                :rows="2" /></el-form-item
            ><el-form-item label="保密条款"
              ><el-input
                v-model="form.elements.confidentiality"
                type="textarea"
                :rows="2" /></el-form-item
            ><el-form-item label="知识产权"
              ><el-input
                v-model="form.elements.intellectual_property"
                type="textarea"
                :rows="2" /></el-form-item
            ><el-form-item label="争议解决"
              ><el-input
                v-model="form.elements.dispute_resolution"
                type="textarea"
                :rows="2" /></el-form-item
            ><el-form-item label="备注"
              ><el-input
                v-model="form.elements.remarks"
                type="textarea"
                :rows="2" /></el-form-item></el-tab-pane></el-tabs></el-form
      ><span slot="footer"
        ><el-button @click="dialogVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存合同要素</el-button
        ></span
      ></el-dialog
    >
    <el-dialog title="合同审批" :visible.sync="decisionVisible" width="560px"
      ><el-alert
        :title="selected ? `${selected.contract_no} · ${selected.title}` : ''"
        type="info"
        :closable="false"
      /><el-input
        v-model="decisionComment"
        type="textarea"
        :rows="4"
        class="decision-comment"
        placeholder="填写审批意见（选填）"
      /><span slot="footer"
        ><el-button @click="decisionVisible = false">取消</el-button
        ><el-button :loading="saving" @click="decide(false)">驳回修改</el-button
        ><el-button type="success" :loading="saving" @click="decide(true)"
          >审批通过</el-button
        ></span
      ></el-dialog
    >
    <el-dialog title="生成合同文件" :visible.sync="exportVisible" width="650px"
      ><div v-loading="preflightLoading">
        <el-alert
          v-if="preflight"
          :title="preflight.valid ? '生成前检查通过' : '生成前检查未通过'"
          :type="preflight.valid ? 'success' : 'error'"
          :closable="false"
          show-icon
        />
        <el-descriptions
          v-if="preflight"
          :column="2"
          border
          size="small"
          class="dialog-form-spaced"
        >
          <el-descriptions-item label="模板"
            >{{ preflight.template_name }} v{{
              preflight.template_version
            }}</el-descriptions-item
          >
          <el-descriptions-item label="引擎">{{
            preflight.engine === "docx_v1" ? "Word模板" : "文本模板"
          }}</el-descriptions-item>
          <el-descriptions-item label="识别字段">{{
            preflight.placeholders.length
          }}</el-descriptions-item>
          <el-descriptions-item label="PDF转换">{{
            preflight.pdf_available ? "可用" : "当前环境不可用"
          }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="preflight && preflight.missing_required.length"
          title="缺少必填要素"
          type="error"
          :description="preflight.missing_required.join('、')"
          :closable="false"
        />
        <el-alert
          v-if="preflight && preflight.unresolved.length"
          title="模板存在未映射字段"
          type="error"
          :description="preflight.unresolved.join('、')"
          :closable="false"
        />
        <el-alert
          v-for="warning in preflight ? preflight.warnings : []"
          :key="warning"
          :title="warning"
          type="warning"
          :closable="false"
          show-icon
        />
      </div>
      <el-form label-width="90px" class="dialog-form-spaced"
        ><el-form-item label="文件格式"
          ><el-radio-group v-model="outputFormat"
            ><el-radio-button label="docx">Word</el-radio-button
            ><el-radio-button
              label="pdf"
              :disabled="preflight && !preflight.pdf_available"
              >PDF</el-radio-button
            ></el-radio-group
          ></el-form-item
        ></el-form
      ><span slot="footer"
        ><el-button @click="exportVisible = false">取消</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!preflight || !preflight.valid"
          @click="generate"
          >生成并下载</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="合同文件生成记录"
      :visible.sync="historyVisible"
      width="900px"
    >
      <el-table
        :data="documentHistory"
        size="mini"
        empty-text="该合同尚未生成文件"
      >
        <el-table-column
          prop="created_at"
          label="生成时间"
          width="180"
        /><el-table-column
          prop="file_name"
          label="文件名"
          min-width="220"
        /><el-table-column
          prop="template_version"
          label="模板版本"
          width="100"
        /><el-table-column
          prop="output_format"
          label="格式"
          width="75"
        /><el-table-column
          prop="created_by"
          label="操作人"
          width="130"
        /><el-table-column label="文件校验值" min-width="160"
          ><template slot-scope="s"
            ><el-tooltip :content="s.row.sha256"
              ><code>{{ s.row.sha256.slice(0, 16) }}…</code></el-tooltip
            ></template
          ></el-table-column
        ><el-table-column label="操作" width="80"
          ><template slot-scope="s"
            ><el-button type="text" @click="downloadGenerated(s.row)"
              >下载</el-button
            ></template
          ></el-table-column
        >
      </el-table>
    </el-dialog>
    <el-dialog
      title="合同 AI 审查"
      :visible.sync="reviewVisible"
      width="1180px"
      top="4vh"
      :close-on-click-modal="false"
      ><contract-a-i-review
        v-if="reviewVisible && selected"
        :contract="selected"
        @reviewed="load"
    /></el-dialog>
  </div>
</template>
<script>
import { api, exportDocument, fetchTemplates } from "../api/client";
import ContractAIReview from "../components/ContractAIReview.vue";
const emptyElements = () => ({
  contract_type: "purchase",
  project_name: "",
  signing_date: null,
  delivery_address: "",
  transport_method: "",
  acceptance_standard: "",
  payment_terms: "",
  invoice_type: "增值税专用发票",
  quality_standard: "",
  warranty_period: "",
  breach_liability: "",
  confidentiality: "",
  intellectual_property: "",
  dispute_resolution: "",
  remarks: "",
});
const emptyForm = () => ({
  title: "",
  supplier_id: "SUP-",
  supplier_name: "",
  amount: 0,
  currency: "CNY",
  effective_date: null,
  expiry_date: null,
  template_id: null,
  elements: emptyElements(),
  items: [],
});
export default {
  components: { ContractAIReview },
  data: () => ({
    contracts: [],
    contractTemplates: [],
    form: emptyForm(),
    formTab: "base",
    dialogVisible: false,
    decisionVisible: false,
    exportVisible: false,
    historyVisible: false,
    reviewVisible: false,
    loading: false,
    saving: false,
    editingId: "",
    selected: null,
    decisionComment: "",
    outputFormat: "docx",
    preflight: null,
    preflightLoading: false,
    documentHistory: [],
    keyword: "",
    statusFilter: "",
    pagination: { page: 1, page_size: 10, total: 0 },
    statusOptions: [
      { label: "草稿", value: "draft" },
      { label: "待审批", value: "pending_approval" },
      { label: "履约中", value: "active" },
      { label: "已到期", value: "expired" },
      { label: "已终止", value: "terminated" },
    ],
    rules: {
      title: [{ required: true, message: "请输入合同名称", trigger: "blur" }],
      supplier_name: [
        { required: true, message: "请输入供应商名称", trigger: "blur" },
      ],
      supplier_id: [
        { required: true, message: "请输入供应商编码", trigger: "blur" },
      ],
    },
  }),
  async created() {
    await Promise.all([this.load(), this.loadTemplates()]);
  },
  methods: {
    money(value) {
      return Number(value).toLocaleString("zh-CN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    },
    statusName(value) {
      const item = this.statusOptions.find((option) => option.value === value);
      return item ? item.label : value;
    },
    statusType(value) {
      return (
        {
          draft: "info",
          pending_approval: "warning",
          active: "success",
          expired: "info",
          terminated: "danger",
        }[value] || ""
      );
    },
    async load() {
      this.loading = true;
      try {
        const params = {
          page: this.pagination.page,
          page_size: this.pagination.page_size,
          keyword: this.keyword,
        };
        if (this.statusFilter) params.status = this.statusFilter;
        const { data } = await api.get("/contracts", { params });
        this.contracts = data.items;
        this.pagination.total = data.total;
      } catch (_) {
        this.$message.error("合同加载失败");
      } finally {
        this.loading = false;
      }
    },
    async loadTemplates() {
      const result = await fetchTemplates({
        page: 1,
        page_size: 100,
        unfiltered: true,
      });
      this.contractTemplates = result.items.filter(
        (item) =>
          item.template_type === "contract" &&
          item.status === "active" &&
          (item.engine !== "docx_v1" || item.validation_status === "validated")
      );
    },
    search() {
      this.pagination.page = 1;
      this.load();
    },
    reset() {
      this.keyword = "";
      this.statusFilter = "";
      this.search();
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
      this.formTab = "base";
      this.dialogVisible = true;
    },
    edit(contract) {
      this.editingId = contract.id;
      this.form = {
        title: contract.title,
        supplier_id: contract.supplier_id,
        supplier_name: contract.supplier_name,
        amount: Number(contract.amount),
        currency: contract.currency,
        effective_date: contract.effective_date,
        expiry_date: contract.expiry_date,
        template_id: contract.template_id,
        elements: { ...emptyElements(), ...(contract.elements || {}) },
        items: (contract.items || []).map((item) => ({
          ...item,
          quantity: Number(item.quantity || 0),
          unit_price: Number(item.unit_price || 0),
          tax_rate: Number(item.tax_rate || 0),
        })),
      };
      this.formTab = "base";
      this.dialogVisible = true;
    },
    addItem() {
      this.form.items.push({
        material_code: "",
        material_name: "",
        specification: "",
        quantity: 1,
        unit: "件",
        unit_price: 0,
        tax_rate: 13,
      });
    },
    removeItem(index) {
      this.form.items.splice(index, 1);
      this.recalculate();
    },
    recalculate() {
      this.form.amount = this.form.items.reduce(
        (sum, item) =>
          sum +
          Number(item.quantity || 0) *
            Number(item.unit_price || 0) *
            (1 + Number(item.tax_rate || 0) / 100),
        0
      );
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        if (
          this.form.effective_date &&
          this.form.expiry_date &&
          this.form.expiry_date < this.form.effective_date
        )
          return this.$message.warning("失效日期不能早于生效日期");
        this.recalculate();
        this.saving = true;
        try {
          if (this.editingId)
            await api.patch(`/contracts/${this.editingId}`, this.form);
          else await api.post("/contracts", this.form);
          this.$message.success(this.editingId ? "合同已更新" : "合同已创建");
          this.dialogVisible = false;
          await this.load();
        } catch (error) {
          this.$message.error(
            (error.response &&
              error.response.data &&
              error.response.data.detail) ||
              "合同保存失败"
          );
        } finally {
          this.saving = false;
        }
      });
    },
    async submit(contract) {
      try {
        await this.$confirm(
          `提交 ${contract.contract_no} 审批后将锁定编辑，是否继续？`,
          "提交审批",
          { type: "warning" }
        );
        await api.post(`/contracts/${contract.id}/submit`);
        this.$message.success("合同已提交审批");
        await this.load();
      } catch (error) {
        if (error !== "cancel")
          this.$message.error(
            (error.response &&
              error.response.data &&
              error.response.data.detail) ||
              "提交失败"
          );
      }
    },
    openReview(contract) {
      this.selected = contract;
      this.reviewVisible = true;
    },
    openDecision(contract) {
      this.selected = contract;
      this.decisionComment = "";
      this.decisionVisible = true;
    },
    async decide(approved) {
      this.saving = true;
      try {
        await api.post(`/contracts/${this.selected.id}/decision`, {
          approved,
          comment: this.decisionComment,
        });
        this.$message.success(approved ? "合同已审批生效" : "合同已驳回草稿");
        this.decisionVisible = false;
        await this.load();
      } catch (error) {
        this.$message.error(
          (error.response &&
            error.response.data &&
            error.response.data.detail) ||
            "审批失败"
        );
      } finally {
        this.saving = false;
      }
    },
    async openExport(contract) {
      this.selected = contract;
      this.outputFormat = "docx";
      this.preflight = null;
      this.exportVisible = true;
      this.preflightLoading = true;
      try {
        const { data } = await api.get(
          `/documents/contract/${contract.id}/preflight`,
          { params: { template_id: contract.template_id } }
        );
        this.preflight = data;
      } catch (error) {
        this.$message.error(
          (error.response &&
            error.response.data &&
            error.response.data.detail) ||
            "生成前检查失败"
        );
      } finally {
        this.preflightLoading = false;
      }
    },
    async openHistory(contract) {
      this.selected = contract;
      try {
        const { data } = await api.get(
          `/documents/contract/${contract.id}/history`
        );
        this.documentHistory = data;
        this.historyVisible = true;
      } catch (_) {
        this.$message.error("生成记录加载失败");
      }
    },
    downloadGenerated(item) {
      window.open(item.download_url, "_blank", "noopener");
    },
    async generate() {
      this.saving = true;
      try {
        const result = await exportDocument("contract", this.selected.id, {
          template_id: this.selected.template_id,
          output_format: this.outputFormat,
        });
        this.$message.success("合同文件已生成并保存版本快照");
        this.exportVisible = false;
        window.open(result.download_url, "_blank", "noopener");
      } catch (error) {
        this.$message.error(
          (error.response &&
            error.response.data &&
            error.response.data.detail) ||
            "文件生成失败"
        );
      } finally {
        this.saving = false;
      }
    },
    async terminate(contract) {
      try {
        await this.$confirm(
          `终止 ${contract.contract_no} 后不可恢复，是否继续？`,
          "终止合同",
          { type: "warning" }
        );
        await api.post(`/contracts/${contract.id}/terminate`);
        this.$message.success("合同已终止");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("终止失败");
      }
    },
    async remove(contract) {
      try {
        await this.$confirm(
          `确定删除合同 ${contract.contract_no} 吗？`,
          "删除确认",
          { type: "warning" }
        );
        await api.delete(`/contracts/${contract.id}`);
        this.$message.success("合同已删除");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("合同删除失败");
      }
    },
  },
};
</script>
<style scoped>
.contract-items-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}
.contract-items-head .el-alert {
  flex: 1;
}
.contract-total {
  text-align: right;
  margin-top: 14px;
  font-size: 15px;
}
.contract-total strong {
  font-size: 20px;
  color: #2563eb;
  margin: 0 5px;
}
</style>

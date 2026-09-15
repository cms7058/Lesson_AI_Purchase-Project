<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">采购需求入口</p>
        <h1>采购申请与审批</h1>
        <p>
          从需求部门提出申请，经采购经理审批后生成采购订单，保留完整状态与审计记录。
        </p>
      </div>
      <el-button type="primary" @click="openCreate">新建采购申请</el-button>
    </div>
    <div class="process-strip">
      <span>1. 草稿申请</span><i>→</i><span>2. 提交审批</span><i>→</i
      ><span>3. 经理审批</span><i>→</i><span>4. 生成订单</span>
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索申请编号、标题或部门"
        @keyup.enter.native="search"
        @clear="search"
      />
      <el-select
        v-model="statusFilter"
        clearable
        placeholder="全部状态"
        @change="search"
      >
        <el-option
          v-for="item in statusOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-button icon="el-icon-search" @click="search">查询</el-button
      ><el-button @click="resetSearch">重置</el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      class="data-table"
      empty-text="暂无采购申请"
    >
      <el-table-column
        prop="request_no"
        label="申请编号"
        width="145"
      /><el-table-column
        prop="title"
        label="申请主题"
        min-width="190"
      /><el-table-column
        prop="department"
        label="需求部门"
        width="120"
      /><el-table-column prop="factory_code" label="工厂" width="100" />
      <el-table-column label="优先级" width="90"
        ><template slot-scope="scope"
          ><el-tag size="mini" :type="priorityType(scope.row.priority)">{{
            priorityName(scope.row.priority)
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="航空需求" width="110"
        ><template slot-scope="scope"
          ><el-tag
            v-if="scope.row.aviation_profile"
            size="mini"
            :type="
              scope.row.aviation_profile.demand_type === 'aog'
                ? 'danger'
                : 'warning'
            "
            >{{
              aviationDemandName(scope.row.aviation_profile.demand_type)
            }}</el-tag
          ><span v-else>-</span></template
        ></el-table-column
      >
      <el-table-column
        prop="needed_date"
        label="需求日期"
        width="110"
      /><el-table-column label="预估金额" width="125"
        ><template slot-scope="scope"
          >¥ {{ scope.row.estimated_total }}</template
        ></el-table-column
      >
      <el-table-column label="状态" width="110"
        ><template slot-scope="scope"
          ><el-tag :type="statusType(scope.row.status)">{{
            statusName(scope.row.status)
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="操作" width="300" fixed="right"
        ><template slot-scope="scope">
          <el-button
            v-if="canEdit(scope.row)"
            type="text"
            @click="openEdit(scope.row)"
            >编辑</el-button
          >
          <el-button
            v-if="canEdit(scope.row)"
            type="text"
            @click="submit(scope.row)"
            >提交</el-button
          >
          <el-button
            v-if="scope.row.status === 'pending_approval'"
            type="text"
            @click="openDecision(scope.row)"
            >审批</el-button
          >
          <el-button
            v-if="scope.row.status === 'approved'"
            type="text"
            @click="openConvert(scope.row)"
            >生成订单</el-button
          >
          <el-button type="text" @click="showDetail(scope.row)">详情</el-button>
          <el-button
            v-if="canEdit(scope.row)"
            type="text"
            class="danger-link"
            @click="remove(scope.row)"
            >删除</el-button
          >
        </template></el-table-column
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
      :title="editingId ? '编辑采购申请' : '新建采购申请'"
      :visible.sync="formVisible"
      width="920px"
      top="5vh"
      :close-on-click-modal="false"
    >
      <el-radio-group
        v-model="requestType"
        @change="requestType === 'spare' && (spareVisible = true)"
        ><el-radio-button label="production">生产件</el-radio-button
        ><el-radio-button label="spare">备件</el-radio-button></el-radio-group
      ><el-button v-if="requestType === 'spare'" @click="spareVisible = true"
        >备件TOC计划</el-button
      >
      <el-checkbox
        v-model="aviationEnabled"
        style="margin-left: 18px"
        @change="toggleAviation"
        >航空MRO需求</el-checkbox
      >
      <el-form
        ref="requestForm"
        :model="form"
        :rules="rules"
        label-width="92px"
      >
        <el-card v-if="aviationEnabled" shadow="never" style="margin: 16px 0"
          ><div slot="header">
            <strong>航空维修项目与紧急需求</strong
            ><el-tag
              v-if="form.aviation_profile.demand_type === 'aog'"
              type="danger"
              style="margin-left: 12px"
              >AOG绿色通道</el-tag
            >
          </div>
          <el-row :gutter="16"
            ><el-col :span="6"
              ><el-form-item label="需求类型"
                ><el-select
                  v-model="form.aviation_profile.demand_type"
                  style="width: 100%"
                  @change="onAviationDemandType"
                  ><el-option label="计划需求" value="planned" /><el-option
                    label="Non-routine"
                    value="non_routine" /><el-option
                    label="AOG停场"
                    value="aog" /></el-select></el-form-item></el-col
            ><el-col :span="6"
              ><el-form-item label="飞机注册号"
                ><el-input
                  v-model.trim="
                    form.aviation_profile.aircraft_registration
                  " /></el-form-item></el-col
            ><el-col :span="6"
              ><el-form-item label="维修工作包"
                ><el-input
                  v-model.trim="
                    form.aviation_profile.work_package
                  " /></el-form-item></el-col
            ><el-col :span="6"
              ><el-form-item label="异常发现编号"
                ><el-input
                  v-model.trim="
                    form.aviation_profile.finding_no
                  " /></el-form-item></el-col></el-row
          ><el-row :gutter="16"
            ><el-col :span="6"
              ><el-form-item label="到货时限(时)"
                ><el-input-number
                  v-model="form.aviation_profile.required_within_hours"
                  :min="0"
                  :max="8760"
                  style="width: 100%" /></el-form-item></el-col
            ><el-col :span="6"
              ><el-form-item label="飞机停场"
                ><el-switch
                  v-model="
                    form.aviation_profile.grounded
                  " /></el-form-item></el-col
            ><el-col :span="6"
              ><el-form-item label="授权通道"
                ><el-select
                  v-model="form.aviation_profile.approval_channel"
                  style="width: 100%"
                  ><el-option label="正常审批" value="normal" /><el-option
                    label="AOG紧急授权"
                    value="aog_fast_track" /><el-option
                    label="经理超限授权"
                    value="manager_override" /></el-select></el-form-item></el-col
            ><el-col :span="6"
              ><el-form-item label="最高溢价%"
                ><el-input-number
                  v-model="form.aviation_profile.maximum_premium_percent"
                  :min="0"
                  :max="500"
                  style="width: 100%" /></el-form-item></el-col></el-row
          ><el-form-item label="维修证据"
            ><el-input
              v-model="form.aviation_profile.evidence"
              type="textarea"
              :rows="2"
              placeholder="维修工作卡、Non-routine记录、AOG通知或工程判定依据" /></el-form-item
        ></el-card>
        <el-row :gutter="16"
          ><el-col :span="12"
            ><el-form-item label="申请主题" prop="title"
              ><el-input v-model.trim="form.title" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="需求部门"
              ><el-input
                v-model.trim="form.department" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="成本中心"
              ><el-input
                v-model.trim="form.cost_center" /></el-form-item></el-col
        ></el-row>
        <el-row :gutter="16"
          ><el-col :span="8"
            ><el-form-item label="收货工厂" prop="factory_code"
              ><el-select
                v-model="form.factory_code"
                filterable
                allow-create
                style="width: 100%"
                ><el-option
                  v-for="factory in factories"
                  :key="factory.id"
                  :label="`${factory.code} · ${factory.name}`"
                  :value="factory.code" /></el-select></el-form-item></el-col
          ><el-col :span="8"
            ><el-form-item label="需求日期"
              ><el-date-picker
                v-model="form.needed_date"
                value-format="yyyy-MM-dd"
                type="date"
                style="width: 100%" /></el-form-item></el-col
          ><el-col :span="8"
            ><el-form-item label="优先级"
              ><el-select v-model="form.priority" style="width: 100%"
                ><el-option label="低" value="low" /><el-option
                  label="普通"
                  value="normal" /><el-option
                  label="高"
                  value="high" /><el-option
                  label="紧急"
                  value="urgent" /></el-select></el-form-item></el-col
        ></el-row>
        <el-form-item label="申请原因"
          ><el-input v-model.trim="form.reason" type="textarea" :rows="2"
        /></el-form-item>
        <div class="dialog-section-title">
          <strong>申请明细</strong
          ><el-button size="mini" icon="el-icon-plus" @click="addLine"
            >添加物料</el-button
          >
        </div>
        <el-table
          :data="form.lines"
          border
          size="mini"
          class="dialog-line-table"
        >
          <el-table-column label="物料编码" min-width="150"
            ><template slot-scope="scope"
              ><el-select
                v-model="scope.row.material_code"
                filterable
                allow-create
                placeholder="选择或输入"
                @change="selectMaterial(scope.$index, $event)"
                ><el-option
                  v-for="material in materials"
                  :key="material.id"
                  :label="`${material.code} · ${material.name}`"
                  :value="material.code" /></el-select></template
          ></el-table-column>
          <el-table-column label="物料名称" min-width="150"
            ><template slot-scope="scope"
              ><el-input
                v-model="scope.row.material_name" /></template></el-table-column
          ><el-table-column label="规格" min-width="130"
            ><template slot-scope="scope"
              ><el-input
                v-model="scope.row.specification" /></template></el-table-column
          ><el-table-column label="数量" width="105"
            ><template slot-scope="scope"
              ><el-input-number
                v-model="scope.row.quantity"
                :min="0.0001"
                :precision="2"
                controls-position="right" /></template></el-table-column
          ><el-table-column label="单位" width="75"
            ><template slot-scope="scope"
              ><el-input v-model="scope.row.unit" /></template></el-table-column
          ><el-table-column label="预估单价" width="125"
            ><template slot-scope="scope"
              ><el-input-number
                v-model="scope.row.estimated_unit_price"
                :min="0"
                :precision="2"
                controls-position="right" /></template></el-table-column
          ><el-table-column width="60" fixed="right"
            ><template slot-scope="scope"
              ><el-button
                type="text"
                class="danger-link"
                :disabled="form.lines.length === 1"
                @click="form.lines.splice(scope.$index, 1)"
                >移除</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <div class="estimated-total">
          预估总额：<strong>¥ {{ formTotal }}</strong>
        </div>
      </el-form>
      <span slot="footer"
        ><el-button @click="formVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存申请</el-button
        ></span
      >
    </el-dialog>

    <SpareRequestPlanner
      :visible="spareVisible"
      @close="spareVisible = false"
      @apply="applySpare"
    />
    <el-dialog
      title="采购申请审批"
      :visible.sync="decisionVisible"
      width="520px"
    >
      <el-descriptions v-if="selected" :column="1" border
        ><el-descriptions-item label="申请编号">{{
          selected.request_no
        }}</el-descriptions-item
        ><el-descriptions-item label="申请主题">{{
          selected.title
        }}</el-descriptions-item
        ><el-descriptions-item label="预估金额"
          >¥ {{ selected.estimated_total }}</el-descriptions-item
        ></el-descriptions
      >
      <el-alert
        v-if="selected && selected.aviation_profile"
        :title="`${aviationDemandName(
          selected.aviation_profile.demand_type
        )} · ${
          selected.aviation_profile.aircraft_registration || '飞机号待补充'
        } · 到货时限 ${
          selected.aviation_profile.required_within_hours || 0
        } 小时`"
        type="warning"
        :closable="false"
        style="margin-top: 12px"
      />
      <el-input
        v-model="decisionComment"
        type="textarea"
        :rows="4"
        placeholder="填写审批意见"
        class="decision-comment"
      />
      <span slot="footer"
        ><el-button type="danger" plain :loading="saving" @click="decide(false)"
          >驳回</el-button
        ><el-button type="success" :loading="saving" @click="decide(true)"
          >批准</el-button
        ></span
      >
    </el-dialog>

    <el-dialog
      title="由申请生成采购订单"
      :visible.sync="convertVisible"
      width="620px"
    >
      <el-alert
        title="系统将复制申请物料、数量、工厂和需求日期，预估单价作为订单初始单价。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form
        :model="conversion"
        label-width="105px"
        class="dialog-form-spaced"
        ><el-form-item label="选择供应商"
          ><el-select
            v-model="conversion.supplier_id"
            filterable
            style="width: 100%"
            @change="selectSupplier"
            ><el-option
              v-for="supplier in suppliers"
              :key="supplier.id"
              :disabled="supplier.status !== 'qualified'"
              :label="`${supplier.code} · ${supplier.name}${
                supplier.status === 'qualified' ? '' : '（未准入）'
              }`"
              :value="supplier.code" /></el-select></el-form-item
        ><el-form-item label="订单模板"
          ><el-select
            v-model="conversion.template_id"
            clearable
            style="width: 100%"
            ><el-option
              v-for="template in orderTemplates"
              :key="template.id"
              :label="`${template.name} v${template.version}`"
              :value="template.id" /></el-select></el-form-item
        ><el-form-item label="付款条件"
          ><el-input v-model="conversion.payment_terms" /></el-form-item
        ><el-form-item label="收货地址"
          ><el-input v-model="conversion.delivery_address" /></el-form-item
      ></el-form>
      <span slot="footer"
        ><el-button @click="convertVisible = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="!conversion.supplier_id"
          :loading="saving"
          @click="convert"
          >生成采购订单</el-button
        ></span
      >
    </el-dialog>

    <el-dialog title="采购申请详情" :visible.sync="detailVisible" width="760px"
      ><template v-if="selected"
        ><el-descriptions
          v-if="selected.aviation_profile"
          title="航空MRO需求"
          :column="3"
          border
          style="margin-bottom: 16px"
          ><el-descriptions-item label="需求类型">{{
            aviationDemandName(selected.aviation_profile.demand_type)
          }}</el-descriptions-item
          ><el-descriptions-item label="飞机注册号">{{
            selected.aviation_profile.aircraft_registration || "-"
          }}</el-descriptions-item
          ><el-descriptions-item label="停场">{{
            selected.aviation_profile.grounded ? "是" : "否"
          }}</el-descriptions-item
          ><el-descriptions-item label="维修工作包">{{
            selected.aviation_profile.work_package || "-"
          }}</el-descriptions-item
          ><el-descriptions-item label="异常发现编号">{{
            selected.aviation_profile.finding_no || "-"
          }}</el-descriptions-item
          ><el-descriptions-item label="到货时限"
            >{{
              selected.aviation_profile.required_within_hours || 0
            }}
            小时</el-descriptions-item
          ><el-descriptions-item label="授权通道">{{
            selected.aviation_profile.approval_channel
          }}</el-descriptions-item
          ><el-descriptions-item label="最高溢价"
            >{{
              selected.aviation_profile.maximum_premium_percent
            }}%</el-descriptions-item
          ><el-descriptions-item label="证据依据">{{
            selected.aviation_profile.evidence || "-"
          }}</el-descriptions-item></el-descriptions
        ><el-collapse v-if="selected.spare_analysis_snapshot"
          ><el-collapse-item title="备件计划分类与历史权重快照"
            ><p>{{ selected.spare_analysis_snapshot.note }}</p>
            <el-table :data="selected.spare_analysis_snapshot.items"
              ><el-table-column
                prop="material_code"
                label="备件" /><el-table-column
                prop="weight"
                label="参考权重 %" /><el-table-column
                prop="unit_toc"
                label="单位TOC" /></el-table></el-collapse-item></el-collapse
        ><el-descriptions :column="2" border
          ><el-descriptions-item label="申请编号">{{
            selected.request_no
          }}</el-descriptions-item
          ><el-descriptions-item label="状态">{{
            statusName(selected.status)
          }}</el-descriptions-item
          ><el-descriptions-item label="申请主题">{{
            selected.title
          }}</el-descriptions-item
          ><el-descriptions-item label="需求部门">{{
            selected.department || "-"
          }}</el-descriptions-item
          ><el-descriptions-item label="审批人">{{
            selected.approved_by || "-"
          }}</el-descriptions-item
          ><el-descriptions-item label="审批意见">{{
            selected.approval_comment || "-"
          }}</el-descriptions-item></el-descriptions
        ><el-table :data="selected.lines" border class="detail-lines"
          ><el-table-column
            prop="material_code"
            label="物料编码" /><el-table-column
            prop="material_name"
            label="物料名称" /><el-table-column
            prop="quantity"
            label="数量"
            width="90" /><el-table-column
            prop="unit"
            label="单位"
            width="70" /><el-table-column
            prop="estimated_unit_price"
            label="预估单价"
            width="110" /></el-table></template
    ></el-dialog>
  </div>
</template>

<script>
import SpareRequestPlanner from "../components/SpareRequestPlanner.vue";
import {
  convertRequisition,
  createRequisition,
  decideRequisition,
  deleteRequisition,
  fetchMasterData,
  fetchRequisitions,
  fetchTemplates,
  submitRequisition,
  updateRequisition,
} from "../api/client";
const emptyLine = () => ({
  material_code: "",
  material_name: "",
  specification: "",
  quantity: 1,
  unit: "件",
  estimated_unit_price: 0,
});
const aviationProfile = () => ({
  demand_type: "planned",
  aircraft_registration: "",
  work_package: "",
  finding_no: "",
  required_within_hours: 0,
  grounded: false,
  approval_channel: "normal",
  maximum_premium_percent: 0,
  evidence: "",
});
const emptyForm = () => ({
  aviation_profile: null,
  spare_plan_codes: [],
  title: "",
  factory_code: "",
  department: "",
  cost_center: "",
  priority: "normal",
  needed_date: null,
  reason: "",
  lines: [emptyLine()],
});
const emptyConversion = () => ({
  supplier_id: "",
  supplier_name: "",
  template_id: null,
  currency: "CNY",
  payment_terms: "",
  delivery_address: "",
});
export default {
  components: { SpareRequestPlanner },
  data: () => ({
    aviationEnabled: false,
    requestType: "production",
    spareVisible: false,
    items: [],
    factories: [],
    materials: [],
    suppliers: [],
    orderTemplates: [],
    keyword: "",
    statusFilter: "",
    loading: false,
    saving: false,
    formVisible: false,
    decisionVisible: false,
    convertVisible: false,
    detailVisible: false,
    editingId: "",
    selected: null,
    decisionComment: "",
    form: emptyForm(),
    conversion: emptyConversion(),
    pagination: { page: 1, page_size: 10, total: 0 },
    statusOptions: [
      { value: "draft", label: "草稿" },
      { value: "pending_approval", label: "待审批" },
      { value: "approved", label: "已批准" },
      { value: "rejected", label: "已驳回" },
      { value: "converted", label: "已生成订单" },
    ],
    rules: {
      title: [{ required: true, message: "请输入申请主题", trigger: "blur" }],
      factory_code: [
        { required: true, message: "请选择收货工厂", trigger: "change" },
      ],
    },
  }),
  computed: {
    formTotal() {
      return this.form.lines
        .reduce(
          (total, line) =>
            total +
            Number(line.quantity || 0) * Number(line.estimated_unit_price || 0),
          0
        )
        .toFixed(2);
    },
  },
  async created() {
    await Promise.all([this.load(), this.loadOptions()]);
  },
  methods: {
    aviationDemandName(value) {
      return (
        { planned: "计划需求", non_routine: "Non-routine", aog: "AOG停场" }[
          value
        ] || value
      );
    },
    onAviationDemandType(value) {
      if (value === "aog") {
        this.form.priority = "urgent";
        this.form.aviation_profile.grounded = true;
        this.form.aviation_profile.approval_channel = "aog_fast_track";
        if (!this.form.aviation_profile.required_within_hours)
          this.form.aviation_profile.required_within_hours = 24;
      } else if (value === "non_routine" && this.form.priority === "normal") {
        this.form.priority = "high";
      }
    },
    toggleAviation(enabled) {
      this.$set(
        this.form,
        "aviation_profile",
        enabled ? this.form.aviation_profile || aviationProfile() : null
      );
    },
    async applySpare(plan) {
      if (this.form.lines.some((l) => l.material_code)) {
        try {
          await this.$confirm("用选中的备件计划替换当前申请明细？", "确认替换");
        } catch (e) {
          return;
        }
      }
      this.$set(
        this.form,
        "spare_plan_codes",
        plan.lines.map((l) => l.material_code)
      );
      this.form.lines = plan.lines;
      this.form.needed_date = plan.needed_date;
      this.form.reason = (this.form.reason + "\n" + plan.summary).slice(
        0,
        1000
      );
      this.spareVisible = false;
      this.$message.success("已带回备件明细，请完善申请主题和工厂后保存");
    },
    statusName(value) {
      return (
        {
          draft: "草稿",
          pending_approval: "待审批",
          approved: "已批准",
          rejected: "已驳回",
          converted: "已生成订单",
          cancelled: "已取消",
        }[value] || value
      );
    },
    statusType(value) {
      return (
        {
          draft: "info",
          pending_approval: "warning",
          approved: "success",
          rejected: "danger",
          converted: "success",
          cancelled: "info",
        }[value] || ""
      );
    },
    priorityName(value) {
      return (
        { low: "低", normal: "普通", high: "高", urgent: "紧急" }[value] ||
        value
      );
    },
    priorityType(value) {
      return (
        { low: "info", normal: "", high: "warning", urgent: "danger" }[value] ||
        ""
      );
    },
    canEdit(item) {
      return ["draft", "rejected"].includes(item.status);
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
        const result = await fetchRequisitions(params);
        this.items = result.items;
        this.pagination.total = result.total;
      } catch (_) {
        this.$message.error("采购申请加载失败");
      } finally {
        this.loading = false;
      }
    },
    async loadOptions() {
      const [factories, materials, suppliers, templates] = await Promise.all([
        fetchMasterData("factories", {
          page: 1,
          page_size: 100,
          unfiltered: true,
        }),
        fetchMasterData("materials", {
          page: 1,
          page_size: 100,
          unfiltered: true,
        }),
        fetchMasterData("suppliers", {
          page: 1,
          page_size: 100,
          unfiltered: true,
        }),
        fetchTemplates({ page: 1, page_size: 100, unfiltered: true }),
      ]);
      this.factories = factories.items.filter((item) => item.active);
      this.materials = materials.items.filter((item) => item.active);
      this.suppliers = suppliers.items;
      this.orderTemplates = templates.items.filter(
        (item) => item.template_type === "order" && item.status === "active"
      );
    },
    search() {
      this.pagination.page = 1;
      this.load();
    },
    resetSearch() {
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
      this.aviationEnabled = false;
      this.requestType = "production";
      this.editingId = "";
      this.form = emptyForm();
      this.formVisible = true;
      this.$nextTick(
        () => this.$refs.requestForm && this.$refs.requestForm.clearValidate()
      );
    },
    openEdit(item) {
      this.aviationEnabled = !!item.aviation_profile;
      this.requestType = item.spare_plan_codes?.length ? "spare" : "production";
      this.editingId = item.id;
      this.form = {
        aviation_profile: item.aviation_profile
          ? { ...item.aviation_profile }
          : null,
        spare_plan_codes: item.spare_plan_codes || [],
        title: item.title,
        factory_code: item.factory_code,
        department: item.department,
        cost_center: item.cost_center,
        priority: item.priority,
        needed_date: item.needed_date,
        reason: item.reason,
        lines: item.lines.map((line) => ({
          ...line,
          quantity: Number(line.quantity),
          estimated_unit_price: Number(line.estimated_unit_price),
        })),
      };
      this.formVisible = true;
    },
    addLine() {
      this.form.lines.push(emptyLine());
    },
    selectMaterial(index, code) {
      const material = this.materials.find((item) => item.code === code);
      if (material)
        this.$set(this.form.lines, index, {
          material_code: material.code,
          material_name: material.name,
          specification: material.specification,
          quantity: this.form.lines[index].quantity,
          unit: material.unit,
          estimated_unit_price: Number(material.standard_price),
        });
    },
    save() {
      this.$refs.requestForm.validate(async (valid) => {
        if (!valid) return;
        if (
          this.form.lines.some(
            (line) =>
              !line.material_code ||
              !line.material_name ||
              Number(line.quantity) <= 0
          )
        )
          return this.$message.warning("请完整填写申请明细");
        this.saving = true;
        try {
          if (this.editingId)
            await updateRequisition(this.editingId, this.form);
          else await createRequisition(this.form);
          this.$message.success("采购申请已保存");
          this.formVisible = false;
          await this.load();
        } catch (error) {
          this.$message.error(
            (error.response &&
              error.response.data &&
              error.response.data.detail) ||
              "采购申请保存失败"
          );
        } finally {
          this.saving = false;
        }
      });
    },
    async submit(item) {
      try {
        await this.$confirm(
          `提交 ${item.request_no} 后将进入审批，是否继续？`,
          "提交审批",
          { type: "warning" }
        );
        await submitRequisition(item.id);
        this.$message.success("已提交审批");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("提交失败");
      }
    },
    openDecision(item) {
      this.selected = item;
      this.decisionComment = "";
      this.decisionVisible = true;
    },
    async decide(approved) {
      this.saving = true;
      try {
        await decideRequisition(this.selected.id, {
          approved,
          comment: this.decisionComment,
        });
        this.$message.success(approved ? "申请已批准" : "申请已驳回");
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
    openConvert(item) {
      this.selected = item;
      this.conversion = emptyConversion();
      this.convertVisible = true;
    },
    selectSupplier(code) {
      const supplier = this.suppliers.find((item) => item.code === code);
      this.conversion.supplier_name = supplier ? supplier.name : "";
    },
    async convert() {
      this.saving = true;
      try {
        const order = await convertRequisition(
          this.selected.id,
          this.conversion
        );
        this.$message.success(`已生成采购订单 ${order.order_no}`);
        this.convertVisible = false;
        await this.load();
      } catch (error) {
        this.$message.error(
          (error.response &&
            error.response.data &&
            error.response.data.detail) ||
            "订单生成失败"
        );
      } finally {
        this.saving = false;
      }
    },
    showDetail(item) {
      this.selected = item;
      this.detailVisible = true;
    },
    async remove(item) {
      try {
        await this.$confirm(
          `确定删除采购申请 ${item.request_no} 吗？`,
          "删除确认",
          { type: "warning" }
        );
        await deleteRequisition(item.id);
        this.$message.success("采购申请已删除");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("采购申请删除失败");
      }
    },
  },
};
</script>

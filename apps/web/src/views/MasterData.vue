<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">{{ pageEyebrow }}</p>
        <h1>{{ pageTitle }}</h1>
        <p>{{ pageDescription }}</p>
      </div>
      <div>
        <el-button v-if="active === 'suppliers'" @click="seedAviationDemo"
          >导入航空MRO演示数据</el-button
        ><el-button
          v-if="active === 'suppliers'"
          @click="
            qualificationSupplier = '';
            qualificationsVisible = true;
          "
          >资质档案与到期预警</el-button
        ><el-button
          v-if="active === 'suppliers' && isAdmin"
          @click="accountsVisible = true"
          >供应商账号与登录网址</el-button
        ><el-button type="primary" @click="openCreate"
          >新增{{ activeLabel }}</el-button
        >
      </div>
    </div>
    <el-dialog
      v-if="active === 'suppliers' && isAdmin"
      title="供应商账号与登录网址"
      :visible.sync="accountsVisible"
      width="1000px"
      :close-on-click-modal="false"
      ><SupplierAccounts v-if="accountsVisible" /><span slot="footer"
        ><el-button @click="accountsVisible = false">关闭</el-button></span
      ></el-dialog
    >
    <el-dialog
      v-if="active === 'suppliers'"
      title="供应商按物料供货指标"
      :visible.sync="metricsVisible"
      width="1100px"
      ><SupplierMetrics
        v-if="metricsVisible"
        :supplier-code="metricSupplier"
      /><span slot="footer"
        ><el-button @click="metricsVisible = false">关闭</el-button></span
      ></el-dialog
    >
    <el-dialog
      v-if="active === 'suppliers'"
      title="供应商资质档案与到期预警"
      :visible.sync="qualificationsVisible"
      width="1200px"
      :close-on-click-modal="false"
      ><SupplierQualifications
        v-if="qualificationsVisible"
        :supplier-id="qualificationSupplier"
      /><span slot="footer"
        ><el-button @click="qualificationsVisible = false"
          >关闭</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      v-if="active === 'suppliers'"
      title="航空MRO供应能力与适用范围"
      :visible.sync="aviationCapabilitiesVisible"
      width="1200px"
      :close-on-click-modal="false"
      ><AviationSupplierCapabilities
        v-if="aviationCapabilitiesVisible"
        :supplier-id="aviationSupplier"
      /><span slot="footer"
        ><el-button @click="aviationCapabilitiesVisible = false"
          >关闭</el-button
        ></span
      ></el-dialog
    >
    <el-button
      v-if="active === 'suppliers'"
      style="margin-bottom: 16px"
      @click="
        metricSupplier = '';
        metricsVisible = true;
      "
      >查看物料供货指标</el-button
    >
    <div class="master-summary">
      <div>
        <span>当前数据集</span><strong>{{ activeLabel }}</strong>
      </div>
      <div>
        <span>记录总数</span><strong>{{ pagination.total }}</strong>
      </div>
      <div><span>页面加载</span><strong>服务端分页</strong></div>
    </div>
    <div v-if="active === 'suppliers'" class="chart-grid compact-charts">
      <div class="chart-card">
        <div class="chart-title">
          <strong>按物料反馈指标中位数</strong
          ><span>质量 / 交付（来源：外部反馈）</span>
        </div>
        <div ref="performanceChart" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">
          <strong>物料三级分类分布</strong><span>关联物料数量</span>
        </div>
        <div ref="categoryChart" class="chart-box"></div>
      </div>
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        :placeholder="`搜索${activeLabel}编码、名称${
          active === 'suppliers' ? '或分类' : ''
        }`"
        @keyup.enter.native="search"
        @clear="search"
      />
      <el-select
        v-if="active === 'suppliers'"
        v-model="statusFilter"
        clearable
        placeholder="全部准入状态"
        @change="search"
      >
        <el-option label="候选" value="candidate" /><el-option
          label="合格"
          value="qualified"
        /><el-option label="暂停" value="suspended" /><el-option
          label="黑名单"
          value="blacklisted"
        />
      </el-select>
      <el-button icon="el-icon-search" @click="search">查询</el-button
      ><el-button @click="resetSearch">重置</el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      class="data-table"
      :empty-text="`暂无${activeLabel}数据`"
    >
      <template v-if="active === 'suppliers'">
        <el-table-column
          prop="code"
          label="供应商编码"
          width="135"
        /><el-table-column
          prop="name"
          label="供应商名称"
          min-width="180"
        /><el-table-column prop="category" label="供应品类" min-width="120" />
        <el-table-column label="准入状态" width="100"
          ><template slot-scope="scope"
            ><el-tag :type="supplierStatusType(scope.row.status)">{{
              supplierStatusName(scope.row.status)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="风险" width="85"
          ><template slot-scope="scope"
            ><el-tag size="mini" :type="riskType(scope.row.risk_level)">{{
              riskName(scope.row.risk_level)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="供货指标" width="150"
          ><template slot-scope="scope"
            ><el-button
              type="text"
              @click="
                metricSupplier = scope.row.code;
                metricsVisible = true;
              "
              >按物料查看指标</el-button
            ></template
          ></el-table-column
        ><el-table-column label="航空能力" width="100"
          ><template slot-scope="scope"
            ><el-button
              type="text"
              @click="
                aviationSupplier = scope.row.id;
                aviationCapabilitiesVisible = true;
              "
              >能力范围</el-button
            ></template
          ></el-table-column
        ><el-table-column label="资质档案" width="100"
          ><template slot-scope="scope"
            ><el-button
              type="text"
              @click="
                qualificationSupplier = scope.row.id;
                qualificationsVisible = true;
              "
              >查看资质</el-button
            ></template
          ></el-table-column
        ><el-table-column prop="contact" label="联系人" width="100" />
      </template>
      <template v-else-if="active === 'materials'">
        <el-table-column
          prop="code"
          label="物料编码"
          width="145"
        /><el-table-column
          prop="name"
          label="物料名称"
          min-width="160"
        /><el-table-column
          prop="specification"
          label="规格型号"
          min-width="180"
        /><el-table-column
          prop="category"
          label="分类"
          width="120"
        /><el-table-column
          prop="unit"
          label="单位"
          width="70"
        /><el-table-column
          prop="standard_price"
          label="标准价"
          width="110"
        /><el-table-column
          prop="safety_stock"
          label="安全库存"
          width="100"
        /><el-table-column
          prop="lead_time_days"
          label="提前期(天)"
          width="100"
        />
        <el-table-column label="状态" width="80"
          ><template slot-scope="scope"
            ><el-tag :type="scope.row.active ? 'success' : 'info'">{{
              scope.row.active ? "启用" : "停用"
            }}</el-tag></template
          ></el-table-column
        >
      </template>
      <template v-else>
        <el-table-column
          prop="code"
          label="工厂编码"
          width="140"
        /><el-table-column
          prop="name"
          label="工厂名称"
          min-width="170"
        /><el-table-column
          prop="address"
          label="地址"
          min-width="240"
          show-overflow-tooltip
        /><el-table-column
          prop="contact"
          label="联系人"
          width="100"
        /><el-table-column
          prop="phone"
          label="联系电话"
          width="140"
        /><el-table-column
          prop="daily_receiving_capacity"
          label="日收货能力"
          width="120"
        />
        <el-table-column label="状态" width="80"
          ><template slot-scope="scope"
            ><el-tag :type="scope.row.active ? 'success' : 'info'">{{
              scope.row.active ? "启用" : "停用"
            }}</el-tag></template
          ></el-table-column
        >
      </template>
      <el-table-column label="操作" width="130" fixed="right"
        ><template slot-scope="scope"
          ><el-button type="text" @click="openEdit(scope.row)">编辑</el-button
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
      :title="`${editingId ? '编辑' : '新增'}${activeLabel}`"
      :visible.sync="dialogVisible"
      width="720px"
      :close-on-click-modal="false"
    >
      <el-form ref="form" :model="form" :rules="rules" label-width="105px">
        <template v-if="active === 'suppliers'">
          <el-row :gutter="16"
            ><el-col :span="12"
              ><el-form-item label="供应商编码" prop="code"
                ><el-input
                  v-model.trim="form.code"
                  :disabled="!!editingId" /></el-form-item></el-col
            ><el-col :span="12"
              ><el-form-item label="供应商名称" prop="name"
                ><el-input v-model.trim="form.name" /></el-form-item></el-col
          ></el-row>
          <el-row :gutter="16"
            ><el-col :span="12"
              ><el-form-item label="统一信用代码"
                ><el-input
                  v-model.trim="
                    form.unified_credit_code
                  " /></el-form-item></el-col
            ><el-col :span="12"
              ><el-form-item label="供应品类"
                ><el-input
                  v-model.trim="form.category" /></el-form-item></el-col
          ></el-row>
          <el-row :gutter="16"
            ><el-col :span="12"
              ><el-form-item label="准入状态"
                ><el-select v-model="form.status" style="width: 100%"
                  ><el-option label="候选" value="candidate" /><el-option
                    label="合格"
                    value="qualified" /><el-option
                    label="暂停"
                    value="suspended" /><el-option
                    label="黑名单"
                    value="blacklisted" /></el-select></el-form-item></el-col
            ><el-col :span="12"
              ><el-form-item label="风险等级"
                ><el-select v-model="form.risk_level" style="width: 100%"
                  ><el-option label="低" value="low" /><el-option
                    label="中"
                    value="medium" /><el-option
                    label="高"
                    value="high" /></el-select></el-form-item></el-col
          ></el-row>
          <el-row :gutter="16"
            ><el-col :span="8"
              ><el-form-item label="联系人"
                ><el-input v-model.trim="form.contact" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="电话"
                ><el-input v-model.trim="form.phone" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="邮箱"
                ><el-input
                  v-model.trim="form.email" /></el-form-item></el-col></el-row
          ><el-form-item label="地址"
            ><el-input v-model.trim="form.address"
          /></el-form-item>
        </template>
        <template v-else-if="active === 'materials'">
          <el-row :gutter="16"
            ><el-col :span="12"
              ><el-form-item label="物料编码" prop="code"
                ><el-input
                  v-model.trim="form.code"
                  :disabled="!!editingId" /></el-form-item></el-col
            ><el-col :span="12"
              ><el-form-item label="物料名称" prop="name"
                ><el-input
                  v-model.trim="form.name" /></el-form-item></el-col></el-row
          ><el-form-item label="规格型号"
            ><el-input v-model.trim="form.specification"
          /></el-form-item>
          <el-row :gutter="16"
            ><el-col :span="8"
              ><el-form-item label="分类"
                ><el-input
                  v-model.trim="form.category" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="计量单位"
                ><el-input v-model.trim="form.unit" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="采购提前期"
                ><el-input-number
                  v-model="form.lead_time_days"
                  :min="0"
                  :max="9999" /></el-form-item></el-col
          ></el-row>
          <el-row :gutter="16"
            ><el-col :span="8"
              ><el-form-item label="标准价格"
                ><el-input-number
                  v-model="form.standard_price"
                  :min="0"
                  :precision="4" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="安全库存"
                ><el-input-number
                  v-model="form.safety_stock"
                  :min="0"
                  :precision="2" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="启用"
                ><el-switch v-model="form.active" /></el-form-item></el-col
          ></el-row>
        </template>
        <template v-else>
          <el-row :gutter="16"
            ><el-col :span="12"
              ><el-form-item label="工厂编码" prop="code"
                ><el-input
                  v-model.trim="form.code"
                  :disabled="!!editingId" /></el-form-item></el-col
            ><el-col :span="12"
              ><el-form-item label="工厂名称" prop="name"
                ><el-input
                  v-model.trim="form.name" /></el-form-item></el-col></el-row
          ><el-form-item label="地址"
            ><el-input v-model.trim="form.address"
          /></el-form-item>
          <el-row :gutter="16"
            ><el-col :span="8"
              ><el-form-item label="联系人"
                ><el-input v-model.trim="form.contact" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="电话"
                ><el-input v-model.trim="form.phone" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="日收货能力"
                ><el-input-number
                  v-model="form.daily_receiving_capacity"
                  :min="0"
                  :precision="2" /></el-form-item></el-col
          ></el-row>
          <el-row :gutter="16"
            ><el-col :span="8"
              ><el-form-item label="纬度"
                ><el-input-number
                  v-model="form.latitude"
                  :min="-90"
                  :max="90"
                  :precision="7" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="经度"
                ><el-input-number
                  v-model="form.longitude"
                  :min="-180"
                  :max="180"
                  :precision="7" /></el-form-item></el-col
            ><el-col :span="8"
              ><el-form-item label="启用"
                ><el-switch v-model="form.active" /></el-form-item></el-col
          ></el-row>
        </template>
      </el-form>
      <span slot="footer"
        ><el-button @click="dialogVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存</el-button
        ></span
      >
    </el-dialog>
  </div>
</template>

<script>
import SupplierMetrics from "../components/SupplierMetrics.vue";
import SupplierQualifications from "../components/SupplierQualifications.vue";
import SupplierAccounts from "./SupplierAccounts.vue";
import AviationSupplierCapabilities from "../components/AviationSupplierCapabilities.vue";
import * as echarts from "echarts";
import {
  api,
  createMasterData,
  deleteMasterData,
  fetchMasterData,
  fetchProcurementAnalytics,
  updateMasterData,
} from "../api/client";

const emptyForms = {
  suppliers: () => ({
    code: "SUP-",
    name: "",
    unified_credit_code: "",
    category: "",
    status: "candidate",
    risk_level: "low",
    contact: "",
    email: "",
    phone: "",
    address: "",
  }),
  materials: () => ({
    code: "MAT-",
    name: "",
    specification: "",
    category: "",
    unit: "件",
    standard_price: 0,
    safety_stock: 0,
    lead_time_days: 0,
    active: true,
  }),
  factories: () => ({
    code: "F-",
    name: "",
    address: "",
    contact: "",
    phone: "",
    latitude: null,
    longitude: null,
    daily_receiving_capacity: 0,
    active: true,
  }),
};

export default {
  components: {
    SupplierAccounts,
    SupplierMetrics,
    SupplierQualifications,
    AviationSupplierCapabilities,
  },
  props: {
    mode: {
      type: String,
      default: "suppliers",
      validator: (value) => ["suppliers", "factories"].includes(value),
    },
  },
  watch: {
    isAdmin(value) {
      if (!value) this.accountsVisible = false;
    },
    mode(value) {
      this.charts.forEach((chart) => chart.dispose());
      this.charts = [];
      this.active = value;
      this.keyword = "";
      this.statusFilter = "";
      this.pagination.page = 1;
      this.form = emptyForms[value]();
      this.load();
      if (value === "suppliers") this.$nextTick(this.loadCharts);
    },
  },
  data: () => ({
    active: "suppliers",
    aviationCapabilitiesVisible: false,
    aviationSupplier: "",
    accountsVisible: false,
    metricsVisible: false,
    metricSupplier: "",
    qualificationsVisible: false,
    qualificationSupplier: "",
    items: [],
    keyword: "",
    statusFilter: "",
    loading: false,
    saving: false,
    dialogVisible: false,
    editingId: "",
    form: emptyForms.suppliers(),
    charts: [],
    pagination: { page: 1, page_size: 10, total: 0 },
    rules: {
      code: [{ required: true, message: "请输入编码", trigger: "blur" }],
      name: [{ required: true, message: "请输入名称", trigger: "blur" }],
    },
  }),
  computed: {
    isAdmin() {
      return this.$store.state.user.role === "admin";
    },
    activeLabel() {
      return { suppliers: "供应商", factories: "工厂" }[this.active];
    },
    pageTitle() {
      return this.active === "suppliers" ? "供应商管理与分析" : "工厂主数据";
    },
    pageEyebrow() {
      return this.active === "suppliers" ? "供应商中心" : "系统与知识库";
    },
    pageDescription() {
      return this.active === "suppliers"
        ? "维护供应商档案，分析质量、交付与服务绩效，统一管理供应商合作信息。"
        : "维护工厂地址、联系人、地理位置和日收货能力，为订单履约与多工厂路径优化提供统一数据。";
    },
  },
  created() {
    this.active = this.mode;
    this.form = emptyForms[this.active]();
    this.load();
  },
  mounted() {
    if (this.active === "suppliers") this.loadCharts();
    window.addEventListener("resize", this.resizeCharts);
  },
  beforeDestroy() {
    window.removeEventListener("resize", this.resizeCharts);
    this.charts.forEach((chart) => chart.dispose());
  },
  methods: {
    async seedAviationDemo() {
      try {
        await this.$confirm(
          "新增航空MRO教学供应商与物料；公开企业只作参考并标记为未核实，不覆盖现有数据。",
          "导入教学数据"
        );
        const r = (await api.post("/aviation-mro/demo")).data;
        this.$message.success(`已准备 ${r.result.suppliers} 家供应渠道`);
        await this.load();
      } catch (e) {
        if (e !== "cancel")
          this.$message.error(e.response?.data?.detail || "导入失败");
      }
    },
    async loadCharts() {
      try {
        const data = await fetchProcurementAnalytics();
        this.$nextTick(() => {
          const performance = echarts.init(this.$refs.performanceChart);
          const list = data.supplier_performance;
          performance.setOption({
            tooltip: { trigger: "axis" },
            legend: { data: ["质量", "交付"], bottom: 0 },
            grid: { left: 45, right: 15, top: 20, bottom: 60 },
            xAxis: {
              type: "category",
              data: list.map((i) => i.name),
              axisLabel: { rotate: 20 },
            },
            yAxis: { type: "value", min: 0, max: 100 },
            series: [
              { name: "质量", type: "bar", data: list.map((i) => i.quality) },
              { name: "交付", type: "bar", data: list.map((i) => i.delivery) },
            ],
          });
          const category = echarts.init(this.$refs.categoryChart);
          const categories = data.category_distribution.length
            ? data.category_distribution
            : [{ name: "暂无分类", value: 0 }];
          category.setOption({
            tooltip: { trigger: "axis" },
            grid: { left: 45, right: 15, top: 15, bottom: 70 },
            xAxis: {
              type: "category",
              data: categories.map((i) => i.name),
              axisLabel: { rotate: 25, overflow: "truncate", width: 90 },
            },
            yAxis: { type: "value", minInterval: 1 },
            series: [
              {
                type: "bar",
                data: categories.map((i) => i.value),
                itemStyle: { color: "#65a7ff", borderRadius: [5, 5, 0, 0] },
              },
            ],
          });
          this.charts = [performance, category];
        });
      } catch (_) {
        /* 主表仍可独立使用 */
      }
    },
    resizeCharts() {
      this.charts.forEach((chart) => chart.resize());
    },
    supplierStatusName(value) {
      return (
        {
          candidate: "候选",
          qualified: "合格",
          suspended: "暂停",
          blacklisted: "黑名单",
        }[value] || value
      );
    },
    supplierStatusType(value) {
      return (
        {
          candidate: "",
          qualified: "success",
          suspended: "warning",
          blacklisted: "danger",
        }[value] || "info"
      );
    },
    riskName(value) {
      return { low: "低", medium: "中", high: "高" }[value] || value;
    },
    riskType(value) {
      return (
        { low: "success", medium: "warning", high: "danger" }[value] || "info"
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
        if (this.active === "suppliers" && this.statusFilter)
          params.status = this.statusFilter;
        const result = await fetchMasterData(this.active, params);
        this.items = result.items;
        this.pagination.total = result.total;
      } catch (error) {
        this.$message.error("主数据加载失败");
      } finally {
        this.loading = false;
      }
    },
    changeTab() {
      this.keyword = "";
      this.statusFilter = "";
      this.pagination.page = 1;
      this.load();
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
      this.editingId = "";
      this.form = emptyForms[this.active]();
      this.dialogVisible = true;
      this.$nextTick(() => this.$refs.form && this.$refs.form.clearValidate());
    },
    openEdit(row) {
      this.editingId = row.id;
      this.form = {
        ...row,
        service_score: Number(row.service_score),
        quality_pass_rate: Number(row.quality_pass_rate),
        on_time_delivery_rate: Number(row.on_time_delivery_rate),
        standard_price: Number(row.standard_price),
        safety_stock: Number(row.safety_stock),
        daily_receiving_capacity: Number(row.daily_receiving_capacity),
        latitude: row.latitude === null ? null : Number(row.latitude),
        longitude: row.longitude === null ? null : Number(row.longitude),
      };
      this.dialogVisible = true;
    },
    updatePayload() {
      const excluded = new Set([
        "id",
        "code",
        "created_by",
        "created_at",
        "updated_at",
      ]);
      return Object.keys(this.form).reduce((result, key) => {
        if (
          !excluded.has(key) &&
          (this.active !== "suppliers" ||
            Object.keys(emptyForms.suppliers()).includes(key))
        )
          result[key] = this.form[key];
        return result;
      }, {});
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        this.saving = true;
        try {
          if (this.editingId)
            await updateMasterData(
              this.active,
              this.editingId,
              this.updatePayload()
            );
          else await createMasterData(this.active, this.form);
          this.$message.success(`${this.activeLabel}已保存`);
          this.dialogVisible = false;
          await this.load();
        } catch (error) {
          this.$message.error(
            (error.response &&
              error.response.data &&
              error.response.data.detail) ||
              `${this.activeLabel}保存失败`
          );
        } finally {
          this.saving = false;
        }
      });
    },
    async remove(row) {
      try {
        await this.$confirm(
          `确定删除 ${row.code} ${row.name} 吗？`,
          "删除确认",
          { type: "warning" }
        );
        await deleteMasterData(this.active, row.id);
        this.$message.success(`${this.activeLabel}已删除`);
        if (this.items.length === 1 && this.pagination.page > 1)
          this.pagination.page -= 1;
        await this.load();
      } catch (error) {
        if (error !== "cancel")
          this.$message.error(`${this.activeLabel}删除失败`);
      }
    },
  },
};
</script>

<template>
  <div class="warehouse-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">智能库存 · 多形态仓储网络</p>
        <h1>库存与仓储管理</h1>
        <p>按自有、寄售、VMI和修理回转四类仓库组织库存策略、盘点差异与检货任务。</p>
      </div>
      <el-button :loading="seeding" type="primary" @click="seedDemo">加入多形态库存演示数据</el-button>
    </div>

    <el-tabs v-model="activeType" type="card" class="warehouse-tabs" @tab-click="typeChanged">
      <el-tab-pane label="仓储总览" name="summary" />
      <el-tab-pane v-for="type in warehouseTypes" :key="type.value" :name="type.value">
        <span slot="label" class="warehouse-tab-label">
          {{ type.label }}
          <button v-if="taskCount(type.value)" type="button" class="task-tag" @click.stop="openTasks(type.value)">检货 {{ taskCount(type.value) }}</button>
        </span>
      </el-tab-pane>
    </el-tabs>

    <template v-if="activeType === 'summary'">
      <div class="summary-grid">
        <el-card v-for="type in warehouseTypes" :key="type.value" shadow="hover" class="summary-card" @click.native="activeType=type.value;subActive='inventory';resetPage()">
          <div class="summary-title"><strong>{{ type.label }}</strong><el-tag :type="type.tag">{{ warehouseCount(type.value) }} 个仓库</el-tag></div>
          <div class="summary-number">{{ availableByType(type.value) }}</div>
          <p>有效可用库存 · {{ inventoryCount(type.value) }} 条物料库存记录</p>
          <div class="summary-footer"><span>待检货 {{ taskCount(type.value) }}</span><span>盘点差异 {{ stocktakeCount(type.value) }}</span></div>
        </el-card>
      </div>
      <div class="chart-grid">
        <div class="chart-card"><h3>各类型仓库有效库存</h3><AnalysisChart :option="inventoryChart" /></div>
        <div class="chart-card"><h3>各类型待检货任务</h3><AnalysisChart :option="taskChart" /></div>
      </div>
    </template>

    <template v-else>
      <div class="warehouse-strip">
        <strong>{{ typeName(activeType) }}</strong>
        <span v-for="warehouse in currentWarehouses" :key="warehouse.code">
          {{ warehouse.name }}（{{ warehouse.code }}） · 负责人 {{ warehouse.manager || '待配置' }}
        </span>
      </div>
      <el-tabs v-model="subActive" type="border-card" @tab-click="resetPage">
        <el-tab-pane label="库存策略" name="inventory" />
        <el-tab-pane label="盘点差异" name="stocktakes" />
        <el-tab-pane name="tasks">
          <span slot="label">检货任务 <el-tag v-if="taskCount(activeType)" size="mini" type="danger">{{ taskCount(activeType) }}</el-tag></span>
        </el-tab-pane>
      </el-tabs>
      <div class="table-toolbar">
        <el-input v-model.trim="keyword" clearable placeholder="搜索物料、仓库、任务号" @keyup.enter.native="resetPage" @clear="resetPage" />
        <el-button icon="el-icon-search" @click="resetPage">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="pagedRows" class="data-table" :empty-text="emptyText">
        <template v-if="subActive === 'inventory'">
          <el-table-column prop="material_code" label="物料编码" width="150" />
          <el-table-column prop="warehouse_code" label="仓库" width="130" />
          <el-table-column label="库存形态" width="110"><template><el-tag :type="currentType.tag">{{ currentType.label }}</el-tag></template></el-table-column>
          <el-table-column prop="quantity" label="账面" />
          <el-table-column prop="reserved_quantity" label="预留" />
          <el-table-column prop="quarantined_quantity" label="隔离" />
          <el-table-column label="有效可用"><template slot-scope="s"><strong>{{ available(s.row) }}</strong></template></el-table-column>
          <el-table-column label="库存策略" min-width="220"><template slot-scope="s"><span v-if="policyFor(s.row)">安全 {{ policyFor(s.row).safety_stock }} / 再订货 {{ policyFor(s.row).reorder_point }} / 最高 {{ policyFor(s.row).max_stock }}</span><el-tag v-else size="mini" type="info">由{{ s.row.source_system }}外部策略管理</el-tag></template></el-table-column>
          <el-table-column prop="available_date" label="可用日期" width="110" />
          <el-table-column prop="source_system" label="来源系统" width="110" />
        </template>
        <template v-else-if="subActive === 'stocktakes'">
          <el-table-column prop="material_code" label="物料编码" />
          <el-table-column prop="warehouse_code" label="仓库" />
          <el-table-column prop="book_quantity" label="账面" />
          <el-table-column prop="counted_quantity" label="实盘" />
          <el-table-column label="差异"><template slot-scope="s"><strong :class="Number(s.row.variance) ? 'danger' : 'success'">{{ s.row.variance }}</strong></template></el-table-column>
          <el-table-column prop="reason" label="差异原因" min-width="220" />
          <el-table-column prop="counted_by" label="盘点人" />
          <el-table-column prop="counted_at" label="盘点时间" min-width="160" />
        </template>
        <template v-else>
          <el-table-column prop="task_no" label="检货任务号" width="200" />
          <el-table-column prop="material_code" label="物料编码" width="150" />
          <el-table-column prop="material_name" label="物料名称" min-width="170" />
          <el-table-column prop="warehouse_code" label="响应仓库" width="130" />
          <el-table-column prop="location_code" label="检货库位" width="110" />
          <el-table-column prop="quantity" label="数量" width="90" />
          <el-table-column label="状态" width="100"><template slot-scope="s"><el-tag :type="s.row.status==='pending_pick'?'warning':'success'">{{ s.row.status==='pending_pick'?'待检货':'已完成' }}</el-tag></template></el-table-column>
          <el-table-column prop="assigned_to" label="负责人" width="120" />
          <el-table-column prop="created_at" label="下发时间" min-width="165" />
        </template>
      </el-table>
      <div class="pagination-row">
        <span>共 {{ filteredRows.length }} 条</span>
        <el-pagination background layout="sizes, prev, pager, next" :page-sizes="[10,20,50]" :current-page="page" :page-size="pageSize" :total="filteredRows.length" @current-change="page=$event" @size-change="pageSize=$event;page=1" />
      </div>
    </template>
  </div>
</template>

<script>
import { api } from "../api/client";
import AnalysisChart from "../components/AnalysisChart.vue";

export default {
  components: { AnalysisChart },
  data: () => ({
    activeType: "summary",
    subActive: "inventory",
    warehouses: [],
    positions: [],
    tasks: [],
    stocks: [],
    stocktakes: [],
    loading: false,
    seeding: false,
    keyword: "",
    page: 1,
    pageSize: 10,
    warehouseTypes: [
      { value: "owned", label: "自有库", tag: "success" },
      { value: "consignment", label: "寄售库", tag: "warning" },
      { value: "vmi", label: "VMI库", tag: "primary" },
      { value: "repair_return", label: "修理回转库", tag: "danger" },
    ],
  }),
  computed: {
    currentType() { return this.warehouseTypes.find(item => item.value === this.activeType) || {}; },
    currentCodes() { return [...new Set(this.positions.filter(row => row.position_type === this.activeType).map(row => row.warehouse_code))]; },
    currentWarehouses() { return this.warehouses.filter(row => this.currentCodes.includes(row.code)); },
    activeRows() {
      if (this.subActive === "tasks") return this.tasks.filter(row => row.warehouse_type === this.activeType);
      if (this.subActive === "stocktakes") return this.stocktakes.filter(row => this.currentCodes.includes(row.warehouse_code));
      return this.positions.filter(row => row.position_type === this.activeType);
    },
    filteredRows() {
      const keyword = this.keyword.toLowerCase();
      if (!keyword) return this.activeRows;
      return this.activeRows.filter(row => [row.material_code, row.material_name, row.warehouse_code, row.task_no].some(value => String(value || "").toLowerCase().includes(keyword)));
    },
    pagedRows() { return this.filteredRows.slice((this.page - 1) * this.pageSize, this.page * this.pageSize); },
    emptyText() { return `暂无${this.currentType.label || "该类仓库"}${{ inventory: "库存策略", stocktakes: "盘点差异", tasks: "检货任务" }[this.subActive]}`; },
    inventoryChart() { return this.barOption("有效库存", this.warehouseTypes.map(item => this.availableByType(item.value)), "#1677ff"); },
    taskChart() { return this.barOption("待检货任务", this.warehouseTypes.map(item => this.taskCount(item.value)), "#f59e0b"); },
  },
  created() { this.load(); },
  methods: {
    error(error) { this.$message.error(error.response?.data?.detail || error.message || "操作失败"); },
    typeName(value) { return (this.warehouseTypes.find(item => item.value === value) || {}).label || value; },
    resetPage() { this.page = 1; },
    typeChanged() { this.subActive = "inventory"; this.keyword = ""; this.resetPage(); },
    openTasks(type) { this.activeType = type; this.subActive = "tasks"; this.keyword = ""; this.resetPage(); },
    available(row) { return Math.max(0, Number(row.quantity) - Number(row.reserved_quantity) - Number(row.quarantined_quantity)); },
    inventoryCount(type) { return this.positions.filter(row => row.position_type === type).length; },
    availableByType(type) { return this.positions.filter(row => row.position_type === type).reduce((sum, row) => sum + this.available(row), 0); },
    taskCount(type) { return this.tasks.filter(row => row.warehouse_type === type && row.status === "pending_pick").length; },
    warehouseCount(type) { return new Set(this.positions.filter(row => row.position_type === type).map(row => row.warehouse_code)).size; },
    stocktakeCount(type) { const codes = new Set(this.positions.filter(row => row.position_type === type).map(row => row.warehouse_code)); return this.stocktakes.filter(row => codes.has(row.warehouse_code) && Number(row.variance) !== 0).length; },
    policyFor(position) { return this.stocks.find(row => row.warehouse_code === position.warehouse_code && row.material_code === position.material_code); },
    barOption(name, data, color) { return { tooltip: { trigger: "axis" }, grid: { left: 55, right: 20, bottom: 40 }, xAxis: { type: "category", data: this.warehouseTypes.map(item => item.label) }, yAxis: { type: "value", minInterval: 1 }, series: [{ name, type: "bar", data, itemStyle: { color } }] }; },
    async load() {
      this.loading = true;
      try {
        const [warehouses, positions, tasks, stocks, stocktakes] = await Promise.all([
          api.get("/warehouses", { params: { page: 1, page_size: 100 } }),
          api.get("/warehouse-supply-positions", { params: { page: 1, page_size: 100 } }),
          api.get("/warehouse-picking-tasks", { params: { page: 1, page_size: 100 } }),
          api.get("/spare-stocks", { params: { page: 1, page_size: 100 } }),
          api.get("/stocktakes", { params: { page: 1, page_size: 100 } }),
        ]);
        this.warehouses = warehouses.data.items;
        this.positions = positions.data.items;
        this.tasks = tasks.data.items;
        this.stocks = stocks.data.items;
        this.stocktakes = stocktakes.data.items;
      } catch (error) { this.error(error); }
      finally { this.loading = false; }
    },
    async seedDemo() {
      this.seeding = true;
      try {
        await api.post("/mro-intelligence/demo");
        await this.load();
        this.$message.success("四类仓库与库存演示数据已加入");
      } catch (error) { this.error(error); }
      finally { this.seeding = false; }
    },
  },
};
</script>

<style scoped>
.warehouse-tabs{margin-bottom:16px}.warehouse-tab-label{display:flex;align-items:center;gap:7px}.task-tag{padding:2px 7px;border:0;border-radius:10px;background:#f56c6c;color:#fff;font-size:11px;line-height:16px;cursor:pointer}.task-tag:hover{background:#f23c3c}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}.summary-card{cursor:pointer}.summary-title,.summary-footer{display:flex;justify-content:space-between;gap:8px}.summary-number{font-size:30px;font-weight:700;color:#12395d;margin:18px 0 6px}.summary-card p{color:#718096}.summary-footer{padding-top:12px;border-top:1px solid #edf1f5;color:#516273}.warehouse-strip{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 16px;margin-bottom:14px;background:#f2f7fd;border:1px solid #dce9f7;border-radius:8px}.warehouse-strip span{padding:5px 9px;background:#fff;border-radius:6px;color:#52677c}.danger{color:#d92d20}.success{color:#12b76a}@media(max-width:1200px){.summary-grid{grid-template-columns:repeat(2,1fr)}}
</style>

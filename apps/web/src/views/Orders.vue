<template>
  <div>
    <div class="page-heading"><div><p class="eyebrow">采购执行</p><h1>采购订单</h1><p>从中标或合同生成订单，并跟踪审批、发送和履约。</p></div><el-button type="primary" @click="openCreate">新建订单</el-button></div>
    <div class="chart-grid compact-charts"><div class="chart-card"><div class="chart-title"><strong>订单状态结构</strong><span>全量订单（不随列表筛选）</span></div><div ref="statusChart" class="chart-box"></div></div><div class="chart-card"><div class="chart-title"><strong>供应商订单金额</strong><span>TOP 8</span></div><div ref="amountChart" class="chart-box"></div></div></div>
    <el-table :data="orders" class="data-table" empty-text="尚无订单，创建第一张采购订单">
      <el-table-column prop="order_no" label="订单编号" width="150" />
      <el-table-column prop="supplier_name" label="供应商" min-width="180" />
      <el-table-column prop="factory_code" label="工厂" width="100" />
      <el-table-column prop="status" label="状态" width="150"><template slot-scope="scope"><el-tag>{{ statusName(scope.row.status) }}</el-tag></template></el-table-column>
      <el-table-column prop="total_amount" label="含税金额" width="150"><template slot-scope="scope">{{ scope.row.currency }} {{ scope.row.total_amount }}</template></el-table-column>
      <el-table-column label="操作" width="350"><template slot-scope="scope"><el-button type="text" @click="traceOrder=scope.row">质量追溯</el-button><el-button type="text" :disabled="['completed','cancelled','quality_tracking','partially_delivered'].includes(scope.row.status)" @click="statusOrder=scope.row; nextStatus=scope.row.status">采购状态</el-button><el-button type="text" :disabled="scope.row.status !== 'draft'" @click="edit(scope.row)">编辑</el-button><el-button type="text" :disabled="!scope.row.template_id" @click="exportFile(scope.row, 'docx')">Word</el-button><el-button type="text" :disabled="!scope.row.template_id" @click="exportFile(scope.row, 'pdf')">PDF</el-button><el-button type="text" class="danger-link" :disabled="!['draft','cancelled'].includes(scope.row.status)" @click="remove(scope.row)">删除</el-button></template></el-table-column>
    </el-table>
    <div class="pagination-row"><span>共 {{ pagination.total }} 条</span><el-pagination background layout="sizes, prev, pager, next" :page-sizes="[10,20,50]" :current-page="pagination.page" :page-size="pagination.page_size" :total="pagination.total" @current-change="changePage" @size-change="changeSize" /></div>

    <el-dialog title="订单质量追溯" :visible="!!traceOrder" @close="traceOrder=null" width="88%" custom-class="analysis-dialog"><OrderTrace v-if="traceOrder" :key="traceOrder.id" :order-id="traceOrder.id"/></el-dialog>
    <el-dialog title="更新采购状态" :visible="!!statusOrder" @close="statusOrder=null" width="460px"><el-select v-model="nextStatus"><el-option v-for="s in ['draft','pending_approval','approved','sent','supplier_confirmed','cancelled']" :key="s" :value="s" :label="statusName(s)"/></el-select><p>收货后状态自动计算：待质检/不合格进入质量追溯；全部合格交付后完成。</p><span slot="footer"><el-button @click="statusOrder=null">取消</el-button><el-button type="primary" @click="saveStatus">保存</el-button></span></el-dialog>
    <el-dialog :title="editingId ? '编辑采购订单' : '创建采购订单'" :visible.sync="dialogVisible" width="720px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="供应商"><el-input v-model="form.supplier_name" /></el-form-item>
        <el-form-item label="供应商编码"><el-input v-model="form.supplier_id" /></el-form-item>
        <el-form-item label="收货工厂"><el-input v-model="form.factory_code" /></el-form-item>
        <el-form-item label="订单模板"><el-select v-model="form.template_id" clearable placeholder="选择订单模板" style="width:100%"><el-option v-for="template in orderTemplates" :key="template.id" :label="`${template.name} v${template.version}`" :value="template.id" /></el-select></el-form-item>
        <el-divider content-position="left">订单明细</el-divider>
        <div v-for="(line,index) in form.lines" :key="index" class="order-line-editor">
          <div class="dialog-section-title"><strong>明细 {{ index+1 }}</strong><el-button type="text" :disabled="form.lines.length===1" @click="form.lines.splice(index,1)">删除明细</el-button></div>
          <el-form-item label="物料编码"><el-input v-model.trim="line.material_code"/></el-form-item>
          <el-form-item label="物料名称"><el-input v-model.trim="line.material_name"/></el-form-item>
          <el-form-item label="承诺交期"><el-date-picker v-model="line.delivery_date" type="date" value-format="yyyy-MM-dd" placeholder="用于采购员交付及时率统计"/></el-form-item>
          <el-form-item label="数量 / 单价"><div class="inline-fields"><el-input v-model="line.quantity"/><el-input v-model="line.unit_price"/></div></el-form-item>
          <el-form-item label="单位 / 税率"><div class="inline-fields"><el-input v-model="line.unit"/><el-input v-model="line.tax_rate"/></div></el-form-item>
        </div><el-button @click="addLine">添加物料明细</el-button>
      </el-form>
      <span slot="footer"><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">{{ editingId ? '保存修改' : '创建订单' }}</el-button></span>
    </el-dialog>
  </div>
</template>

<script>
import * as echarts from "echarts";
import OrderTrace from "../components/OrderTrace.vue";
import { createOrder, deleteOrder, exportDocument, fetchOrders, fetchProcurementAnalytics, fetchTemplates, updateOrder } from "../api/client";

const emptyForm = () => ({
  supplier_id: "SUP-001", supplier_name: "", factory_code: "F01", currency: "CNY",
  lines: [{ material_code: "", material_name: "", specification: "", quantity: "1", unit: "件", unit_price: "0", tax_rate: "0.13" }]
});

export default {
  components: {OrderTrace},
  data: () => ({ traceOrder: null, statusOrder: null, nextStatus: "", orders: [], orderTemplates: [], dialogVisible: false, saving: false, form: emptyForm(), editingId: "", charts: [], pagination: { page: 1, page_size: 10, total: 0 } }),
  async created() { await Promise.all([this.load(), this.loadTemplates()]); },
  mounted() { this.loadCharts(); window.addEventListener("resize", this.resizeCharts); },
  beforeDestroy() { window.removeEventListener("resize", this.resizeCharts); this.charts.forEach(chart => chart.dispose()); },
  methods: {
    openCreate() { this.editingId=""; this.form=emptyForm(); this.dialogVisible=true; },
    addLine() { this.form.lines.push({...emptyForm().lines[0]}); },
    async loadCharts() { try { const data = await fetchProcurementAnalytics(); this.$nextTick(() => { const status = echarts.init(this.$refs.statusChart); const statuses = data.order_status.length ? data.order_status.map(i=>({...i,name:this.statusName(i.name)})) : [{ name: "暂无订单", value: 1 }]; status.setOption({ tooltip: { trigger: "item" }, legend: { orient: "vertical", left: 5, top: "middle" }, color: ["#2878ff", "#75cfa4", "#f6bd60", "#ef8354"], series: [{ type: "pie", radius: ["40%", "70%"], center: ["65%", "50%"], data: statuses }] }); const amount = echarts.init(this.$refs.amountChart); const amounts = data.supplier_amount.length ? data.supplier_amount : [{ name: "暂无数据", value: 0 }]; amount.setOption({ tooltip: { trigger: "axis" }, grid: { left: 95, right: 20, top: 15, bottom: 25 }, xAxis: { type: "value" }, yAxis: { type: "category", data: amounts.map(i => i.name) }, series: [{ type: "bar", data: amounts.map(i => i.value), itemStyle: { color: "#2878ff", borderRadius: [0, 5, 5, 0] } }] }); this.charts = [status, amount]; }); } catch (_) { /* 列表仍可独立使用 */ } },
    resizeCharts() { this.charts.forEach(chart => chart.resize()); },
    statusName(status) { return {draft:"草稿",pending_approval:"待审批",approved:"已审批",sent:"已发送",supplier_confirmed:"待送货",partially_delivered:"部分送货",quality_tracking:"质量追溯",completed:"完成",cancelled:"已取消"}[status]||status; },
    async saveStatus(){try{await updateOrder(this.statusOrder.id,{status:this.nextStatus});this.statusOrder=null;await this.load();this.$message.success("采购状态已更新");}catch(e){this.$message.error(e.response?.data?.detail||"状态更新失败");}},
    async load() { try { const result = await fetchOrders({ page: this.pagination.page, page_size: this.pagination.page_size }); this.orders = result.items; this.pagination.total = result.total; } catch (_) { this.$message.warning("请先启动后端API"); } },
    async loadTemplates() { const result = await fetchTemplates({ page: 1, page_size: 100, unfiltered: true }); this.orderTemplates = result.items.filter(template => template.template_type === "order" && template.status === "active"); },
    changePage(page) { this.pagination.page = page; this.load(); },
    changeSize(size) { this.pagination.page_size = size; this.pagination.page = 1; this.load(); },
    edit(order) { this.editingId = order.id; this.form = { ...order, lines: order.lines.map(line => ({ ...line })) }; this.dialogVisible = true; },
    async exportFile(order, outputFormat) { try { const result = await exportDocument("order", order.id, { template_id: order.template_id, output_format: outputFormat }); window.open(result.download_url, "_blank"); this.$message.success(`${outputFormat.toUpperCase()} 单据已生成`); } catch (error) { this.$message.error(error.response?.data?.detail || "单据生成失败"); } },
    async remove(order) { try { await this.$confirm(`确定删除订单 ${order.order_no} 吗？`, "删除确认", { type: "warning" }); await deleteOrder(order.id); this.$message.success("订单已删除"); if (this.orders.length === 1 && this.pagination.page > 1) this.pagination.page -= 1; await this.load(); } catch (error) { if (error !== "cancel") this.$message.error(error.response?.data?.detail || "订单删除失败"); } },
    async save() {
      this.saving = true;
      try { if (this.editingId) await updateOrder(this.editingId, { supplier_id: this.form.supplier_id, supplier_name: this.form.supplier_name, factory_code: this.form.factory_code, template_id: this.form.template_id || null, lines: this.form.lines }); else await createOrder(this.form); this.$message.success(this.editingId ? "订单已更新" : "订单已创建"); this.dialogVisible = false; this.form = emptyForm(); this.editingId = ""; await this.load(); }
      catch (error) { const detail=error.response?.data?.detail; this.$message.error(typeof detail==="string" ? detail : detail?.[0]?.msg || "订单保存失败"); }
      finally { this.saving = false; }
    }
  }
};
</script>

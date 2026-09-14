<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">PARAMETER RECOMMENDATION · COLLABORATION · LCC</p>
        <h1>智能库存与生命周期成本</h1>
        <p>
          以真实领用、设备故障、维护计划和交期推荐库存参数，并执行共享库存、VMI、寄售及LCC评审。
        </p>
      </div>
      <el-button
        v-if="active === 'agreements'"
        type="primary"
        @click="openAgreement()"
        >新增协同协议</el-button
      >
    </div>
    <div class="process-strip">
      <span>需求证据</span><i>→</i><span>参数推荐</span><i>→</i
      ><span>供应协同</span><i>→</i><span>LCC成本</span><i>→</i
      ><span>保存与执行</span>
    </div>
    <el-tabs v-model="active" type="card"
      ><el-tab-pane label="库存参数与LCC" name="analysis" /><el-tab-pane
        label="共享/VMI/寄售"
        name="agreements"
    /></el-tabs>

    <template v-if="active === 'analysis'">
      <el-card shadow="never" class="input-card"
        ><el-form inline
          ><el-form-item label="备件物料"
            ><el-select
              v-model="materialCode"
              filterable
              placeholder="选择备件"
              style="width: 280px"
              @change="resetAnalysis"
              ><el-option
                v-for="m in materials"
                :key="m.code"
                :label="`${m.code} · ${m.name}`"
                :value="m.code" /></el-select></el-form-item
          ><el-form-item label="场景"
            ><el-input v-model.trim="form.scenario_name" /></el-form-item
          ><el-form-item label="服务水平"
            ><el-select v-model="form.service_level"
              ><el-option
                v-for="n in [90, 95, 97, 99]"
                :key="n"
                :label="n + '%'"
                :value="n" /></el-select></el-form-item
          ><el-form-item label="评审周期"
            ><el-input-number v-model="form.review_days" :min="1" /><span>
              天</span
            ></el-form-item
          ><el-form-item label="分析年限"
            ><el-input-number
              v-model="form.horizon_years"
              :min="1"
              :max="30" /></el-form-item
        ></el-form>
        <el-divider content-position="left">生命周期成本假设（CNY）</el-divider
        ><el-form label-position="top" class="cost-form"
          ><el-row :gutter="12"
            ><el-col v-for="f in costFields" :key="f.key" :span="6"
              ><el-form-item :label="f.label"
                ><el-input-number
                  v-model="form[f.key]"
                  :min="0"
                  :precision="2"
                  style="width: 100%" /></el-form-item></el-col></el-row
        ></el-form>
        <div class="actions">
          <el-button type="primary" :loading="loading" @click="calculate(false)"
            >预览分析</el-button
          ><el-button type="success" :loading="loading" @click="calculate(true)"
            >计算并保存快照</el-button
          >
        </div></el-card
      >
      <template v-if="result"
        ><el-alert
          :title="result.lcc.formula"
          :description="result.warnings.join('；')"
          :type="result.warnings.length ? 'warning' : 'success'"
          :closable="false"
          show-icon
        />
        <div class="metric-grid">
          <div class="metric-card">
            <span>年需求基准</span
            ><strong>{{ result.evidence.annual_demand }}</strong
            ><small>{{ result.evidence.sample_count }}条实际样本</small>
          </div>
          <div class="metric-card">
            <span>安全 / 再订货点</span
            ><strong
              >{{ result.parameters.safety_stock }} /
              {{ result.parameters.reorder_point }}</strong
            ><small>服务水平 {{ result.parameters.service_level }}%</small>
          </div>
          <div class="metric-card">
            <span>最高库存</span
            ><strong>{{ result.parameters.max_stock }}</strong
            ><small>交期 {{ result.parameters.lead_time_days }}天</small>
          </div>
          <div class="metric-card">
            <span>{{ result.lcc.horizon_years }}年LCC</span
            ><strong>¥{{ money(result.lcc.total) }}</strong
            ><small>当前币种 {{ result.lcc.currency }}</small>
          </div>
        </div>
        <div class="chart-grid">
          <div class="chart-card">
            <h3>需求证据对比</h3>
            <AnalysisChart :option="demandChart" />
          </div>
          <div class="chart-card">
            <h3>LCC成本构成</h3>
            <AnalysisChart :option="lccChart" />
          </div>
        </div>
        <el-row :gutter="14"
          ><el-col :span="12"
            ><el-card shadow="never"
              ><h3>推荐参数计算规则</h3>
              <el-descriptions :column="1" border
                ><el-descriptions-item
                  v-for="(v, k) in result.rules"
                  :key="k"
                  :label="ruleName(k)"
                  >{{ v }}</el-descriptions-item
                ></el-descriptions
              ></el-card
            ></el-col
          ><el-col :span="12"
            ><el-card shadow="never"
              ><h3>已生效协同协议</h3>
              <el-table
                :data="result.collaborations"
                empty-text="暂无生效的共享/VMI/寄售协议"
                ><el-table-column prop="mode" label="模式"
                  ><template slot-scope="s">{{
                    modeName(s.row.mode)
                  }}</template></el-table-column
                ><el-table-column
                  prop="supplier_name"
                  label="供应商" /><el-table-column
                  prop="response_hours"
                  label="响应h" /><el-table-column
                  prop="service_level"
                  label="服务%" /></el-table></el-card></el-col
        ></el-row>
        <div class="actions">
          <el-button
            :disabled="!matchingStocks.length"
            type="warning"
            @click="applyParameters"
            >应用参数到该物料全部库存</el-button
          ><span v-if="!matchingStocks.length"
            >该物料尚无库存记录，推荐参数只能保存为分析快照。</span
          >
        </div>
        <h3>历史分析快照</h3>
        <el-table :data="history.items"
          ><el-table-column prop="scenario_name" label="场景" /><el-table-column
            prop="total_cost"
            label="LCC"
            ><template slot-scope="s"
              >¥{{ money(s.row.total_cost) }}</template
            ></el-table-column
          ><el-table-column prop="created_by" label="分析人" /><el-table-column
            prop="created_at"
            label="时间"
        /></el-table>
      </template>
    </template>

    <template v-else
      ><div class="table-toolbar">
        <el-input
          v-model.trim="keyword"
          clearable
          placeholder="物料、供应商"
          @keyup.enter.native="loadAgreements"
        /><el-select
          v-model="mode"
          clearable
          placeholder="全部模式"
          @change="loadAgreements"
          ><el-option label="共享库存" value="shared_stock" /><el-option
            label="VMI"
            value="vmi" /><el-option
            label="寄售"
            value="consignment" /></el-select
        ><el-button @click="loadAgreements">查询</el-button>
      </div>
      <el-table :data="agreements.items" v-loading="loading"
        ><el-table-column prop="material_code" label="物料" /><el-table-column
          prop="supplier_name"
          label="供应商"
        /><el-table-column
          prop="mode"
          label="模式"
          :formatter="formatMode"
        /><el-table-column
          prop="ownership"
          label="所有权"
          :formatter="formatOwner"
        /><el-table-column label="保障数量"
          ><template slot-scope="s"
            >{{ s.row.min_quantity }}～{{ s.row.max_quantity }}</template
          ></el-table-column
        ><el-table-column prop="response_hours" label="响应h" /><el-table-column
          prop="service_level"
          label="服务%"
        /><el-table-column
          prop="status"
          label="状态"
          :formatter="formatStatus"
        /><el-table-column label="操作" width="130" fixed="right"
          ><template slot-scope="s"
            ><el-button type="text" @click="openAgreement(s.row)"
              >编辑</el-button
            ><el-button
              type="text"
              class="danger-link"
              @click="removeAgreement(s.row)"
              >删除</el-button
            ></template
          ></el-table-column
        ></el-table
      >
      <div class="pagination-row">
        <span>共 {{ agreements.total }} 条</span
        ><el-pagination
          background
          layout="sizes,prev,pager,next"
          :total="agreements.total"
          :current-page="agreementPage.page"
          :page-size="agreementPage.page_size"
          @current-change="
            (p) => {
              agreementPage.page = p;
              loadAgreements();
            }
          "
        /></div
    ></template>

    <el-dialog
      :title="agreementForm.id ? '编辑协同协议' : '新增协同协议'"
      :visible.sync="agreementVisible"
      width="820px"
      :close-on-click-modal="false"
      ><el-form label-width="115px"
        ><el-row :gutter="14"
          ><el-col :span="12"
            ><el-form-item label="备件物料"
              ><el-select
                v-model="agreementForm.material_code"
                filterable
                style="width: 100%"
                ><el-option
                  v-for="m in materials"
                  :key="m.code"
                  :label="`${m.code} · ${m.name}`"
                  :value="m.code" /></el-select></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="供应商"
              ><el-select
                v-model="agreementForm.supplier_code"
                filterable
                style="width: 100%"
                @change="selectSupplier"
                ><el-option
                  v-for="s in suppliers"
                  :key="s.code"
                  :label="`${s.code} · ${s.name}`"
                  :value="s.code" /></el-select></el-form-item></el-col></el-row
        ><el-row :gutter="14"
          ><el-col :span="8"
            ><el-form-item label="协同模式"
              ><el-select v-model="agreementForm.mode"
                ><el-option label="共享库存" value="shared_stock" /><el-option
                  label="VMI"
                  value="vmi" /><el-option
                  label="寄售"
                  value="consignment" /></el-select></el-form-item></el-col
          ><el-col :span="8"
            ><el-form-item label="库存所有权"
              ><el-select v-model="agreementForm.ownership"
                ><el-option label="供应商" value="supplier" /><el-option
                  label="采购方"
                  value="buyer" /><el-option
                  label="共同"
                  value="shared" /></el-select></el-form-item></el-col
          ><el-col :span="8"
            ><el-form-item label="状态"
              ><el-select v-model="agreementForm.status"
                ><el-option label="草稿" value="draft" /><el-option
                  label="生效"
                  value="active" /><el-option
                  label="暂停"
                  value="paused" /><el-option
                  label="失效"
                  value="expired" /></el-select></el-form-item></el-col></el-row
        ><el-form-item label="补货规则"
          ><el-input
            v-model.trim="agreementForm.replenishment_rule"
            placeholder="例如：库存低于5件时供应商在24小时内补至15件" /></el-form-item
        ><el-form-item label="结算触发点"
          ><el-input
            v-model.trim="agreementForm.settlement_trigger"
            placeholder="领用、月结、所有权转移等" /></el-form-item
        ><el-row :gutter="14"
          ><el-col :span="6"
            ><el-form-item label="最低保障"
              ><el-input-number
                v-model="agreementForm.min_quantity"
                :min="0" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="最高保障"
              ><el-input-number
                v-model="agreementForm.max_quantity"
                :min="0" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="响应小时"
              ><el-input-number
                v-model="agreementForm.response_hours"
                :min="1" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="服务水平%"
              ><el-input-number
                v-model="agreementForm.service_level"
                :min="50"
                :max="100" /></el-form-item></el-col></el-row
        ><el-row :gutter="14"
          ><el-col :span="12"
            ><el-form-item label="开始日期"
              ><el-date-picker
                v-model="agreementForm.effective_from"
                value-format="yyyy-MM-dd" /></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="结束日期"
              ><el-date-picker
                v-model="agreementForm.effective_to"
                value-format="yyyy-MM-dd" /></el-form-item></el-col></el-row
        ><el-form-item label="协议与凭证"
          ><el-input
            v-model="agreementForm.evidence"
            type="textarea"
            :rows="3"
            placeholder="填写协议编号、所有权、盘点责任、退出机制和证据来源" /></el-form-item></el-form
      ><span slot="footer"
        ><el-button @click="agreementVisible = false">取消</el-button
        ><el-button type="primary" :loading="loading" @click="saveAgreement"
          >保存协议</el-button
        ></span
      ></el-dialog
    >
  </div>
</template>
<script>
import { api } from "../api/client";
import AnalysisChart from "../components/AnalysisChart.vue";
const analysisBlank = () => ({
  scenario_name: "五年基准方案",
  service_level: 95,
  review_days: 30,
  horizon_years: 5,
  unit_price: null,
  logistics_cost: 0,
  annual_maintenance_cost: 0,
  downtime_cost: 0,
  disposal_cost: 0,
  residual_value: 0,
  annual_holding_rate: 18,
});
const agreementBlank = () => ({
  id: "",
  material_code: "",
  supplier_code: "",
  supplier_name: "",
  mode: "vmi",
  ownership: "supplier",
  replenishment_rule: "",
  settlement_trigger: "",
  min_quantity: 0,
  max_quantity: 0,
  response_hours: 24,
  service_level: 95,
  effective_from: null,
  effective_to: null,
  status: "draft",
  evidence: "",
  version: 1,
});
export default {
  components: { AnalysisChart },
  data: () => ({
    active: "analysis",
    materials: [],
    suppliers: [],
    stocks: [],
    materialCode: "",
    form: analysisBlank(),
    result: null,
    history: { items: [], total: 0 },
    loading: false,
    costFields: [
      { key: "unit_price", label: "采购单价（默认标准价）" },
      { key: "logistics_cost", label: "期间物流与加急" },
      { key: "annual_maintenance_cost", label: "年度维护保养" },
      { key: "downtime_cost", label: "期间停机损失" },
      { key: "disposal_cost", label: "期末处置成本" },
      { key: "residual_value", label: "期末残值" },
      { key: "annual_holding_rate", label: "年持有率%" },
    ],
    agreements: { items: [], total: 0 },
    agreementPage: { page: 1, page_size: 10 },
    keyword: "",
    mode: "",
    agreementVisible: false,
    agreementForm: agreementBlank(),
  }),
  computed: {
    matchingStocks() {
      return this.stocks.filter((x) => x.material_code === this.materialCode);
    },
    demandChart() {
      const e = this.result.evidence;
      return {
        tooltip: { trigger: "axis" },
        xAxis: {
          type: "category",
          data: ["实际领用+故障", "维护计划年化", "BOM周期年化", "采用基准"],
        },
        yAxis: { type: "value", name: "数量/年" },
        series: [
          {
            type: "bar",
            data: [
              e.actual_consumption,
              e.planned_annual,
              e.lifecycle_annual,
              e.annual_demand,
            ],
            itemStyle: { color: "#3478f6" },
          },
        ],
      };
    },
    lccChart() {
      const p = this.result.lcc.parts;
      return {
        tooltip: { trigger: "axis" },
        xAxis: {
          type: "category",
          data: Object.keys(p),
          axisLabel: { rotate: 25 },
        },
        yAxis: { type: "value", name: "CNY" },
        series: [
          {
            type: "bar",
            data: Object.values(p),
            itemStyle: { color: "#10a37f" },
          },
        ],
      };
    },
  },
  async created() {
    const [m, s, st] = await Promise.all([
      api.get("/materials", {
        params: { material_type: "spare", page: 1, page_size: 100 },
      }),
      api.get("/suppliers", {
        params: { page: 1, page_size: 100, unfiltered: true },
      }),
      api.get("/spare-stocks", { params: { page: 1, page_size: 100 } }),
    ]);
    this.materials = m.data.items;
    this.suppliers = s.data.items;
    this.stocks = st.data.items;
    this.materialCode = this.materials[0]?.code || "";
    this.setStandardPrice();
    await Promise.all([
      this.loadAgreements(),
      this.materialCode ? this.calculate(false) : null,
    ]);
  },
  methods: {
    error(e) {
      this.$message.error(e.response?.data?.detail || "操作失败");
    },
    money(v) {
      return Number(v || 0).toLocaleString("zh-CN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    },
    modeName(v) {
      return (
        { shared_stock: "共享库存", vmi: "VMI", consignment: "寄售" }[v] || v
      );
    },
    ownerName(v) {
      return { supplier: "供应商", buyer: "采购方", shared: "共同" }[v] || v;
    },
    statusName(v) {
      return (
        { draft: "草稿", active: "生效", paused: "暂停", expired: "失效" }[v] ||
        v
      );
    },
    formatMode(row) {
      return this.modeName(row.mode);
    },
    formatOwner(row) {
      return this.ownerName(row.ownership);
    },
    formatStatus(row) {
      return this.statusName(row.status);
    },
    ruleName(k) {
      return (
        {
          demand: "需求口径",
          safety: "安全库存",
          reorder: "再订货点",
          max: "最高库存",
        }[k] || k
      );
    },
    setStandardPrice() {
      const m = this.materials.find((x) => x.code === this.materialCode);
      this.form.unit_price = m ? Number(m.standard_price) : 0;
    },
    resetAnalysis() {
      this.result = null;
      this.setStandardPrice();
      this.calculate(false);
    },
    async calculate(save) {
      if (!this.materialCode) return this.$message.warning("请选择备件物料");
      this.loading = true;
      try {
        this.result = (
          await api.post(
            `/inventory-intelligence/${encodeURIComponent(
              this.materialCode
            )}/analyze`,
            { ...this.form, save }
          )
        ).data;
        await this.loadHistory();
        if (save) this.$message.success("LCC分析快照已保存");
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async loadHistory() {
      if (!this.materialCode) return;
      this.history = (
        await api.get(
          `/inventory-intelligence/${encodeURIComponent(
            this.materialCode
          )}/history`,
          { params: { page: 1, page_size: 10 } }
        )
      ).data;
    },
    async applyParameters() {
      const p = this.result.parameters;
      try {
        await this.$confirm(
          `将推荐参数应用到该物料 ${this.matchingStocks.length} 条库存记录？`,
          "应用参数"
        );
        await api.post(
          `/inventory-intelligence/${encodeURIComponent(
            this.materialCode
          )}/apply-parameters`,
          {
            stock_ids: this.matchingStocks.map((x) => x.id),
            safety_stock: p.safety_stock,
            min_stock: p.min_stock,
            reorder_point: p.reorder_point,
            max_stock: p.max_stock,
          }
        );
        this.$message.success("库存参数已应用");
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
    async loadAgreements() {
      this.loading = true;
      try {
        this.agreements = (
          await api.get("/supply-collaborations", {
            params: {
              keyword: this.keyword,
              mode: this.mode,
              ...this.agreementPage,
            },
          })
        ).data;
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    openAgreement(row) {
      this.agreementForm = row
        ? {
            ...row,
            min_quantity: Number(row.min_quantity),
            max_quantity: Number(row.max_quantity),
            service_level: Number(row.service_level),
          }
        : agreementBlank();
      this.agreementVisible = true;
    },
    selectSupplier(code) {
      const s = this.suppliers.find((x) => x.code === code);
      if (s) this.agreementForm.supplier_name = s.name;
    },
    async saveAgreement() {
      const f = this.agreementForm;
      if (
        !f.material_code ||
        !f.supplier_code ||
        !f.replenishment_rule ||
        !f.settlement_trigger ||
        !f.evidence
      )
        return this.$message.warning(
          "请完整填写物料、供应商、补货、结算和凭证"
        );
      this.loading = true;
      try {
        await (f.id
          ? api.put("/supply-collaborations/" + f.id, f)
          : api.post("/supply-collaborations", f));
        this.agreementVisible = false;
        await this.loadAgreements();
        this.$message.success("协同协议已保存");
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async removeAgreement(row) {
      try {
        await this.$confirm("删除该协同协议？", "删除确认");
        await api.delete("/supply-collaborations/" + row.id, {
          params: { version: row.version },
        });
        await this.loadAgreements();
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
  },
};
</script>
<style scoped>
.input-card {
  margin-bottom: 16px;
}
.cost-form {
  margin-top: 10px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}
.chart-grid {
  margin: 16px 0;
}
.danger-link {
  color: #f56c6c;
}
</style>

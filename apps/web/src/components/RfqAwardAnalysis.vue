<template>
  <div v-loading="loading">
    <el-radio-group v-model="method" size="medium"
      ><el-radio-button label="lowest">1. 最低价中标</el-radio-button
      ><el-radio-button label="tco"
        >2. TOC分析定标</el-radio-button
      ></el-radio-group
    >
    <div v-if="method === 'tco'" style="margin: 16px 0">
      <el-button
        type="primary"
        size="small"
        @click="
          $refs.normalAnalysis.$el.scrollIntoView({
            behavior: 'smooth',
            block: 'start',
          })
        "
        >查看正态分析图</el-button
      ><el-button size="small" @click="showDemo">查看完整TOC演示</el-button
      ><el-button size="small" @click="showWeightDemo"
        >生成并查看权重演示</el-button
      ><el-button size="small" :loading="loading" @click="generateDemo"
        >生成当前询价模拟数据</el-button
      >
      <el-checkbox v-model="includeDemo" @change="load(false)"
        >包含模拟数据（仅演示）</el-checkbox
      ><el-alert
        v-if="includeDemo"
        title="模拟数据仅用于演示分析，不能执行正式TOC定标。"
        type="warning"
        :closable="false"
      />
    </div>
    <el-alert
      v-if="previewDemo"
      :title="`当前展示独立模拟案例 ${result.rfq_no}（模拟供货批次），不是当前询价的实际分析。原因：${previewReason}`"
      type="warning"
      :closable="false"
      show-icon
    />
    <p style="margin: 16px 0">{{ result.formula }}</p>
    <el-alert
      v-if="result.quoted_count && !result.review_ready"
      :title="`当前 ${result.verified_count || 0}/${
        result.quoted_count
      } 份报价核验通过；未核验报价不会参与最低价或TOC定标。`"
      type="warning"
      :closable="false"
    /><el-alert
      v-if="method === 'tco' && result.verified_count && !result.tco_ready"
      title="已核验的有效回标中，部分报价缺少至少3个已确认历史批次，暂不能进行完整TOC排名定标。"
      type="info"
      :closable="false"
    />
    <el-table :data="result.items || []" border
      ><el-table-column
        prop="supplier_name"
        label="供应商"
        min-width="150"
      /><el-table-column label="核验" width="90"
        ><template slot-scope="s"
          ><el-tag
            :type="s.row.review_status === 'verified' ? 'success' : 'warning'"
            >{{
              s.row.review_status === "verified" ? "已核验" : "待核验"
            }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column label="报价合计" width="150"
        ><template slot-scope="s">{{
          money(s.row.quoted_total)
        }}</template></el-table-column
      ><el-table-column v-if="method === 'tco'" label="预计综合成本" width="150"
        ><template slot-scope="s">{{
          money(s.row.tco_total)
        }}</template></el-table-column
      ><el-table-column label="分析结果"
        ><template slot-scope="s"
          ><el-tag
            v-if="recommended.includes(s.row.quotation_id)"
            type="success"
            >推荐中标</el-tag
          ><span v-else>{{
            s.row.reason ||
            (!s.row.valid
              ? "无效报价"
              : method === "tco" && s.row.tco_total === null
              ? "历史数据不足"
              : "非最低")
          }}</span></template
        ></el-table-column
      ><el-table-column label="选择" width="85"
        ><template slot-scope="s"
          ><el-radio
            v-model="selectedId"
            :label="s.row.quotation_id"
            :disabled="!recommended.includes(s.row.quotation_id)"
            ><span>选择</span></el-radio
          ></template
        ></el-table-column
      ><el-table-column type="expand"
        ><template slot-scope="s"
          ><el-table :data="s.row.materials"
            ><el-table-column
              prop="material_code"
              label="物料编码"
            /><el-table-column
              prop="material_name"
              label="物料名称"
            /><el-table-column prop="quantity" label="数量" /><el-table-column
              label="报价合计"
              ><template slot-scope="m">{{
                money(m.row.quoted)
              }}</template></el-table-column
            ><el-table-column label="预计TOC"
              ><template slot-scope="m">{{
                money(m.row.tco)
              }}</template></el-table-column
            ><el-table-column
              prop="cost_method"
              label="成本计算方法"
              min-width="150"
            /><el-table-column label="回归适用检查" min-width="200"
              ><template slot-scope="m">{{
                m.row.prediction.reason
              }}</template></el-table-column
            ><el-table-column label="有效历史批次"
              ><template slot-scope="m">{{
                m.row.profile.n
              }}</template></el-table-column
            ></el-table
          ></template
        ></el-table-column
      ></el-table
    >
    <section v-if="method === 'tco' && selectedModel" class="doe-gate">
      <h2>DOE六因子交叉验证与定价准入</h2>
      <el-alert
        :title="selectedModel.doe_validation.diagnostics.status"
        :type="selectedModel.pricing_usable ? 'success' : 'warning'"
        :description="
          selectedModel.pricing_usable
            ? '当前模型及全部因子验证通过，允许使用多元回归定价系数。'
            : '当前多元系数禁止用于正式定价；下方可建立30次DOE并记录实际响应，未通过时系统统一回退历史成本核算。'
        "
        :closable="false"
        show-icon
      />
      <el-select
        v-model="material"
        style="margin: 14px 0"
        @change="historyPage = 1"
      >
        <el-option v-for="m in materials" :key="m" :label="m" :value="m" />
      </el-select>
      <DoeAnalysis
        :key="material + '-' + selectedModel.fingerprint"
        :material="material"
        :fingerprint="selectedModel.fingerprint"
        :default-factors="doeFactors"
        :default-runs="30"
        design-kind="screening"
        response-label="实际单位TOC成本"
      />
    </section>
    <TocWeights
      v-if="method === 'tco'"
      :models="result.weight_models || {}"
      @refresh="load()"
    />
    <TocDistribution
      ref="normalAnalysis"
      v-if="method === 'tco'"
      :suppliers="result.items || []"
      :include-demo="includeDemo"
      :currency="result.currency"
    />
    <section v-if="method === 'tco'" style="margin-top: 24px">
      <h3>按物料查看各供应商回归曲线</h3>
      <el-select v-model="material" @change="historyPage = 1"
        ><el-option v-for="m in materials" :key="m" :label="m" :value="m"
      /></el-select>
      <p>
        横轴：历史含税采购单价；纵轴：历史单位合格品综合成本。至少5批且价格有变化才展示拟合线，R²仅表示历史拟合程度。
      </p>
      <ExplainableChart
        :option="regressionChart"
        title="供应商采购价格与综合成本回归曲线"
        interpretation="每个散点代表一个历史供货批次；同一供应商的曲线越低，在相同报价水平下预测的单位综合成本越低。R²越接近1表示历史拟合程度越高，但不能单独作为定标结论。"
        principle="以含税采购单价为自变量、单位合格交付综合成本为因变量进行一元线性回归；曲线反映历史样本内的统计关联，并通过批次数、价格变化范围和适用区间限制外推。"
      />
      <div v-for="s in profiles" :key="s.supplier">
        <strong>{{ s.supplier }}</strong
        >：{{ s.profile.n }}批；合格品率中位数
        {{
          s.profile.median_yield === null
            ? "—"
            : (s.profile.median_yield * 100).toFixed(2) + "%"
        }}；<span v-if="s.profile.regression"
          >y={{ s.profile.regression.slope.toFixed(4) }}x+{{
            s.profile.regression.intercept.toFixed(4)
          }}，R²={{
            s.profile.regression.r_squared === null
              ? "—"
              : s.profile.regression.r_squared.toFixed(3)
          }}</span
        ><span v-else>不足以拟合回归</span>
      </div>
      <el-table
        :data="history.slice((historyPage - 1) * 10, historyPage * 10)"
        max-height="320"
        ><el-table-column prop="supplier" label="供应商" /><el-table-column
          prop="external_id"
          label="来源批次"
        /><el-table-column prop="date" label="日期" /><el-table-column
          label="含税单价"
          ><template slot-scope="s">{{
            money(s.row.price)
          }}</template></el-table-column
        ><el-table-column label="单位综合成本"
          ><template slot-scope="s">{{
            money(s.row.cost)
          }}</template></el-table-column
        ><el-table-column label="数据"
          ><template slot-scope="s">{{
            s.row.is_demo ? "模拟" : "外部反馈"
          }}</template></el-table-column
        ></el-table
      ><el-pagination
        layout="prev,pager,next"
        :total="history.length"
        :page-size="10"
        :current-page.sync="historyPage"
      />
    </section>
    <div style="text-align: right; margin-top: 24px">
      <el-button @click="$emit('close')">关闭</el-button
      ><el-button
        type="primary"
        :disabled="
          previewDemo ||
          !recommended.includes(selectedId) ||
          (method === 'tco' && includeDemo)
        "
        :loading="saving"
        @click="award"
        >确认{{ method === "lowest" ? "最低价" : "TOC" }}定标</el-button
      >
    </div>
  </div>
</template>
<script>
import TocDistribution from "./TocDistribution.vue";
import TocWeights from "./TocWeights.vue";
import { api } from "../api/client";
import ExplainableChart from "./ExplainableChart.vue";
import DoeAnalysis from "./DoeAnalysis.vue";
export default {
  components: { DoeAnalysis, ExplainableChart, TocDistribution, TocWeights },
  props: { rfqId: String },
  data: () => ({
    method: "lowest",
    includeDemo: false,
    previewDemo: false,
    previewReason: "",
    result: {},
    loading: false,
    saving: false,
    selectedId: "",
    material: "",
    historyPage: 1,
  }),
  created() {
    this.load();
  },
  watch: {
    method() {
      this.selectedId = "";
      this.load(this.method === "tco");
    },
  },
  computed: {
    recommended() {
      return (
        (this.method === "lowest"
          ? this.result.lowest_ids
          : this.result.tco_ids) || []
      );
    },
    materials() {
      return [
        ...new Set(
          (this.result.items || []).flatMap((s) =>
            s.materials.map((m) => m.material_code)
          )
        ),
      ];
    },
    profiles() {
      return (this.result.items || []).flatMap((s) =>
        s.materials
          .filter((m) => m.material_code === this.material)
          .map((m) => ({ supplier: s.supplier_name, profile: m.profile }))
      );
    },
    history() {
      return this.profiles.flatMap((s) =>
        s.profile.samples.map((p) => ({ ...p, supplier: s.supplier }))
      );
    },
    selectedModel() {
      return (this.result.weight_models || {})[this.material] || null;
    },
    doeFactors() {
      if (!this.selectedModel) return [];
      return this.selectedModel.features.map((feature, index) => {
        const weight = this.selectedModel.weights[index] || {};
        const low = Number.isFinite(weight.min) ? weight.min : 0;
        return {
          name: feature.label,
          low,
          high:
            Number.isFinite(weight.max) && weight.max > low
              ? weight.max
              : low + 1,
        };
      });
    },
    regressionChart() {
      return {
        tooltip: { trigger: "item" },
        legend: { type: "scroll" },
        grid: { left: 75, right: 25, top: 55, bottom: 55 },
        xAxis: { type: "value", name: "含税单价", scale: true },
        yAxis: { type: "value", name: "单位综合成本", scale: true },
        series: this.profiles.flatMap((s) => [
          {
            name: s.supplier,
            type: "scatter",
            data: s.profile.samples
              .filter((p) => p.cost !== null)
              .map((p) => [p.price, p.cost]),
          },
          ...(s.profile.regression
            ? [
                {
                  name: s.supplier,
                  type: "line",
                  showSymbol: false,
                  data: s.profile.regression.line,
                },
              ]
            : []),
        ]),
      };
    },
  },
  methods: {
    async showWeightDemo() {
      try {
        await this.$confirm(
          "生成独立的240批多指标模拟数据，仅用于权重演示，不参与正式定标。",
          "权重演示"
        );
        this.loading = true;
        this.result = (
          await api.post("/supply-feedback/weight-demo", null, {
            timeout: 60000,
          })
        ).data;
        this.previewDemo = true;
        this.previewReason = "独立多指标权重演示";
        this.includeDemo = true;
        this.material = this.materials[0] || "";
        this.selectedId = "";
      } catch (e) {
        if (e !== "cancel") this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async showDemo() {
      try {
        this.loading = true;
        let response;
        try {
          response = await api.get("/supply-feedback/demo-analysis");
        } catch (e) {
          if (e.response?.status !== 404) throw e;
          await api.post("/supply-feedback/demo");
          response = await api.get("/supply-feedback/demo-analysis");
        }
        this.result = response.data;
        this.previewDemo = true;
        this.includeDemo = true;
        this.material = this.materials[0] || "";
        this.selectedId = "";
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async generateDemo() {
      try {
        await this.$confirm(
          "为当前已回标供应商和物料生成模拟供货批次？所有批次标记为模拟，仅用于演示。",
          "生成模拟数据"
        );
        this.loading = true;
        const r = (await api.post(`/rfqs/${this.rfqId}/demo-feedback`)).data;
        this.includeDemo = true;
        await this.load();
        this.$message.success(r.message);
      } catch (e) {
        if (e !== "cancel") this.error(e);
      } finally {
        this.loading = false;
      }
    },
    money(v) {
      return v === null || v === undefined ? "数据不足" : Number(v).toFixed(2);
    },
    error(e) {
      this.$message.error(e.response?.data?.detail || "分析失败");
    },
    async load(autoPreview = false) {
      this.loading = true;
      this.previewDemo = false;
      try {
        if (this.method === "lowest") this.includeDemo = false;
        else if (autoPreview) this.includeDemo = true;
        this.result = (
          await api.get(`/rfqs/${this.rfqId}/award-analysis`, {
            params: { include_demo: this.includeDemo },
          })
        ).data;
        this.material = this.materials.includes(this.material)
          ? this.material
          : this.materials[0] || "";
        this.selectedId = "";
        if (autoPreview && this.result.review_ready && !this.result.tco_ready) {
          this.previewReason =
            (this.result.items || []).find((r) => r.reason)?.reason ||
            "当前询价尚无足够的有效报价或供货批次";
          await this.showDemo();
        }
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async award() {
      if (this.previewDemo) return;
      try {
        await this.$confirm(
          "确认按当前分析结果整单定标？系统将重新核验最新数据并锁定询价。",
          "确认定标"
        );
        this.saving = true;
        await api.post(`/rfqs/${this.rfqId}/award`, {
          quotation_id: this.selectedId,
          method: this.method,
        });
        this.$message.success("定标完成");
        this.$emit("awarded");
      } catch (e) {
        if (e !== "cancel") this.error(e);
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<template>
  <section>
    <h3>DOE试验设计与数据诊断</h3>
    <el-alert
      title="历史回归通过不等于DOE验证通过。未执行试验时不生成验证结论。因素必须可操控，并经安全及业务评审。"
      type="warning"
      :closable="false"
    />
    <p>
      {{
        designKind === "three_level"
          ? "三水平分类全因子"
          : designKind === "screening"
          ? "两水平筛选"
          : "两水平全因子"
      }}设计：{{ factors.length }}个因素，建议至少 {{ minimum }} 次；当前计划
      {{ runs || minimum }} 次。次数可调整，正式执行前须评审统计功效。
    </p>
    <el-table :data="factors" size="small"
      ><el-table-column label="可控因素名称"
        ><template slot-scope="s"
          ><el-input
            v-model="s.row.name"
            placeholder="填写已评审的可控因素" /></template></el-table-column
      ><el-table-column label="低水平"
        ><template slot-scope="s"
          ><el-input-number v-model="s.row.low" /></template></el-table-column
      ><el-table-column label="高水平"
        ><template slot-scope="s"
          ><el-input-number v-model="s.row.high" /></template></el-table-column
      ><el-table-column width="80"
        ><template slot-scope="s"
          ><el-button
            :disabled="factors.length <= 1"
            @click="factors.splice(s.$index, 1)"
            >移除</el-button
          ></template
        ></el-table-column
      ></el-table
    ><el-button
      :disabled="factors.length >= 6"
      @click="factors.push({ name: '', low: 0, high: 1 })"
      >添加因素</el-button
    ><span>试验次数（0=自动推荐）</span
    ><el-input-number
      v-model="runs"
      :min="0"
      :max="128"
      :precision="0"
    /><el-button type="primary" :loading="loading" @click="create"
      >生成并保存DOE方案</el-button
    ><el-button @click="load">刷新历史</el-button>
    <el-collapse v-model="opened"
      ><el-collapse-item
        v-for="s in studies"
        :key="s.id"
        :name="s.id"
        :title="s.method + ' · ' + s.runs + '次 · ' + s.diagnostics.status"
        ><p>{{ s.note }}</p>
        <p>关联模型：{{ s.model_fingerprint }}；记录编号：{{ s.id }}</p>
        <el-alert
          v-if="s.diagnostics.completed === s.runs"
          :title="s.diagnostics.status"
          :type="s.diagnostics.passed ? 'success' : 'warning'"
          :description="
            s.diagnostics.passed
              ? '全部因子已通过显著性、五折方向稳定性和系数波动检查，可进入当前模型定价系数。'
              : '未通过或模拟试验的因子禁止进入正式定价系数；系统将使用不含回归系数的历史成本核算。'
          "
          :closable="false"
          show-icon
        />
        <el-table :data="s.design" max-height="300" border
          ><el-table-column
            prop="run"
            label="随机执行序号"
            width="110" /><el-table-column
            v-for="(f, i) in s.factors"
            :key="f.name"
            :label="f.name"
            ><template slot-scope="r">{{
              r.row.levels[i]
            }}</template></el-table-column
          ><el-table-column :label="responseLabel + '（手动记录）'" width="230"
            ><template slot-scope="r"
              ><el-input
                :value="responseValue(s.values[r.$index])"
                type="number"
                step="0.0001"
                placeholder="请输入实际响应"
                @input="setResponse(s, r.$index, $event)" /></template></el-table-column></el-table
        ><el-switch
          v-model="s.simulated"
          active-text="模拟试验"
          inactive-text="实际试验"
        /><el-input
          v-model="s.evidence"
          placeholder="试验来源、操作者、记录编号与测量口径"
        /><el-button @click="save(s)">保存响应并运行诊断</el-button>
        <div class="chart-grid">
          <ExplainableChart
            :option="runChart(s)"
            title="DOE执行序列与响应"
            interpretation="横轴是随机化后的试验顺序，记录值表示每次组合得到的实际或模拟响应，拟合线表示主效应模型的样本内预测。两线偏差较大的位置应检查执行条件或遗漏因素。"
            principle="DOE通过有计划地改变因素水平并随机化执行顺序，分离因素效应与时间漂移；拟合值来自设计矩阵的最小二乘主效应模型。"
          /><ExplainableChart
            v-if="s.diagnostics.residuals"
            :option="residualChart(s)"
            title="拟合值与残差"
            interpretation="散点应围绕零线随机分布；漏斗形提示方差不稳定，弧形提示非线性，孤立大残差提示异常试验或遗漏条件。"
            principle="残差等于记录响应减去模型拟合值。残差图用于检查线性、等方差和独立性假设，不是独立预测验证。"
          /><ExplainableChart
            v-if="s.diagnostics.qq"
            :option="qqChart(s)"
            title="DOE残差正态Q-Q图"
            interpretation="点越接近直线，残差越接近正态；两端明显偏离需要检查厚尾、异常值或模型结构不足。"
            principle="按顺序比较残差样本分位数与理论正态分位数，用于评估误差分布假设；小样本下应结合残差图和业务证据。"
          /><ExplainableChart
            v-if="s.diagnostics.coefficients"
            :option="coefficientChart(s)"
            title="DOE主效应系数"
            interpretation="柱子的正负表示因素从低水平到高水平时响应变化方向，绝对值越大表示该因素在本试验范围内的主效应越强。分类编码方向须结合ABC、VED、FSN等级映射解释。"
            principle="系数由编码尺度设计矩阵拟合得到，使不同量纲因素可比较方向与相对效应；未纳入交互项时不能把主效应解释为完整因果关系。"
          /><ExplainableChart
            v-if="
              s.diagnostics.cross_validation &&
              s.diagnostics.cross_validation.predicted.length
            "
            :option="crossValidationChart(s)"
            title="DOE五折交叉验证：实测与预测"
            interpretation="散点越接近45度参考线，说明不同留出折上的预测越一致；系统不是只看样本内拟合，而是让每一折数据都在未参与拟合时接受预测。"
            principle="系统固定分成最多5折，每次用其余折拟合主效应，再预测被留出的一折，汇总得到交叉验证R²、MAE、RMSE及各折系数稳定性。"
          />
        </div>
        <h4 v-if="s.diagnostics.factor_validation">因子定价准入结论</h4>
        <el-table
          v-if="s.diagnostics.factor_validation"
          :data="s.diagnostics.factor_validation"
          border
          size="small"
        >
          <el-table-column prop="name" label="因子" min-width="180" />
          <el-table-column label="主效应p值" width="115"
            ><template slot-scope="r">{{
              number(r.row.p_value)
            }}</template></el-table-column
          >
          <el-table-column label="跨折方向一致率" width="135"
            ><template slot-scope="r">{{
              percent(r.row.sign_consistency)
            }}</template></el-table-column
          >
          <el-table-column label="系数变异CV" width="115"
            ><template slot-scope="r">{{
              percent(r.row.coefficient_cv)
            }}</template></el-table-column
          >
          <el-table-column label="定价准入" width="105"
            ><template slot-scope="r"
              ><el-tag :type="r.row.eligible ? 'success' : 'danger'">{{
                r.row.eligible ? "允许纳入" : "禁止纳入"
              }}</el-tag></template
            ></el-table-column
          >
          <el-table-column label="诊断原因" min-width="210"
            ><template slot-scope="r">{{
              r.row.reasons.join("；") || "全部规则通过"
            }}</template></el-table-column
          >
        </el-table>
        <p v-if="s.diagnostics.cross_validation">
          五折交叉验证：R²
          {{ number(s.diagnostics.cross_validation.r_squared) }}；MAE
          {{ number(s.diagnostics.cross_validation.mae) }}；RMSE
          {{ number(s.diagnostics.cross_validation.rmse) }}。
        </p>
        <p v-if="s.diagnostics.lack_of_fit">
          失拟检验 p：{{
            s.diagnostics.lack_of_fit.p === null
              ? "不可计算"
              : s.diagnostics.lack_of_fit.p
          }}；{{ s.diagnostics.lack_of_fit.note }}
        </p>
        <p v-if="s.diagnostics.rmse !== undefined">
          样本内RMSE：{{ s.diagnostics.rmse }}；残差自由度：{{
            s.diagnostics.residual_df
          }}。定价准入还必须同时满足上方交叉验证与正式试验证据规则。
        </p></el-collapse-item
      ></el-collapse
    >
  </section>
</template>
<script>
import { api } from "../api/client";
import ExplainableChart from "./ExplainableChart.vue";
export default {
  components: { ExplainableChart },
  props: {
    material: String,
    fingerprint: { type: String, default: "unfitted" },
    defaultFactors: { type: Array, default: () => [] },
    defaultRuns: { type: Number, default: 0 },
    designKind: { type: String, default: "full_factorial" },
    responseLabel: { type: String, default: "单位TOC响应" },
  },
  data() {
    return {
      factors: this.defaultFactors.length
        ? this.defaultFactors.map((f) => ({ ...f }))
        : [
            { name: "", low: 0, high: 1 },
            { name: "", low: 0, high: 1 },
          ],
      runs: this.defaultRuns,
      studies: [],
      opened: [],
      loading: false,
    };
  },
  computed: {
    minimum() {
      return this.designKind === "three_level"
        ? 3 ** this.factors.length + 3
        : this.designKind === "screening"
        ? Math.max(12, this.factors.length * 2 + 2)
        : 2 ** this.factors.length + 2;
    },
  },
  watch: {
    material() {
      this.load();
    },
  },
  mounted() {
    this.load();
  },
  methods: {
    number(value) {
      return value === null || value === undefined
        ? "—"
        : Number(value).toFixed(4);
    },
    percent(value) {
      return value === null || value === undefined
        ? "—"
        : (Number(value) * 100).toFixed(1) + "%";
    },
    responseValue(value) {
      return value === null || value === undefined ? "" : value;
    },
    setResponse(study, index, value) {
      this.$set(study.values, index, value === "" ? null : Number(value));
    },
    qqChart(s) {
      return {
        title: { text: "残差正态QQ图" },
        tooltip: {},
        xAxis: { type: "value", name: "理论分位数" },
        yAxis: { type: "value", name: "残差分位数" },
        series: [{ type: "scatter", data: s.diagnostics.qq }],
      };
    },
    coefficientChart(s) {
      return {
        title: { text: "DOE编码尺度主效应系数" },
        tooltip: {},
        xAxis: { type: "category", data: s.factors.map((f) => f.name) },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: s.diagnostics.coefficients.slice(1) }],
      };
    },
    crossValidationChart(s) {
      const actual = s.values || [];
      const predicted = s.diagnostics.cross_validation.predicted || [];
      const values = actual.filter((value) => value !== null).concat(predicted);
      const low = Math.min(...values);
      const high = Math.max(...values);
      return {
        tooltip: { trigger: "item" },
        xAxis: { type: "value", name: "实测响应", scale: true },
        yAxis: { type: "value", name: "交叉验证预测", scale: true },
        series: [
          {
            name: "留出折预测",
            type: "scatter",
            data: actual.map((value, index) => [value, predicted[index]]),
          },
          {
            name: "45°参考",
            type: "line",
            showSymbol: false,
            data: [
              [low, low],
              [high, high],
            ],
          },
        ],
      };
    },
    error(e) {
      const detail = e.response?.data?.detail;
      const validation = Array.isArray(detail)
        ? detail.map((item) => item.msg).filter(Boolean).join("；")
        : "";
      this.$message.error(
        typeof detail === "string"
          ? detail
          : validation || "请求失败，请检查输入数据"
      );
    },
    async load() {
      if (!this.material) return;
      try {
        this.studies = (
          await api.get("/toc-doe", {
            params: {
              material_code: this.material,
              model_fingerprint: this.fingerprint || "unfitted",
            },
          })
        ).data.items;
        this.opened = this.studies.length ? [this.studies[0].id] : [];
      } catch (e) {
        this.error(e);
      }
    },
    async create() {
      this.loading = true;
      try {
        await api.post("/toc-doe", {
          material_code: this.material,
          model_fingerprint: this.fingerprint || "unfitted",
          factors: this.factors,
          runs: this.runs || null,
          design_kind: this.designKind,
        });
        await this.load();
        this.$message.success("DOE方案已保存，待实际执行");
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async save(s) {
      const missing = s.values.filter(
        (value) =>
          value === null ||
          value === undefined ||
          value === "" ||
          !Number.isFinite(Number(value))
      ).length;
      if (missing) {
        this.$message.warning(
          `DOE方案已保存，但尚有 ${missing} 次试验未录入响应，暂时不能运行诊断`
        );
        return;
      }
      if (!String(s.evidence || "").trim()) {
        this.$message.warning(
          "请填写试验记录依据，包括来源、操作者、记录编号和测量口径"
        );
        return;
      }
      try {
        await api.put("/toc-doe/" + s.id, {
          values: s.values,
          evidence: s.evidence,
          version: s.version,
          simulated: s.simulated,
        });
        await this.load();
        this.$message.success("响应已保存，DOE诊断已更新");
      } catch (e) {
        this.error(e);
      }
    },
    runChart(s) {
      return {
        title: { text: "DOE执行序列与响应" },
        tooltip: { trigger: "axis" },
        legend: { top: 28 },
        grid: { top: 65, left: 65, bottom: 45 },
        xAxis: { type: "category", data: s.design.map((r) => r.run) },
        yAxis: { type: "value" },
        series: [
          { name: "记录值", type: "line", data: s.values },
          {
            name: "样本内拟合",
            type: "line",
            data: s.diagnostics.predicted || [],
          },
        ],
      };
    },
    residualChart(s) {
      return {
        title: { text: "拟合值与残差（非独立验证）" },
        tooltip: {},
        xAxis: { type: "value", name: "拟合值" },
        yAxis: { type: "value", name: "残差" },
        series: [
          {
            type: "scatter",
            data: s.diagnostics.residuals.map((r, i) => [
              s.diagnostics.predicted[i],
              r,
            ]),
          },
        ],
      };
    },
  },
};
</script>

<template>
  <el-dialog
    :title="'物料联合策略分析 · ' + material"
    :visible="!!material"
    @close="$emit('close')"
    width="94%"
    top="3vh"
    append-to-body
    :close-on-click-modal="false"
  >
    <div v-loading="busy">
      <p>{{ context.name }} · {{ context.note }}</p>
      <el-alert
        v-if="context.aviation"
        :title="`航空适航硬门槛：PN ${
          context.aviation.part_number || material
        } · ${context.aviation.oem || 'OEM待确认'} · ATA ${
          context.aviation.ata_chapter || '待确认'
        }`"
        :description="`必须先验证供应商能力准入、适用机型、${
          (context.aviation.certificates_required || []).join('/') || '适航证书'
        }、全链路追溯和剩余寿命≥${
          context.aviation.minimum_remaining_life_percent || 0
        }%，未通过的方案不得参与价格推荐。`"
        type="error"
        show-icon
        :closable="false"
      />
      <el-alert
        v-if="form.simulated"
        title="当前为明确标识的模拟场景，分析与快照均保留模拟标记。"
        type="warning"
        :closable="false"
      />
      <div style="margin: 16px 0">
        <el-button @click="example">载入演示场景</el-button
        ><el-button type="primary" @click="calculate(false)">重新分析</el-button
        ><el-button @click="calculate(true)">计算并保存快照</el-button
        ><el-tag v-if="dirty" type="warning">输入已修改，需重新分析</el-tag>
      </div>
      <el-tabs v-model="tab">
        <el-tab-pane label="1. 需求与约束" name="input">
          <el-form label-position="top"
            ><el-row :gutter="18"
              ><el-col v-for="f in fields" :key="f.key" :span="6"
                ><el-form-item :label="f.label"
                  ><el-input
                    type="number"
                    :value="form[f.key]"
                    placeholder="待补充"
                    @input="
                      $set(form, f.key, $event === '' ? null : Number($event))
                    " /></el-form-item></el-col
            ></el-row>
            <el-row :gutter="18"
              ><el-col :span="6"
                ><el-form-item label="必要到货日期"
                  ><el-date-picker
                    v-model="form.required_date"
                    value-format="yyyy-MM-dd"
                    style="width: 100%" /></el-form-item></el-col
              ><el-col :span="6"
                ><el-form-item label="设备关键性"
                  ><el-select v-model="form.critical"
                    ><el-option label="关键设备" :value="true" /><el-option
                      label="一般设备"
                      :value="false" /></el-select></el-form-item></el-col
              ><el-col :span="6"
                ><el-form-item label="处理负责人"
                  ><el-input v-model="form.owner" /></el-form-item></el-col
              ><el-col :span="6"
                ><el-form-item label="库存口径"
                  ><el-checkbox v-model="form.inventory_confirmed"
                    >已扣除预留及不可用量</el-checkbox
                  >
                  <p>
                    在库参考 {{ context.inventory }}，{{ context.stock_rows }}
                    条记录
                  </p></el-form-item
                ></el-col
              ></el-row
            >
            <el-row v-if="context.aviation" :gutter="18">
              <el-col :span="6"
                ><el-form-item label="航空需求类型"
                  ><el-select v-model="form.demand_type" style="width: 100%"
                    ><el-option label="计划需求" value="planned" /><el-option
                      label="Non-routine"
                      value="non_routine" /><el-option
                      label="AOG停场"
                      value="aog" /></el-select></el-form-item
              ></el-col>
              <el-col v-if="form.demand_type === 'aog'" :span="6"
                ><el-form-item label="要求响应小时"
                  ><el-input-number
                    v-model="form.required_within_hours"
                    :min="1"
                    :max="8760"
                    controls-position="right" /></el-form-item
              ></el-col>
            </el-row>
            <el-form-item
              label="数据来源、统计期间及参数依据（费用统一CNY，同含税口径）"
              ><el-input
                v-model="form.evidence"
                type="textarea" /></el-form-item
          ></el-form>
        </el-tab-pane>
        <el-tab-pane label="2. 候选方案" name="candidates">
          <el-button @click="add">添加候选方案</el-button>
          <el-card
            v-for="(c, i) in form.candidates"
            :key="i"
            style="margin: 14px 0"
          >
            <el-form label-position="top"
              ><el-row :gutter="12"
                ><el-col :span="6"
                  ><el-form-item label="方案名称"
                    ><el-input v-model="c.name" /></el-form-item></el-col
                ><el-col :span="5"
                  ><el-form-item label="寻源方式"
                    ><el-select v-model="c.source"
                      ><el-option
                        v-for="(label, key) in sources"
                        :key="key"
                        :label="label"
                        :value="key" /></el-select></el-form-item></el-col
                ><el-col :span="5"
                  ><el-form-item label="供应模式"
                    ><el-select v-model="c.supply_mode"
                      ><el-option
                        v-for="(label, key) in modes"
                        :key="key"
                        :label="label"
                        :value="key" /></el-select></el-form-item></el-col
                ><el-col :span="5"
                  ><el-form-item label="技术验证"
                    ><el-select v-model="c.validated"
                      ><el-option label="已放行" :value="true" /><el-option
                        label="未放行"
                        :value="false" /></el-select></el-form-item></el-col
                ><el-col :span="3"
                  ><el-button type="text" @click="form.candidates.splice(i, 1)"
                    >删除方案</el-button
                  ></el-col
                ></el-row
              >
              <el-row :gutter="12"
                ><el-col v-for="f in candidateFields" :key="f.key" :span="4"
                  ><el-form-item :label="f.label"
                    ><el-input
                      type="number"
                      :value="c[f.key]"
                      placeholder="待补充"
                      @input="
                        $set(c, f.key, $event === '' ? null : Number($event))
                      " /></el-form-item></el-col
                ><el-col :span="4"
                  ><el-form-item label="承诺到货日期"
                    ><el-date-picker
                      v-model="c.arrival"
                      value-format="yyyy-MM-dd"
                      style="width: 100%" /></el-form-item></el-col
              ></el-row>
              <template v-if="context.aviation">
                <el-divider content-position="left"
                  >航空件适航与交易条件</el-divider
                >
                <el-row :gutter="12">
                  <el-col :span="16"
                    ><el-form-item label="供应渠道与航空能力"
                      ><el-select
                        v-model="c.supplier_id"
                        filterable
                        placeholder="选择已维护航空能力的供应商"
                        style="width: 100%"
                        ><el-option
                          v-for="(
                            supplier, supplierIndex
                          ) in context.supplier_capabilities || []"
                          :key="supplier.supplier_id + '-' + supplierIndex"
                          :label="`${supplier.supplier_code} · ${
                            supplier.supplier_name
                          } · ${supplier.capability_name} · ${
                            supplier.aog_247 ? 'AOG 24/7/' : ''
                          }${supplier.response_hours}h${
                            supplier.relationship_status === 'qualified'
                              ? ''
                              : '（未核实）'
                          }`"
                          :value="
                            supplier.supplier_id
                          " /></el-select></el-form-item
                  ></el-col>
                  <el-col :span="8"
                    ><el-alert
                      title="能力范围与准入状态由后台自动核验，不能在候选方案中手工修改。"
                      type="info"
                      :closable="false" /></el-col
                ></el-row>
                <el-row :gutter="12">
                  <el-col :span="4"
                    ><el-form-item label="交易方式"
                      ><el-select v-model="c.offer_type"
                        ><el-option label="采购" value="purchase" /><el-option
                          label="交换"
                          value="exchange" /><el-option
                          label="借件"
                          value="loan" /><el-option
                          label="送修"
                          value="repair" /></el-select></el-form-item
                  ></el-col>
                  <el-col :span="4"
                    ><el-form-item label="件况"
                      ><el-select v-model="c.condition"
                        ><el-option
                          v-for="v in ['NEW', 'OH', 'SV', 'AR', 'USM']"
                          :key="v"
                          :label="v"
                          :value="v" /></el-select></el-form-item
                  ></el-col>
                  <el-col :span="4"
                    ><el-form-item label="证书"
                      ><el-select v-model="c.certificate_status"
                        ><el-option label="已核验" value="verified" /><el-option
                          label="缺失/未核验"
                          value="missing" /></el-select></el-form-item
                  ></el-col>
                  <el-col :span="4"
                    ><el-form-item label="追溯链"
                      ><el-select v-model="c.trace_status"
                        ><el-option label="完整" value="complete" /><el-option
                          label="不完整"
                          value="incomplete" /></el-select></el-form-item
                  ></el-col>
                  <el-col :span="4"
                    ><el-form-item label="适用性"
                      ><el-select v-model="c.applicability_status"
                        ><el-option label="已验证" value="verified" /><el-option
                          label="未验证"
                          value="not_verified" /></el-select></el-form-item
                  ></el-col>
                  <el-col :span="4"
                    ><el-form-item label="剩余寿命%"
                      ><el-input-number
                        v-model="c.remaining_life_percent"
                        :min="0"
                        :max="100"
                        controls-position="right" /></el-form-item
                  ></el-col>
                </el-row>
                <el-row :gutter="12">
                  <el-col :span="6"
                    ><el-form-item label="送修成本"
                      ><el-input-number
                        v-model="c.repair_cost"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="6"
                    ><el-form-item label="Core占用"
                      ><el-input-number
                        v-model="c.core_charge"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="6"
                    ><el-form-item label="旧件返还抵扣"
                      ><el-input-number
                        v-model="c.core_credit"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="6"
                    ><el-form-item label="逾期返还风险"
                      ><el-input-number
                        v-model="c.return_penalty"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                </el-row>
                <el-divider content-position="left"
                  >库存可获得性与订货约束</el-divider
                >
                <el-row :gutter="12">
                  <el-col :span="6"
                    ><el-form-item label="供应商可获得数量"
                      ><el-input-number
                        v-model="c.available_quantity"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="6"
                    ><el-form-item label="最小订货量MOQ"
                      ><el-input-number
                        v-model="c.minimum_order_quantity"
                        :min="1"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="6"
                    ><el-form-item label="包装数量"
                      ><el-input-number
                        v-model="c.package_quantity"
                        :min="1"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col v-if="context.aviation.shelf_life_days" :span="6"
                    ><el-form-item label="收货时剩余货架寿命(天)"
                      ><el-input-number
                        v-model="c.shelf_life_remaining_days"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                </el-row>
                <el-row v-if="c.offer_type === 'repair'" :gutter="12">
                  <el-col :span="8"
                    ><el-form-item label="维修周转TAT(天)"
                      ><el-input-number
                        v-model="c.repair_tat_days"
                        :min="0"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="8"
                    ><el-form-item label="历史修复成功率%"
                      ><el-input-number
                        v-model="c.repair_success_rate"
                        :min="0"
                        :max="100"
                        controls-position="right" /></el-form-item
                  ></el-col>
                  <el-col :span="8"
                    ><el-form-item label="BER报废概率%"
                      ><el-input-number
                        v-model="c.ber_probability"
                        :min="0"
                        :max="100"
                        controls-position="right" /></el-form-item
                  ></el-col>
                </el-row>
              </template>
              <el-form-item
                v-if="['vmi', 'consignment'].includes(c.supply_mode)"
                label="供货协议评审"
                ><el-checkbox v-model="c.agreement_reviewed"
                  >所有权、补货责任、结算触发点已评审（在下方填写凭证）</el-checkbox
                ></el-form-item
              ><el-form-item label="报价/协议/技术放行/履约数据来源"
                ><el-input v-model="c.evidence" type="textarea" /></el-form-item
            ></el-form>
          </el-card>
        </el-tab-pane>
        <el-tab-pane label="3. 图表与计算过程" name="analysis">
          <template v-if="result"
            ><el-alert
              :title="result.status"
              :type="result.recommendation ? 'success' : 'warning'"
              :closable="false"
            />
            <el-table :data="result.missing" empty-text="必要输入已完整"
              ><el-table-column prop="label" label="缺失信息" /><el-table-column
                prop="action"
                label="补录方法"
              /><el-table-column label="操作"
                ><template
                  ><el-button type="text" @click="tab = 'input'"
                    >前往补录</el-button
                  ></template
                ></el-table-column
              ></el-table
            >
            <div class="chart-grid" style="margin-top: 20px">
              <div class="chart-card">
                <ExplainableChart
                  :option="quadrant"
                  title="综合成本—供应风险四象限"
                  interpretation="右侧成本更高，上方历史未准时率更高；灰色点存在硬约束或资料问题，不能仅凭所在象限执行。点击方案点查看矛盾。"
                  principle="横轴为本次综合成本，纵轴为100−历史及时率；分界线为输入预算及风险阈值。预算约束实际检查现金支出，延期损失另列。"
                  @select="selectCandidate"
                />
              </div>
              <div class="chart-card">
                <ExplainableChart
                  :option="costChart"
                  title="寻源价格与TOC构成"
                  interpretation="比较相同净采购量下的货值、运输、持有、验证和延期损失，缺数据的方案不绘制完整总额。"
                  principle="下单量先按MOQ和包装量向上取整；延期损失=超期天数×每日停机损失；送修/交换另计BER概率期望损失，均不代表已发生费用。"
                />
              </div>
              <div class="chart-card">
                <ExplainableChart
                  :option="timeChart"
                  title="紧急采购交期冲突"
                  interpretation="正值表示超过必要到货日的天数；零表示承诺日期未超期。"
                  principle="延迟=max(0,到货日期−必要日期)，超期方案不进入可执行推荐。"
                />
              </div>
              <div class="chart-card">
                <ExplainableChart
                  :option="flowChart"
                  title="独立策略检查进度"
                  interpretation="1表示已具备该检查的基本条件，0表示未具备；各策略的详细限制见下面计算表。"
                  principle="流程状态由输入完整性及逐项规则生成，不是模型置信度，也不代表审批完成。"
                />
              </div>
              <div class="chart-card">
                <ExplainableChart
                  :option="modeChart"
                  title="差异化供应模式比较"
                  interpretation="按候选供应模式展示现金支出；VMI和寄售需核验所有权、补货责任及结算触发点。"
                  principle="现金支出=货值+运输加急+持有+验证改造；协议缺失作为独立冲突。"
                />
              </div>
              <div class="chart-card">
                <ExplainableChart
                  :option="longtailChart"
                  title="领用频次—设备关键性"
                  interpretation="本物料低频但关键时，不可仅因低频取消储备。频次未知时不显示点。"
                  principle="低频暂用≤2次/年业务规则；关键性为人工确认类别，纵轴0/1仅作类别编码。"
                />
              </div>
            </div>
            <el-table :data="result.process"
              ><el-table-column prop="name" label="分析步骤" /><el-table-column
                prop="detail"
                label="计算与判断依据"
              /><el-table-column label="结果" width="90"
                ><template slot-scope="s"
                  ><el-tag :type="s.row.passed ? 'success' : 'danger'">{{
                    s.row.passed ? "通过" : "未通过"
                  }}</el-tag></template
                ></el-table-column
              ></el-table
            >
            <p v-for="(v, k) in result.rules" :key="k">{{ v }}</p> </template
          ><el-empty v-else description="补充输入后点击重新分析" />
        </el-tab-pane>
        <el-tab-pane label="4. 矛盾与结论" name="conclusion"
          ><template v-if="result"
            ><el-alert
              :title="dirty ? '输入已变化，以下为上次分析结果' : result.status"
              type="info"
              :closable="false"
            />
            <h3 style="margin-top: 18px">{{ result.conclusion }}</h3>
            <p v-if="context.aviation">
              适航硬门槛先于成本排序；证书、追溯、适用性或剩余寿命任一项未通过，即使报价最低也不进入推荐。
            </p>
            <p>
              净采购数量：{{
                result.net_quantity === null ? "待补充" : result.net_quantity
              }}；此处为需求缺口计算，与ABC/VED/FSN采购优先权重分别使用。
            </p>
            <el-button v-if="selected" @click="selected = ''"
              >取消方案筛选</el-button
            ><el-table :data="conflicts" empty-text="未发现已建模约束冲突"
              ><el-table-column prop="candidate" label="方案" /><el-table-column
                prop="type"
                label="矛盾类型" /><el-table-column
                prop="detail"
                label="证据与差额"
                min-width="200" /><el-table-column
                prop="solution"
                label="修正办法"
                min-width="260" /><el-table-column
                prop="owner"
                label="负责人" /><el-table-column
                prop="status"
                label="状态" /></el-table
            ><el-table :data="result.candidates" style="margin-top: 20px"
              ><el-table-column prop="name" label="候选" /><el-table-column
                v-if="context.aviation"
                prop="supplier_name"
                label="供应渠道"
                min-width="150"
              /><el-table-column
                v-if="context.aviation"
                prop="offer_type"
                label="交易方式"
              /><el-table-column
                v-if="context.aviation"
                prop="condition"
                label="件况"
              /><el-table-column
                prop="order_quantity"
                label="下单量"
              /><el-table-column
                prop="available_quantity"
                label="可获得量"
              /><el-table-column prop="cash" label="现金支出" /><el-table-column
                prop="cost"
                label="综合成本"
              /><el-table-column
                prop="premium"
                label="单价溢价%"
              /><el-table-column
                prop="delay_days"
                label="超期天数"
              /><el-table-column label="结果"
                ><template slot-scope="s"
                  >{{ s.row.eligible ? "通过约束" : "待处理" }}
                  {{ s.row.issues.join("、") }}</template
                ></el-table-column
              ></el-table
            ></template
          ></el-tab-pane
        >
        <el-tab-pane label="5. 历史快照" name="history"
          ><el-table :data="history"
            ><el-table-column prop="created_at" label="时间" /><el-table-column
              prop="actor"
              label="分析人"
            /><el-table-column
              prop="result.status"
              label="结果"
            /><el-table-column label="操作"
              ><template slot-scope="s"
                ><el-button type="text" @click="restore(s.row)"
                  >查看并复算</el-button
                ></template
              ></el-table-column
            ></el-table
          ><el-pagination
            :current-page.sync="page"
            :total="total"
            :page-size="10"
            layout="prev,pager,next"
            @current-change="loadHistory"
        /></el-tab-pane>
      </el-tabs>
    </div>
  </el-dialog>
</template>
<script>
import { api } from "../api/client";
import ExplainableChart from "./ExplainableChart.vue";
const fresh = () => ({
  quantity: null,
  required_date: null,
  budget: null,
  baseline_price: null,
  premium_limit: null,
  risk_limit: null,
  downtime_per_day: null,
  annual_issues: null,
  critical: null,
  reserve: null,
  available: null,
  inventory_confirmed: false,
  owner: "",
  evidence: "",
  simulated: false,
  demand_type: "planned",
  required_within_hours: null,
  candidates: [],
});
const bars = (title, names, values) => ({
  title: { text: title, textStyle: { fontSize: 14 } },
  tooltip: { trigger: "axis" },
  grid: { left: 65, right: 20, bottom: 70 },
  xAxis: { type: "category", data: names, axisLabel: { rotate: 15 } },
  yAxis: { type: "value" },
  series: [{ type: "bar", data: values }],
});
export default {
  components: { ExplainableChart },
  props: { material: String },
  data: () => ({
    form: fresh(),
    context: {},
    result: null,
    snapshot: "",
    busy: false,
    tab: "input",
    selected: "",
    history: [],
    page: 1,
    total: 0,
    sources: {
      oem: "原厂OEM",
      domestic: "国产替代",
      alternative: "等效件",
      remanufactured: "再制造",
      shared_stock: "共享库存",
      platform: "平台采购",
    },
    modes: {
      standard: "标准供货",
      vmi: "VMI",
      consignment: "寄售",
      framework: "框架协议",
    },
    fields: [
      { key: "quantity", label: "需求数量" },
      { key: "reserve", label: "必要储备量" },
      { key: "available", label: "已确认可用库存" },
      { key: "budget", label: "预算CNY" },
      { key: "baseline_price", label: "基准单价CNY" },
      { key: "premium_limit", label: "溢价上限%" },
      { key: "risk_limit", label: "风险阈值%" },
      { key: "downtime_per_day", label: "每日停机损失CNY" },
      { key: "annual_issues", label: "年度领用次数" },
    ],
    candidateFields: [
      { key: "unit_price", label: "单价CNY" },
      { key: "fees", label: "运输加急总费" },
      { key: "holding_cost", label: "持有总成本" },
      { key: "validation_cost", label: "验证改造总费" },
      { key: "reliability", label: "历史及时率%" },
    ],
  }),
  watch: {
    material: {
      immediate: true,
      async handler(v) {
        if (!v) return;
        this.form = fresh();
        this.result = null;
        this.tab = "input";
        this.page = 1;
        try {
          this.context = (
            await api.get(
              "/strategy-decisions/" + encodeURIComponent(v) + "/context"
            )
          ).data;
          await this.loadHistory();
        } catch (e) {
          this.error(e);
        }
      },
    },
  },
  computed: {
    analyzed() {
      return this.snapshot ? JSON.parse(this.snapshot) : this.form;
    },
    dirty() {
      return !!this.result && JSON.stringify(this.form) !== this.snapshot;
    },
    rows() {
      return this.result?.candidates || [];
    },
    conflicts() {
      return (this.result?.conflicts || []).filter(
        (x) =>
          !this.selected ||
          x.candidate === this.selected ||
          x.candidate === "物料整体"
      );
    },
    quadrant() {
      return {
        title: { text: "综合成本 / 历史未准时率", textStyle: { fontSize: 14 } },
        tooltip: {
          formatter: (p) =>
            p.name + "：" + p.value[0] + "元 / " + p.value[1] + "%",
        },
        grid: { left: 65, right: 30, bottom: 50 },
        xAxis: { type: "value", name: "CNY" },
        yAxis: { type: "value", name: "未准时率%", min: 0, max: 100 },
        series: [
          {
            type: "scatter",
            symbolSize: 20,
            data: this.rows
              .filter((r) => r.cost !== null && r.risk !== null)
              .map((r) => ({
                name: r.name,
                value: [r.cost, r.risk],
                itemStyle: { color: r.eligible ? "#12b76a" : "#98a2b3" },
              })),
            markLine: {
              silent: true,
              symbol: "none",
              data: [
                ...(this.analyzed.budget
                  ? [{ xAxis: this.analyzed.budget, name: "预算" }]
                  : []),
                ...(this.analyzed.risk_limit !== null
                  ? [{ yAxis: this.analyzed.risk_limit, name: "风险阈值" }]
                  : []),
              ],
            },
          },
        ],
      };
    },
    costChart() {
      const r = this.rows.filter((r) => r.cost !== null),
        o = bars(
          "寻源方案成本构成",
          r.map((x) => x.name),
          []
        );
      o.legend = { top: 28, type: "scroll" };
      o.grid.top = 75;
      o.series = [
        "采购货值",
        "运输及加急",
        "持有成本",
        "验证改造",
        "维修成本",
        "Core占用",
        "旧件归还风险",
        "BER预期损失",
        "延期损失",
      ].map((k) => ({
        name: k,
        type: "bar",
        stack: "cost",
        data: r.map((x) => x.parts[k]),
      }));
      return o;
    },
    timeChart() {
      return bars(
        "超过必要日期的天数",
        this.rows.map((r) => r.name),
        this.rows.map((r) => r.delay_days)
      );
    },
    flowChart() {
      return bars(
        "策略检查过程",
        this.result.process.map((r) => r.name),
        this.result.process.map((r) => (r.passed ? 1 : 0))
      );
    },
    modeChart() {
      return bars(
        "供货模式与现金支出",
        this.rows.map((r) => r.name + " / " + this.modes[r.supply_mode]),
        this.rows.map((r) => r.cash)
      );
    },
    longtailChart() {
      return {
        title: { text: "领用频次 × 关键性", textStyle: { fontSize: 14 } },
        tooltip: {},
        xAxis: {
          type: "value",
          name: "年度领用次数",
          min: 0,
          max: Math.max(5, this.analyzed.annual_issues || 0),
        },
        yAxis: { type: "value", name: "关键=1 / 一般=0", min: -0.5, max: 1.5 },
        series: [
          {
            type: "scatter",
            symbolSize: 24,
            data:
              this.analyzed.annual_issues !== null &&
              this.analyzed.critical !== null
                ? [
                    [
                      this.analyzed.annual_issues,
                      this.analyzed.critical ? 1 : 0,
                    ],
                  ]
                : [],
            markLine: {
              silent: true,
              symbol: "none",
              data: [{ xAxis: 2 }, { yAxis: 0.5 }],
            },
          },
        ],
      };
    },
  },
  methods: {
    error(e) {
      const d = e.response?.data?.detail;
      this.$message.error(
        Array.isArray(d)
          ? d.map((x) => x.loc.slice(1).join(".") + ": " + x.msg).join("；")
          : d || e.message
      );
    },
    add() {
      this.form.candidates.push({
        name: "",
        source: "oem",
        supply_mode: "standard",
        unit_price: null,
        fees: null,
        holding_cost: null,
        validation_cost: null,
        arrival: null,
        validated: null,
        reliability: null,
        supplier_id: "",
        supplier_name: "",
        capability_status: this.context.aviation ? "unmatched" : "not_required",
        offer_type: "purchase",
        condition: "NEW",
        certificate_status: this.context.aviation ? "missing" : "not_required",
        trace_status: this.context.aviation ? "incomplete" : "not_required",
        applicability_status: this.context.aviation
          ? "not_verified"
          : "not_applicable",
        remaining_life_percent: this.context.aviation ? 0 : null,
        repair_cost: 0,
        core_charge: 0,
        core_credit: 0,
        return_penalty: 0,
        available_quantity: null,
        minimum_order_quantity: 1,
        package_quantity: 1,
        repair_tat_days: null,
        repair_success_rate: null,
        ber_probability: null,
        shelf_life_remaining_days: null,
        evidence: "",
      });
    },
    async example() {
      try {
        this.form = (
          await api.get(
            "/strategy-decisions/" +
              encodeURIComponent(this.material) +
              "/example"
          )
        ).data;
        if (this.context.aviation) {
          this.form.candidates = this.form.candidates.map(
            (candidate, index) => ({
              ...candidate,
              offer_type: index === 1 ? "exchange" : "purchase",
              condition: index === 2 ? "USM" : "NEW",
              certificate_status: index === 2 ? "missing" : "verified",
              trace_status: index === 2 ? "incomplete" : "complete",
              applicability_status: index === 2 ? "not_verified" : "verified",
              remaining_life_percent: index === 2 ? 25 : 100,
              repair_cost: 0,
              core_charge: index === 1 ? 8000 : 0,
              core_credit: index === 1 ? 6500 : 0,
              return_penalty: index === 1 ? 1200 : 0,
              available_quantity: candidate.available_quantity ?? 20,
              minimum_order_quantity: candidate.minimum_order_quantity || 1,
              package_quantity: candidate.package_quantity || 1,
              repair_tat_days: null,
              repair_success_rate: null,
              ber_probability: index === 1 ? 8 : null,
              shelf_life_remaining_days:
                candidate.shelf_life_remaining_days ?? 540,
            })
          );
        }
        await this.calculate(false);
      } catch (e) {
        this.error(e);
      }
    },
    async calculate(save) {
      this.busy = true;
      try {
        const r = (
          await api.post(
            "/strategy-decisions/" +
              encodeURIComponent(this.material) +
              (save ? "" : "/preview"),
            this.form
          )
        ).data;
        this.result = save ? r.result : r;
        this.snapshot = JSON.stringify(this.form);
        this.selected = "";
        this.tab = "analysis";
        if (save) {
          await this.loadHistory();
          this.$message.success("分析快照已保存");
        }
      } catch (e) {
        this.error(e);
      } finally {
        this.busy = false;
      }
    },
    selectCandidate(e) {
      if (e.name) {
        this.selected = e.name;
        this.tab = "conclusion";
      }
    },
    async loadHistory() {
      const r = (
        await api.get(
          "/strategy-decisions/" +
            encodeURIComponent(this.material) +
            "/history",
          { params: { page: this.page, page_size: 10 } }
        )
      ).data;
      this.history = r.items;
      this.total = r.total;
    },
    restore(row) {
      this.form = JSON.parse(JSON.stringify(row.input));
      this.result = row.result;
      this.snapshot = JSON.stringify(this.form);
      this.tab = "analysis";
    },
  },
};
</script>

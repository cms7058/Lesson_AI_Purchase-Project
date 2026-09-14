<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">正式询价流程</p>
        <h1>询价项目</h1>
        <p>
          创建询价范围、邀请合格供应商、自动接收供应商报价并完成定标，过程全程留痕。
        </p>
      </div>
      <el-button type="primary" @click="openCreate">新建询价项目</el-button>
    </div>
    <div class="process-strip">
      <span>1. 创建询价</span><i>→</i><span>2. 邀请供应商</span><i>→</i
      ><span>3. 在线报价自动回标</span><i>→</i><span>4. TOC 比价与定标</span>
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索询价编号或项目名称"
        @keyup.enter.native="search"
        @clear="search"
      /><el-select
        v-model="statusFilter"
        clearable
        placeholder="全部状态"
        @change="search"
        ><el-option label="草稿" value="draft" /><el-option
          label="已发布"
          value="published" /><el-option
          label="已定标"
          value="awarded" /></el-select
      ><el-button icon="el-icon-search" @click="search">查询</el-button
      ><el-button
        @click="
          keyword = '';
          statusFilter = '';
          search();
        "
        >重置</el-button
      >
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      class="data-table"
      empty-text="暂无询价项目"
      ><el-table-column
        prop="rfq_no"
        label="询价编号"
        width="145"
      /><el-table-column
        prop="title"
        label="项目名称"
        min-width="200"
      /><el-table-column
        prop="deadline"
        label="报价截止日"
        width="120"
      /><el-table-column label="询价物料" width="100"
        ><template slot-scope="scope"
          >{{ scope.row.lines.length }} 项</template
        ></el-table-column
      ><el-table-column label="回标状态" width="130"
        ><template slot-scope="scope"
          ><el-button type="text" @click="showDetail(scope.row)"
            ><el-tag
              :type="
                responseCount(scope.row) === scope.row.invitations.length
                  ? 'success'
                  : 'warning'
              "
              >{{ responseCount(scope.row) }}/{{
                scope.row.invitations.length
              }}</el-tag
            ></el-button
          ></template
        ></el-table-column
      ><el-table-column label="状态" width="100"
        ><template slot-scope="scope"
          ><el-tag :type="statusType(scope.row.status)">{{
            statusName(scope.row.status)
          }}</el-tag></template
        ></el-table-column
      ><el-table-column label="操作" width="300" fixed="right"
        ><template slot-scope="scope"
          ><el-button
            v-if="scope.row.status === 'draft'"
            type="text"
            @click="openEdit(scope.row)"
            >编辑</el-button
          ><el-button
            v-if="scope.row.status === 'draft'"
            type="text"
            @click="publish(scope.row)"
            >发布</el-button
          ><el-button
            v-if="scope.row.status === 'published'"
            type="text"
            @click="sendMail(scope.row)"
            >发送/重试邮件</el-button
          ><el-button
            v-if="scope.row.status === 'published' && responseCount(scope.row)"
            type="text"
            @click="openAward(scope.row)"
            >定标</el-button
          ><el-button type="text" @click="showDetail(scope.row)"
            >报价/附件</el-button
          ><el-button
            v-if="scope.row.status === 'draft'"
            type="text"
            class="danger-link"
            @click="remove(scope.row)"
            >删除</el-button
          ></template
        ></el-table-column
      ></el-table
    >
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
      :title="editingId ? '编辑询价项目' : '新建询价项目'"
      :visible.sync="formVisible"
      width="820px"
      :close-on-click-modal="false"
      ><el-form ref="form" :model="form" :rules="rules" label-width="100px"
        ><el-row :gutter="16"
          ><el-col :span="16"
            ><el-form-item label="项目名称" prop="title"
              ><el-input v-model.trim="form.title" /></el-form-item></el-col
          ><el-col :span="8"
            ><el-form-item label="报价截止日"
              ><el-date-picker
                v-model="form.deadline"
                value-format="yyyy-MM-dd"
                type="date"
                style="width: 100%" /></el-form-item></el-col></el-row
        ><el-form-item label="邀请供应商" prop="supplierCodes"
          ><el-select
            v-model="form.supplierCodes"
            multiple
            filterable
            style="width: 100%"
            placeholder="仅显示已准入供应商"
            ><el-option
              v-for="supplier in qualifiedSuppliers"
              :key="supplier.id"
              :label="`${supplier.code} · ${supplier.name}`"
              :value="supplier.code" /></el-select
        ></el-form-item>
        <div class="dialog-section-title">
          <strong>询价物料</strong
          ><el-button
            size="mini"
            icon="el-icon-plus"
            @click="form.lines.push(emptyLine())"
            >添加物料</el-button
          >
        </div>
        <el-table :data="form.lines" border size="mini"
          ><el-table-column label="物料编码" min-width="180"
            ><template slot-scope="scope"
              ><el-select
                v-model="scope.row.material_code"
                filterable
                allow-create
                @change="selectMaterial(scope.$index, $event)"
                ><el-option
                  v-for="material in materials"
                  :key="material.id"
                  :label="`${material.code} · ${material.name}`"
                  :value="
                    material.code
                  " /></el-select></template></el-table-column
          ><el-table-column label="物料名称" min-width="160"
            ><template slot-scope="scope"
              ><el-input
                v-model="scope.row.material_name" /></template></el-table-column
          ><el-table-column label="规格" min-width="140"
            ><template slot-scope="scope"
              ><el-input
                v-model="scope.row.specification" /></template></el-table-column
          ><el-table-column label="数量" width="110"
            ><template slot-scope="scope"
              ><el-input-number
                v-model="scope.row.quantity"
                :min="0.01"
                :precision="2"
                controls-position="right" /></template></el-table-column
          ><el-table-column label="单位" width="75"
            ><template slot-scope="scope"
              ><el-input v-model="scope.row.unit" /></template></el-table-column
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
          ></el-table
        ></el-form
      ><span slot="footer"
        ><el-button @click="formVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存询价</el-button
        ></span
      ></el-dialog
    >

    <el-dialog
      title="询价项目定标分析"
      custom-class="analysis-dialog"
      :visible.sync="awardVisible"
      width="1160px"
      :close-on-click-modal="false"
      ><RfqAwardAnalysis
        v-if="awardVisible && selected"
        :rfq-id="selected.id"
        @close="awardVisible = false"
        @awarded="
          awardVisible = false;
          load();
        "
    /></el-dialog>
    <el-dialog
      title="询价项目回标与附件"
      :visible.sync="detailVisible"
      width="1160px"
      ><template v-if="selected"
        ><p>
          {{ selected.rfq_no }} · {{ selected.title }} · 回标
          {{ responseCount(selected) }}/{{ selected.invitations.length }}
        </p>
        <el-table :data="bidRows" border
          ><el-table-column
            prop="supplier_name"
            label="供应商"
            min-width="160"
          /><el-table-column label="回标状态" width="95"
            ><template slot-scope="s"
              ><el-tag :type="s.row.quotation ? 'success' : 'info'">{{
                s.row.quotation ? "已回标" : "待回标"
              }}</el-tag></template
            ></el-table-column
          ><el-table-column label="报价编号" min-width="150"
            ><template slot-scope="s">{{
              s.row.quotation ? s.row.quotation.quotation_no : "—"
            }}</template></el-table-column
          ><el-table-column label="录入方式" width="95"
            ><template slot-scope="s">{{
              s.row.quotation
                ? s.row.quotation.source_type === "ocr"
                  ? "附件识别"
                  : "手工填报"
                : "—"
            }}</template></el-table-column
          ><el-table-column label="交期/天" width="85"
            ><template slot-scope="s">{{
              s.row.quotation ? s.row.quotation.delivery_days : "—"
            }}</template></el-table-column
          ><el-table-column label="含税及物流合计" width="140"
            ><template slot-scope="s">{{
              s.row.quotation ? total(s.row.quotation) : "—"
            }}</template></el-table-column
          ><el-table-column label="复核状态" width="105"
            ><template slot-scope="s"
              ><el-tag
                v-if="s.row.quotation"
                :type="reviewType(s.row.review.status)"
                >{{ reviewName(s.row.review.status) }}</el-tag
              ><span v-else>—</span></template
            ></el-table-column
          ><el-table-column label="邮件状态" width="110"
            ><template slot-scope="s"
              ><el-tooltip :content="s.row.mail_error || '询价邀请邮件'"
                ><span>{{ mailName(s.row.mail_status) }}</span></el-tooltip
              ></template
            ></el-table-column
          ><el-table-column label="复核" width="70"
            ><template slot-scope="s"
              ><el-button
                v-if="s.row.quotation"
                type="text"
                @click="openReview(s.row)"
                >复核</el-button
              ></template
            ></el-table-column
          ><el-table-column type="expand"
            ><template slot-scope="s"
              ><el-table v-if="s.row.quotation" :data="s.row.quotation.lines"
                ><el-table-column
                  prop="material_code"
                  label="物料编码" /><el-table-column
                  prop="material_name"
                  label="物料名称" /><el-table-column
                  prop="quantity"
                  label="数量" /><el-table-column
                  prop="unit_price"
                  label="未税单价" /><el-table-column
                  prop="tax_rate"
                  label="税率" /><el-table-column
                  prop="logistics_cost"
                  label="物流费"
              /></el-table>
              <el-alert
                v-if="s.row.quotation && s.row.anomalies.length"
                title="规则校验发现异常"
                type="warning"
                :closable="false"
                style="margin-top: 12px"
              >
                <div v-for="(a, index) in s.row.anomalies" :key="index">
                  {{ a.material_code }}：{{ a.message }}
                </div>
              </el-alert>
              <p v-if="s.row.cost_summary">
                未税货值 {{ money(s.row.cost_summary.goods_before_tax) }}；税额
                {{ money(s.row.cost_summary.tax) }}；物流费
                {{ money(s.row.cost_summary.logistics) }}；含税到厂总成本
                <strong>{{ money(s.row.cost_summary.landed_total) }}</strong>
              </p>
              <p v-else>该供应商尚未提交报价</p>
              <div v-if="s.row.quotation">
                <strong>供应商报价附件：</strong
                ><el-button
                  v-for="a in s.row.quotation_attachments"
                  :key="a.id"
                  type="text"
                  @click="download(a, 'quotation-attachments')"
                  >{{ a.name }}</el-button
                ><span v-if="!s.row.quotation_attachments.length">无附件</span>
              </div>
              <div v-if="s.row.revision_history && s.row.revision_history.length" style="margin-top: 14px">
                <strong>报价修订历史（旧版本仅追溯，不参与定标）：</strong>
                <el-table :data="s.row.revision_history" size="mini" border style="margin-top: 8px">
                  <el-table-column label="版本" width="80"><template slot-scope="v">V{{ v.row.version }} <el-tag v-if="v.row.current" size="mini" type="success">当前</el-tag></template></el-table-column>
                  <el-table-column prop="quotation_no" label="报价编号" min-width="150"/>
                  <el-table-column label="录入方式" width="90"><template slot-scope="v">{{ v.row.source_type === 'ocr' ? '附件识别' : '手工填报' }}</template></el-table-column>
                  <el-table-column label="含税及物流合计" width="150"><template slot-scope="v">{{ money(v.row.total) }}</template></el-table-column>
                  <el-table-column label="复核状态" width="95"><template slot-scope="v"><el-tag size="mini" :type="reviewType(v.row.review.status)">{{ reviewName(v.row.review.status) }}</el-tag></template></el-table-column>
                  <el-table-column prop="review.note" label="复核说明" min-width="180"/>
                </el-table>
              </div></template
            ></el-table-column
          ></el-table
        >
        <h3>询价附件</h3>
        <p>
          支持
          PDF、Word、Excel、图片、CSV、TXT、ZIP，单文件最大10MB；发布后附件锁定。
        </p>
        <el-upload
          v-if="selected.status === 'draft'"
          action="#"
          :http-request="upload"
          :show-file-list="false"
          ><el-button :loading="uploading" type="primary" size="small"
            >上传询价附件</el-button
          ></el-upload
        >
        <div v-for="a in attachments" :key="a.id">
          <el-button type="text" @click="download(a)">{{ a.name }}</el-button
          ><span>（{{ Math.ceil(a.size / 1024) }} KB）</span
          ><el-button
            v-if="selected.status === 'draft'"
            type="text"
            class="danger-link"
            @click="removeAttachment(a)"
            >删除</el-button
          >
        </div>
        <p v-if="!attachments.length">暂无附件</p></template
      ><span slot="footer"
        ><el-button @click="showDetail(selected)">刷新回标状态</el-button
        ><el-button @click="detailVisible = false">关闭</el-button></span
      ></el-dialog
    >
    <el-dialog
      title="供应商报价人工复核"
      :visible.sync="reviewVisible"
      width="620px"
      :close-on-click-modal="false"
    >
      <template v-if="reviewRow">
        <p>
          {{ reviewRow.supplier_name }} ·
          {{ reviewRow.quotation.quotation_no }} ·
          {{
            reviewRow.quotation.source_type === "ocr" ? "附件识别" : "手工填报"
          }}
        </p>
        <el-alert
          v-if="reviewRow.anomalies.length"
          :title="`存在 ${reviewRow.anomalies.length} 项规则异常，请对照原始附件核实`"
          type="warning"
          :closable="false"
        />
        <el-form label-width="100px" style="margin-top: 18px">
          <el-form-item label="复核结论">
            <el-radio-group v-model="reviewForm.status">
              <el-radio label="verified">核验通过</el-radio>
              <el-radio label="rejected">退回核实</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="复核说明">
            <el-input
              v-model.trim="reviewForm.note"
              type="textarea"
              :rows="4"
              maxlength="1000"
              show-word-limit
              placeholder="记录与原始附件的核对结果；退回时必须填写原因"
            />
          </el-form-item>
        </el-form>
      </template>
      <span slot="footer">
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="primary" :loading="reviewSaving" @click="saveReview"
          >保存复核</el-button
        >
      </span>
    </el-dialog>
  </div>
</template>
<script>
import RfqAwardAnalysis from "../components/RfqAwardAnalysis.vue";
import {
  api,
  awardRfq,
  createRfq,
  deleteRfq,
  fetchMasterData,
  fetchRfqs,
  publishRfq,
  updateRfq,
} from "../api/client";
const emptyLine = () => ({
  material_code: "",
  material_name: "",
  specification: "",
  quantity: 1,
  unit: "件",
});
const emptyForm = () => ({
  title: "",
  deadline: null,
  currency: "CNY",
  supplierCodes: [],
  lines: [emptyLine()],
});
export default {
  components: { RfqAwardAnalysis },
  data: () => ({
    items: [],
    suppliers: [],
    materials: [],
    keyword: "",
    statusFilter: "",
    loading: false,
    saving: false,
    uploading: false,
    formVisible: false,
    awardVisible: false,
    detailVisible: false,
    reviewVisible: false,
    reviewSaving: false,
    reviewRow: null,
    reviewForm: { status: "verified", note: "" },
    editingId: "",
    selected: null,
    selectedQuotationId: "",
    form: emptyForm(),
    bidRows: [],
    attachments: [],
    pagination: { page: 1, page_size: 10, total: 0 },
    rules: {
      title: [{ required: true, message: "请输入项目名称", trigger: "blur" }],
      supplierCodes: [
        {
          type: "array",
          required: true,
          min: 1,
          message: "至少邀请一家供应商",
          trigger: "change",
        },
      ],
    },
  }),
  computed: {
    qualifiedSuppliers() {
      return this.suppliers.filter((s) => s.status === "qualified");
    },
    respondedInvitations() {
      return this.selected
        ? this.selected.invitations.filter((i) => i.quotation_id)
        : [];
    },
  },
  async created() {
    await Promise.all([this.load(), this.loadOptions()]);
  },
  mounted() {
    this.refreshTimer = setInterval(async () => {
      if (this.loading || this.formVisible || this.awardVisible) return;
      await this.load();
      if (this.detailVisible && this.selected) {
        this.selected =
          this.items.find((i) => i.id === this.selected.id) || this.selected;
        try {
          const r = (await api.get("/rfqs/" + this.selected.id + "/bids")).data;
          this.bidRows = r.items;
          this.attachments = r.attachments;
        } catch (e) {
          /* next periodic refresh retries */
        }
      }
    }, 15000);
  },
  beforeDestroy() {
    clearInterval(this.refreshTimer);
  },
  methods: {
    emptyLine,
    error(e) {
      const d = e.response?.data?.detail;
      this.$message.error(typeof d === "string" ? d : "操作失败，请检查数据");
    },
    statusName(v) {
      return (
        {
          draft: "草稿",
          published: "已发布",
          awarded: "已定标",
          closed: "已关闭",
          cancelled: "已取消",
        }[v] || v
      );
    },
    statusType(v) {
      return (
        { draft: "info", published: "warning", awarded: "success" }[v] || "info"
      );
    },
    mailName(v) {
      return (
        {
          not_queued: "未入队",
          pending: "待发送",
          sending: "发送中",
          sent: "已发送",
          failed: "失败可重试",
        }[v] || v
      );
    },
    reviewName(v) {
      return (
        { pending: "待复核", verified: "已核验", rejected: "已退回" }[v] || v
      );
    },
    reviewType(v) {
      return (
        { pending: "warning", verified: "success", rejected: "danger" }[v] ||
        "info"
      );
    },
    money(v) {
      return `${this.selected?.currency || "CNY"} ${Number(v || 0).toFixed(2)}`;
    },
    responseCount(item) {
      return item.invitations.filter((i) => i.quotation_id).length;
    },
    total(q) {
      return (
        q.currency +
        " " +
        q.lines.reduce((sum, l) => sum + Number(l.tco_amount), 0).toFixed(2)
      );
    },
    async load() {
      this.loading = true;
      try {
        const r = await fetchRfqs({
          ...this.pagination,
          keyword: this.keyword,
          status: this.statusFilter,
        });
        this.items = r.items;
        this.pagination.total = r.total;
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    async loadOptions() {
      for (const kind of ["suppliers", "materials"]) {
        let page = 1,
          total = 1;
        this[kind] = [];
        while (this[kind].length < total) {
          const r = await fetchMasterData(kind, { page, page_size: 100 });
          this[kind].push(...r.items);
          total = r.total;
          if (!r.items.length) break;
          page++;
        }
      }
    },
    search() {
      this.pagination.page = 1;
      this.load();
    },
    changePage(p) {
      this.pagination.page = p;
      this.load();
    },
    changeSize(n) {
      this.pagination.page_size = n;
      this.search();
    },
    openCreate() {
      this.editingId = "";
      this.form = emptyForm();
      this.formVisible = true;
    },
    openEdit(item) {
      this.editingId = item.id;
      this.form = {
        title: item.title,
        deadline: item.deadline,
        currency: item.currency,
        supplierCodes: item.invitations.map(
          (i) =>
            this.suppliers.find(
              (s) => s.id === i.supplier_id || s.code === i.supplier_id
            )?.code || i.supplier_id
        ),
        lines: item.lines.map((l) => ({ ...l, quantity: Number(l.quantity) })),
      };
      this.formVisible = true;
    },
    selectMaterial(index, code) {
      const m = this.materials.find((m) => m.code === code);
      if (m)
        this.$set(this.form.lines, index, {
          material_code: code,
          material_name: m.name,
          specification: m.specification,
          quantity: this.form.lines[index].quantity,
          unit: m.unit,
        });
    },
    payload() {
      return {
        ...this.form,
        invitations: this.form.supplierCodes.map((code) => ({
          supplier_id: code,
          supplier_name:
            this.suppliers.find((s) => s.code === code)?.name || code,
        })),
      };
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        this.saving = true;
        try {
          const r = this.editingId
            ? await updateRfq(this.editingId, this.payload())
            : await createRfq(this.payload());
          this.formVisible = false;
          await this.load();
          this.$message.success("已保存，可在报价/附件中上传文件后发布");
          await this.showDetail(r);
        } catch (e) {
          this.error(e);
        } finally {
          this.saving = false;
        }
      });
    },
    async publish(item) {
      try {
        await this.$confirm(
          "发布后锁定物料及附件；已开启自动发送时将给供应商发送询价邮件。",
          "发布询价"
        );
        await publishRfq(item.id);
        await this.load();
        this.$message.success("已发布，邮件状态可在回标详情查看");
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
    async sendMail(item) {
      try {
        await api.post("/rfqs/" + item.id + "/send-mail");
        this.$message.success("已加入发送任务，已发送成功的供应商不会重复发送");
      } catch (e) {
        this.error(e);
      }
    },
    async showDetail(item) {
      try {
        await this.load();
        this.selected = this.items.find((i) => i.id === item.id) || item;
        const r = (await api.get("/rfqs/" + item.id + "/bids")).data;
        this.bidRows = r.items;
        this.attachments = r.attachments;
        this.detailVisible = true;
      } catch (e) {
        this.error(e);
      }
    },
    openReview(row) {
      this.reviewRow = row;
      this.reviewForm = {
        status: row.review.status === "rejected" ? "rejected" : "verified",
        note: row.review.note || "",
      };
      this.reviewVisible = true;
    },
    async saveReview() {
      if (this.reviewForm.status === "rejected" && !this.reviewForm.note) {
        this.$message.warning("退回报价必须填写原因");
        return;
      }
      this.reviewSaving = true;
      try {
        await api.put(
          `/rfqs/${this.selected.id}/quotations/${this.reviewRow.quotation.id}/review`,
          this.reviewForm
        );
        this.reviewVisible = false;
        await this.showDetail(this.selected);
        this.$message.success("报价复核结果已保存并记录审计日志");
      } catch (e) {
        this.error(e);
      } finally {
        this.reviewSaving = false;
      }
    },
    openAward(item) {
      this.selected = item;
      this.selectedQuotationId = "";
      this.awardVisible = true;
    },
    quoteNumber(id) {
      return id.slice(0, 8);
    },
    async award() {
      this.saving = true;
      try {
        await awardRfq(this.selected.id, this.selectedQuotationId);
        this.awardVisible = false;
        await this.load();
        this.$message.success("定标成功");
      } catch (e) {
        this.error(e);
      } finally {
        this.saving = false;
      }
    },
    async remove(item) {
      try {
        await this.$confirm("确定删除草稿询价？", "删除确认");
        await deleteRfq(item.id);
        await this.load();
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
    async upload(options) {
      this.uploading = true;
      try {
        const form = new FormData();
        form.append("file", options.file);
        await api.post("/rfqs/" + this.selected.id + "/attachments", form);
        await this.showDetail(this.selected);
        this.$message.success("附件已上传");
      } catch (e) {
        this.error(e);
      } finally {
        this.uploading = false;
      }
    },
    async download(a, kind = "attachments") {
      try {
        const r = await api.get(
          "/rfqs/" + this.selected.id + "/" + kind + "/" + a.id,
          { responseType: "blob" }
        );
        const url = URL.createObjectURL(r.data);
        const link = document.createElement("a");
        link.href = url;
        link.download = a.name;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) {
        this.error(e);
      }
    },
    async removeAttachment(a) {
      try {
        await this.$confirm("删除附件 " + a.name + "？", "删除附件");
        await api.delete("/rfqs/" + this.selected.id + "/attachments/" + a.id);
        await this.showDetail(this.selected);
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
  },
};
</script>

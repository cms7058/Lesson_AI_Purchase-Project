<template>
  <main class="supplier-portal">
    <div class="page-heading">
      <div>
        <h1>AI助力供应商门户</h1>
        <p>询价报价 · 订单交付 · 发票上传</p>
      </div>
      <el-button v-if="token" @click="logout">退出登录</el-button>
    </div>
    <el-card v-if="!token" class="login-card"
      ><h2>供应商登录</h2>
      <el-form @submit.native.prevent="login"
        ><el-form-item label="登录名"
          ><el-input
            v-model.trim="credentials.username"
            autocomplete="username" /></el-form-item
        ><el-form-item label="密码"
          ><el-input
            v-model="credentials.password"
            show-password
            autocomplete="current-password"
            @keyup.enter.native="login" /></el-form-item
        ><el-button type="primary" :loading="busy" @click="login"
          >登录</el-button
        ></el-form
      ></el-card
    >
    <template v-else
      ><el-tabs v-model="portalTab"
        ><el-tab-pane label="询价报价" name="quotes" /><el-tab-pane
          label="订单交付"
          name="orders" /><el-tab-pane
          label="发票上传"
          name="invoices" /></el-tabs
      ><SupplierExecution
        v-if="portalTab !== 'quotes'"
        :key="portalTab"
        :token="token"
        :mode="portalTab"
        @expired="logout" />
      <div v-else>
        <ListFilters
          :only-resources="['supplier/rfqs']"
          :provided-schemas="filterSchemas"
          @query="
            pagination.page = 1;
            load();
          "
        /><el-tabs
          v-model="tab"
          @tab-click="
            pagination.page = 1;
            load();
          "
          ><el-tab-pane label="待报价" name="pending" /><el-tab-pane
            label="报价历史"
            name="history" /></el-tabs
        ><el-table :data="items" v-loading="loading"
          ><el-table-column prop="rfq_no" label="询价编号" /><el-table-column
            prop="title"
            label="询价项目"
          /><el-table-column prop="deadline" label="截止日期" /><el-table-column
            label="状态"
            ><template slot-scope="s">{{
              s.row.review_status === "rejected"
                ? "已退回待修正"
                : s.row.responded
                ? "已报价"
                : closed(s.row)
                ? "已截止/关闭"
                : "待报价"
            }}</template></el-table-column
          ><el-table-column label="操作"
            ><template slot-scope="s"
              ><el-button type="text" @click="open(s.row)">{{
                s.row.review_status === "rejected"
                  ? "修改并重报"
                  : s.row.responded
                  ? "查看报价"
                  : "查看 / 报价"
              }}</el-button></template
            ></el-table-column
          ></el-table
        ><Pager
          :page="pagination"
          @change="changePage"
          @size="changeSize"
        /></div
    ></template>
    <el-dialog
      :title="detail.title || '询价详情'"
      :visible.sync="visible"
      width="900px"
      :close-on-click-modal="false"
      ><template v-if="detail.id"
        ><p>
          {{ detail.rfq_no }} · 币种 {{ detail.currency }} · 截止
          {{ detail.deadline || "未设置" }}
        </p>
        <div>
          <strong>询价附件（点击查看/下载）：</strong
          ><el-button
            v-for="a in detail.attachments"
            :key="a.id"
            type="text"
            @click="download(a)"
            >{{ a.name }}</el-button
          ><span v-if="!detail.attachments.length">无附件</span>
        </div>
        <section class="quote-attachments">
          <h3>我的报价附件</h3>
          <p>
            可上传盖章报价单、技术说明等，单个文件最大10MB，最多20个。表格/Word采用结构化识别，扫描PDF/图片采用视觉模型；结果须人工核对后提交。
          </p>
          <el-upload
            v-if="!readonly"
            action="#"
            :http-request="uploadQuote"
            :show-file-list="false"
            :disabled="uploading || busy"
            accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg,.csv,.txt,.zip"
            ><el-button size="small" :loading="uploading" :disabled="busy"
              >上传报价附件</el-button
            ></el-upload
          >
          <div v-for="a in detail.quotation_attachments" :key="a.id">
            <el-button
              type="text"
              @click="download(a, 'quotation-attachments')"
              >{{ a.name }}</el-button
            ><span>（{{ Math.ceil(a.size / 1024) }} KB）</span
            ><el-button
              v-if="!readonly && !a.submitted"
              type="text"
              :loading="extractingId === a.id"
              :disabled="uploading || busy"
              @click="extractQuote(a)"
              >智能识别并填入</el-button
            ><el-button
              v-if="!readonly && !a.submitted"
              type="text"
              :disabled="uploading || busy"
              @click="deleteQuoteFile(a)"
              >删除附件</el-button
            >
          </div>
          <p
            v-if="
              !detail.quotation_attachments ||
              !detail.quotation_attachments.length
            "
          >
            尚无报价附件
          </p>
        </section>
        <el-alert
          v-if="extraction"
          :title="`${
            extraction.extraction_mode === 'vision' ? '视觉模型' : '结构化'
          }识别匹配率 ${Math.round(
            extraction.confidence * 100
          )}%，请核对后提交`"
          :description="
            extraction.warnings.length
              ? extraction.warnings.join('；')
              : '全部询价物料均已匹配'
          "
          :type="extraction.warnings.length ? 'warning' : 'success'"
          show-icon
          :closable="false" /><el-alert
          v-if="detail.review && detail.review.status === 'rejected'"
          :title="`采购方已退回：${detail.review.note}`"
          type="warning"
          show-icon
          :closable="false" /><el-alert
          v-if="detail.quotation && detail.review.status !== 'rejected'"
          title="报价已提交，采购方已自动收到回标。"
          type="success"
          :closable="false" /><el-table :data="lines" border
          ><el-table-column
            prop="material_code"
            label="物料编码" /><el-table-column
            prop="material_name"
            label="名称" /><el-table-column
            prop="quantity"
            label="数量"
            width="85" /><el-table-column
            prop="unit"
            label="单位"
            width="65" /><el-table-column label="未税单价" width="130"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.unit_price"
                :min="0"
                :precision="4"
                :controls="false"
                :disabled="readonly"
                style="width: 100%" /></template></el-table-column
          ><el-table-column label="税率(0—1)" width="110"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.tax_rate"
                :min="0"
                :max="1"
                :step="0.01"
                :controls="false"
                :disabled="readonly"
                style="width: 100%" /></template></el-table-column
          ><el-table-column label="物流费用" width="120"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.logistics_cost"
                :min="0"
                :precision="2"
                :controls="false"
                :disabled="readonly"
                style="width: 100%" /></template></el-table-column></el-table
        ><el-form inline style="margin-top: 20px"
          ><el-form-item label="交期（天）"
            ><el-input-number
              v-model="bid.delivery_days"
              :min="0"
              :max="999"
              :disabled="readonly" /></el-form-item
          ><el-form-item label="有效期（天）"
            ><el-input-number
              v-model="bid.validity_days"
              :min="1"
              :max="365"
              :disabled="readonly" /></el-form-item></el-form></template
      ><span slot="footer"
        ><el-button @click="visible = false">关闭</el-button
        ><el-button
          v-if="!readonly"
          type="primary"
          :loading="busy"
          :disabled="uploading"
          @click="submit"
          >确认提交报价</el-button
        ></span
      ></el-dialog
    >
  </main>
</template>
<script>
import SupplierExecution from "../components/SupplierExecution.vue";
import ListFilters from "../components/ListFilters.vue";
import { listQueryFilters } from "../api/client";
import axios from "axios";
import Pager from "../components/Pager.vue";
const client = axios.create({
  baseURL: process.env.VUE_APP_API_BASE_URL || "/api/v1",
  timeout: 20000,
});
export default {
  components: { Pager, ListFilters, SupplierExecution },
  data: () => ({
    portalTab: "quotes",
    filterSchemas: [
      {
        resource: "supplier/rfqs",
        label: "我的询价",
        fields: [
          { name: "rfq_no", label: "询价编号", type: "text" },
          { name: "title", label: "询价标题", type: "text" },
          { name: "material_code", label: "物料编码", type: "text" },
          { name: "deadline", label: "报价截止日期", type: "date" },
          {
            name: "status",
            label: "状态",
            type: "text",
            options: [
              { value: "published", label: "待定标" },
              { value: "awarded", label: "已定标" },
            ],
          },
        ],
      },
    ],
    token: sessionStorage.getItem("supplier_token") || "",
    credentials: { username: "", password: "" },
    tab: "pending",
    items: [],
    pagination: { page: 1, page_size: 10, total: 0 },
    loading: false,
    busy: false,
    uploading: false,
    extractingId: "",
    extraction: null,
    visible: false,
    detail: {},
    lines: [],
    bid: { delivery_days: 14, validity_days: 30 },
  }),
  computed: {
    readonly() {
      return (
        (!!this.detail.quotation &&
          this.detail.review?.status !== "rejected") ||
        this.closed(this.detail)
      );
    },
  },
  created() {
    if (this.token) this.load();
  },
  methods: {
    headers() {
      return { Authorization: `Bearer ${this.token}` };
    },
    closed(r) {
      const today = new Date();
      const date = `${today.getFullYear()}-${String(
        today.getMonth() + 1
      ).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
      return r.status !== "published" || (r.deadline && r.deadline < date);
    },
    error(e) {
      if (e.response?.status === 401) {
        this.token = "";
        sessionStorage.removeItem("supplier_token");
      }
      const d = e.response?.data?.detail;
      this.$message.error(
        typeof d === "string" ? d : "操作失败，请检查填写内容"
      );
    },
    async login() {
      this.busy = true;
      try {
        const r = (await client.post("/supplier/login", this.credentials)).data;
        this.token = r.token;
        sessionStorage.setItem("supplier_token", r.token);
        this.credentials.password = "";
        await this.load();
      } catch (e) {
        this.error(e);
      } finally {
        this.busy = false;
      }
    },
    async logout() {
      const headers = this.headers();
      this.token = "";
      sessionStorage.removeItem("supplier_token");
      this.items = [];
      try {
        await client.post("/supplier/logout", {}, { headers });
      } catch (e) {
        this.$message.warning("本地已退出，服务端会话将在到期后失效");
      }
    },
    async load() {
      this.loading = true;
      try {
        const r = (
          await client.get("/supplier/rfqs", {
            params: {
              ...this.pagination,
              tab: this.tab,
              filters: JSON.stringify(listQueryFilters["supplier/rfqs"] || []),
            },
            headers: this.headers(),
          })
        ).data;
        this.items = r.items;
        this.pagination.total = r.total;
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    changePage(p) {
      this.pagination.page = p;
      this.load();
    },
    changeSize(n) {
      this.pagination.page = 1;
      this.pagination.page_size = n;
      this.load();
    },
    async open(row) {
      try {
        this.detail = (
          await client.get(`/supplier/rfqs/${row.id}`, {
            headers: this.headers(),
          })
        ).data;
        this.lines = (this.detail.quotation?.lines || this.detail.lines).map(
          (l) => ({
            ...l,
            unit_price: Number(l.unit_price || 0),
            tax_rate: Number(l.tax_rate ?? 0.13),
            logistics_cost: Number(l.logistics_cost || 0),
          })
        );
        this.bid = {
          delivery_days: this.detail.quotation?.delivery_days || 14,
          validity_days: this.detail.quotation?.validity_days || 30,
        };
        this.extraction = null;
        this.visible = true;
      } catch (e) {
        this.error(e);
      }
    },
    async uploadQuote(options) {
      this.uploading = true;
      try {
        const form = new FormData();
        form.append("file", options.file);
        const r = await client.post(
          `/supplier/rfqs/${this.detail.id}/quotation-attachments`,
          form,
          { headers: this.headers() }
        );
        this.detail.quotation_attachments.push(r.data);
        this.$message.success("附件已上传，可点击智能识别并填入");
      } catch (e) {
        this.error(e);
      } finally {
        this.uploading = false;
      }
    },
    async extractQuote(a) {
      this.extractingId = a.id;
      try {
        const result = (
          await client.post(
            `/supplier/rfqs/${this.detail.id}/quotation-attachments/${a.id}/extract`,
            {},
            { headers: this.headers() }
          )
        ).data;
        this.lines = this.lines.map((line, index) => ({
          ...line,
          ...result.lines[index],
        }));
        this.bid = {
          delivery_days: result.delivery_days,
          validity_days: result.validity_days,
        };
        this.extraction = result;
        this.$message.success("报价字段已识别并填入，请人工核对");
      } catch (e) {
        this.error(e);
      } finally {
        this.extractingId = "";
      }
    },
    async deleteQuoteFile(a) {
      try {
        await this.$confirm("删除此报价附件？", "删除附件");
        await client.delete(
          `/supplier/rfqs/${this.detail.id}/quotation-attachments/${a.id}`,
          { headers: this.headers() }
        );
        this.detail.quotation_attachments =
          this.detail.quotation_attachments.filter((f) => f.id !== a.id);
        if (this.extraction?.filename === a.name) this.extraction = null;
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
    async download(a, kind = "attachments") {
      try {
        const r = await client.get(
          `/supplier/rfqs/${this.detail.id}/${kind}/${a.id}`,
          { headers: this.headers(), responseType: "blob" }
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
    async submit() {
      try {
        await this.$confirm(
          "提交后不可自行修改，请确认所有报价金额、交期及附件。",
          "提交报价"
        );
        this.busy = true;
        await client.post(
          `/supplier/rfqs/${this.detail.id}/quote`,
          {
            ...this.bid,
            source_type: this.extraction ? "ocr" : "manual",
            lines: this.lines.map((l) => ({
              unit_price: l.unit_price,
              tax_rate: l.tax_rate,
              logistics_cost: l.logistics_cost,
            })),
          },
          { headers: this.headers() }
        );
        this.$message.success("报价已提交");
        this.visible = false;
        await this.load();
      } catch (e) {
        if (e !== "cancel") this.error(e);
      } finally {
        this.busy = false;
      }
    },
  },
};
</script>

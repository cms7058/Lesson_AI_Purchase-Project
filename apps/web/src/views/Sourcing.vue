<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">EXTERNAL SOURCING</p>
        <h1>外部智能寻源</h1>
        <p>
          汇集外部供应商线索，按价格、质量、交付与风险自动评价并形成候选排名。
        </p>
      </div>
      <el-button type="primary" @click="openCreate">新建寻源项目</el-button>
    </div>
    <div class="connector-note">
      <strong>外部数据接入</strong
      ><span
        >候选供应商可来自行业平台、企业系统
        API、展会名录或人工调研；来源链接和能力证据随项目保存。</span
      >
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索寻源项目"
        @keyup.enter.native="search"
        @clear="search"
      /><el-select
        v-model="statusFilter"
        clearable
        placeholder="全部状态"
        @change="search"
        ><el-option label="待评价" value="draft" /><el-option
          label="已评价"
          value="evaluated" /></el-select
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
      empty-text="暂无寻源项目"
      ><el-table-column
        prop="name"
        label="项目名称"
        min-width="190"
      /><el-table-column
        prop="category"
        label="品类"
        width="140"
      /><el-table-column label="候选数" width="90"
        ><template slot-scope="s">{{
          s.row.candidates.length
        }}</template></el-table-column
      ><el-table-column label="推荐供应商" min-width="170"
        ><template slot-scope="s"
          ><strong
            v-if="s.row.result.recommended_supplier"
            class="blue-number"
            >{{ s.row.result.recommended_supplier }}</strong
          ><span v-else>-</span></template
        ></el-table-column
      ><el-table-column label="状态" width="100"
        ><template slot-scope="s"
          ><el-tag :type="s.row.status === 'evaluated' ? 'success' : 'info'">{{
            s.row.status === "evaluated" ? "已评价" : "待评价"
          }}</el-tag></template
        ></el-table-column
      ><el-table-column label="操作" width="220" fixed="right"
        ><template slot-scope="s"
          ><el-button type="text" @click="edit(s.row)">编辑</el-button
          ><el-button type="text" @click="evaluate(s.row)">智能评价</el-button
          ><el-button
            v-if="s.row.status === 'evaluated'"
            type="text"
            @click="showResult(s.row)"
            >排名</el-button
          ><el-button type="text" class="danger-link" @click="remove(s.row)"
            >删除</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <div class="pagination-row">
      <span>共 {{ page.total }} 条</span
      ><el-pagination
        background
        layout="sizes, prev, pager, next"
        :page-sizes="[10, 20, 50]"
        :current-page="page.page"
        :page-size="page.page_size"
        :total="page.total"
        @current-change="
          (v) => {
            page.page = v;
            load();
          }
        "
        @size-change="changeSize"
      />
    </div>
    <el-dialog
      :title="editingId ? '编辑寻源项目' : '新建寻源项目'"
      :visible.sync="formVisible"
      width="900px"
      :close-on-click-modal="false"
      ><el-form ref="form" :model="form" :rules="rules" label-width="90px"
        ><el-row :gutter="14"
          ><el-col :span="12"
            ><el-form-item label="项目名称" prop="name"
              ><el-input v-model.trim="form.name" /></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="采购品类" prop="category"
              ><el-input
                v-model.trim="form.category" /></el-form-item></el-col></el-row
        ><el-form-item label="寻源要求"
          ><el-input
            v-model="form.requirements"
            type="textarea"
            :rows="2"
            placeholder="认证、产能、工艺、地域与交期要求"
        /></el-form-item>
        <div class="dialog-section-title">
          <strong>外部候选供应商</strong
          ><el-button
            size="mini"
            icon="el-icon-plus"
            @click="form.candidates.push(emptyCandidate())"
            >添加候选</el-button
          >
        </div>
        <el-table :data="form.candidates" border size="mini"
          ><el-table-column label="供应商/来源" min-width="190"
            ><template slot-scope="s"
              ><el-input
                v-model.trim="s.row.supplier_name"
                placeholder="供应商名称" /><el-input
                v-model.trim="s.row.source_url"
                class="stack-input"
                placeholder="来源网址或API标识" /></template></el-table-column
          ><el-table-column label="国家/能力" min-width="160"
            ><template slot-scope="s"
              ><el-input v-model.trim="s.row.country" /><el-input
                v-model.trim="s.row.capabilities"
                class="stack-input"
                placeholder="资质与能力" /></template></el-table-column
          ><el-table-column label="价格" width="95"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.price_score"
                :min="0"
                :max="100"
                controls-position="right" /></template></el-table-column
          ><el-table-column label="质量" width="95"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.quality_score"
                :min="0"
                :max="100"
                controls-position="right" /></template></el-table-column
          ><el-table-column label="交付" width="95"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.delivery_score"
                :min="0"
                :max="100"
                controls-position="right" /></template></el-table-column
          ><el-table-column label="风险" width="105"
            ><template slot-scope="s"
              ><el-select v-model="s.row.risk_level"
                ><el-option label="低" value="low" /><el-option
                  label="中"
                  value="medium" /><el-option
                  label="高"
                  value="high" /></el-select></template></el-table-column
          ><el-table-column width="60"
            ><template slot-scope="s"
              ><el-button
                type="text"
                class="danger-link"
                @click="form.candidates.splice(s.$index, 1)"
                >移除</el-button
              ></template
            ></el-table-column
          ></el-table
        ></el-form
      ><span slot="footer"
        ><el-button @click="formVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存项目</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="候选供应商智能排名"
      :visible.sync="resultVisible"
      width="820px"
      ><el-table v-if="selected" :data="selected.result.ranking" border
        ><el-table-column
          type="index"
          label="排名"
          width="65" /><el-table-column
          prop="supplier_name"
          label="供应商"
          min-width="170" /><el-table-column
          prop="country"
          label="国家/地区"
          width="100" /><el-table-column
          prop="score"
          label="综合得分"
          width="100"
          ><template slot-scope="s"
            ><strong class="blue-number">{{ s.row.score }}</strong></template
          ></el-table-column
        ><el-table-column
          prop="quality_score"
          label="质量"
          width="80" /><el-table-column
          prop="delivery_score"
          label="交付"
          width="80" /><el-table-column label="风险" width="80"
          ><template slot-scope="s">{{
            riskName(s.row.risk_level)
          }}</template></el-table-column
        ><el-table-column
          prop="capabilities"
          label="能力证据"
          min-width="170"
          show-overflow-tooltip /></el-table
    ></el-dialog>
  </div>
</template>
<script>
import { api } from "../api/client";
const emptyCandidate = () => ({
  supplier_name: "",
  country: "中国",
  source_url: "",
  capabilities: "",
  price_score: 80,
  quality_score: 80,
  delivery_score: 80,
  risk_level: "low",
});
const emptyForm = () => ({
  name: "",
  category: "",
  requirements: "",
  candidates: [emptyCandidate()],
});
export default {
  data: () => ({
    items: [],
    keyword: "",
    statusFilter: "",
    loading: false,
    saving: false,
    formVisible: false,
    resultVisible: false,
    editingId: "",
    selected: null,
    form: emptyForm(),
    page: { page: 1, page_size: 10, total: 0 },
    rules: {
      name: [{ required: true, message: "请输入项目名称", trigger: "blur" }],
      category: [
        { required: true, message: "请输入采购品类", trigger: "blur" },
      ],
    },
  }),
  created() {
    this.load();
  },
  methods: {
    emptyCandidate,
    riskName(v) {
      return { low: "低", medium: "中", high: "高" }[v] || v;
    },
    async load() {
      this.loading = true;
      try {
        const params = {
          page: this.page.page,
          page_size: this.page.page_size,
          keyword: this.keyword,
        };
        if (this.statusFilter) params.status = this.statusFilter;
        const { data } = await api.get("/sourcing-projects", { params });
        this.items = data.items;
        this.page.total = data.total;
      } catch (_) {
        this.$message.error("寻源项目加载失败");
      } finally {
        this.loading = false;
      }
    },
    search() {
      this.page.page = 1;
      this.load();
    },
    changeSize(v) {
      this.page.page_size = v;
      this.page.page = 1;
      this.load();
    },
    openCreate() {
      this.editingId = "";
      this.form = emptyForm();
      this.formVisible = true;
    },
    edit(item) {
      this.editingId = item.id;
      this.form = {
        name: item.name,
        category: item.category,
        requirements: item.requirements,
        candidates: item.candidates.map((v) => ({ ...v })),
      };
      this.formVisible = true;
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        if (this.form.candidates.some((v) => !v.supplier_name))
          return this.$message.warning("请填写候选供应商名称");
        this.saving = true;
        try {
          if (this.editingId)
            await api.patch(`/sourcing-projects/${this.editingId}`, this.form);
          else await api.post("/sourcing-projects", this.form);
          this.$message.success("寻源项目已保存");
          this.formVisible = false;
          await this.load();
        } catch (error) {
          this.$message.error(
            (error.response &&
              error.response.data &&
              error.response.data.detail) ||
              "保存失败"
          );
        } finally {
          this.saving = false;
        }
      });
    },
    async evaluate(item) {
      try {
        const { data } = await api.post(
          `/sourcing-projects/${item.id}/evaluate`
        );
        this.$message.success("候选供应商评价完成");
        await this.load();
        this.selected = data;
        this.resultVisible = true;
      } catch (error) {
        this.$message.error(
          (error.response &&
            error.response.data &&
            error.response.data.detail) ||
            "评价失败"
        );
      }
    },
    showResult(item) {
      this.selected = item;
      this.resultVisible = true;
    },
    async remove(item) {
      try {
        await this.$confirm(`确定删除 ${item.name}？`, "删除确认", {
          type: "warning",
        });
        await api.delete(`/sourcing-projects/${item.id}`);
        this.$message.success("寻源项目已删除");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("删除失败");
      }
    },
  },
};
</script>

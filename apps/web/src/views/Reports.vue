<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">REPORTING & AUDIT</p>
        <h1>报告与审计</h1>
        <p>基于实时采购数据生成管理报告，并提供不可篡改的业务操作审计查询。</p>
      </div>
      <el-button
        v-if="activeTab === 'reports'"
        type="primary"
        @click="openCreate"
        >新建报告</el-button
      >
    </div>
    <el-tabs v-model="activeTab" @tab-click="loadActive"
      ><el-tab-pane label="采购报告" name="reports"
        ><div class="table-toolbar">
          <el-input
            v-model.trim="keyword"
            clearable
            placeholder="搜索报告标题"
            @keyup.enter.native="search"
            @clear="search"
          /><el-select
            v-model="statusFilter"
            clearable
            placeholder="全部状态"
            @change="search"
            ><el-option label="待生成" value="draft" /><el-option
              label="已生成"
              value="generated" /></el-select
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
          :data="reports"
          class="data-table"
          empty-text="暂无报告"
          ><el-table-column
            prop="title"
            label="报告标题"
            min-width="220"
          /><el-table-column label="类型" width="130"
            ><template slot-scope="s">{{
              typeName(s.row.report_type)
            }}</template></el-table-column
          ><el-table-column
            prop="notes"
            label="说明"
            min-width="180"
            show-overflow-tooltip
          /><el-table-column label="状态" width="100"
            ><template slot-scope="s"
              ><el-tag
                :type="s.row.status === 'generated' ? 'success' : 'info'"
                >{{
                  s.row.status === "generated" ? "已生成" : "待生成"
                }}</el-tag
              ></template
            ></el-table-column
          ><el-table-column
            prop="updated_at"
            label="更新时间"
            width="180"
          /><el-table-column label="操作" width="210" fixed="right"
            ><template slot-scope="s"
              ><el-button type="text" @click="edit(s.row)">编辑</el-button
              ><el-button type="text" @click="generate(s.row)">生成</el-button
              ><el-button
                v-if="s.row.status === 'generated'"
                type="text"
                @click="view(s.row)"
                >查看</el-button
              ><el-button type="text" class="danger-link" @click="remove(s.row)"
                >删除</el-button
              ></template
            ></el-table-column
          ></el-table
        ><pager
          :page="reportPage"
          @change="
            reportPage.page = $event;
            loadReports();
          "
          @size="
            reportPage.page_size = $event;
            reportPage.page = 1;
            loadReports();
          " /></el-tab-pane
      ><el-tab-pane label="操作审计" name="audit"
        ><div class="table-toolbar">
          <el-input
            v-model.trim="auditKeyword"
            clearable
            placeholder="搜索人员、单据或详情"
            @keyup.enter.native="loadAudit"
            @clear="loadAudit"
          /><el-input
            v-model.trim="auditType"
            clearable
            placeholder="资源类型，如 order"
          /><el-button icon="el-icon-search" @click="loadAudit">查询</el-button>
        </div>
        <el-alert
          title="审计记录由系统业务动作自动写入，只允许查询，不允许修改或删除。"
          type="info"
          :closable="false"
          show-icon /><el-table
          v-loading="loading"
          :data="audits"
          class="data-table outbox-table"
          empty-text="暂无审计记录"
          ><el-table-column
            prop="created_at"
            label="时间"
            width="180" /><el-table-column
            prop="actor_id"
            label="操作人"
            width="140" /><el-table-column
            prop="actor_role"
            label="角色"
            width="150" /><el-table-column
            prop="action"
            label="动作"
            width="100" /><el-table-column
            prop="resource_type"
            label="业务类型"
            width="120" /><el-table-column
            prop="resource_id"
            label="业务ID"
            width="180"
            show-overflow-tooltip /><el-table-column
            prop="detail"
            label="详情"
            min-width="220"
            show-overflow-tooltip /></el-table
        ><pager
          :page="auditPage"
          @change="
            auditPage.page = $event;
            loadAudit();
          "
          @size="
            auditPage.page_size = $event;
            auditPage.page = 1;
            loadAudit();
          " /></el-tab-pane
    ></el-tabs>
    <el-dialog
      :title="editingId ? '编辑报告' : '新建报告'"
      :visible.sync="formVisible"
      width="560px"
      ><el-form ref="form" :model="form" :rules="rules" label-width="90px"
        ><el-form-item label="报告标题" prop="title"
          ><el-input v-model.trim="form.title" /></el-form-item
        ><el-form-item label="报告类型"
          ><el-select v-model="form.report_type" style="width: 100%"
            ><el-option label="采购运营总览" value="overview" /><el-option
              label="供应商绩效"
              value="supplier" /><el-option
              label="质量分析"
              value="quality" /><el-option
              label="合同履约"
              value="contract" /></el-select></el-form-item
        ><el-form-item label="报告说明"
          ><el-input
            v-model="form.notes"
            type="textarea"
            :rows="4" /></el-form-item></el-form
      ><span slot="footer"
        ><el-button @click="formVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存报告</el-button
        ></span
      ></el-dialog
    ><el-dialog title="采购分析报告" :visible.sync="detailVisible" width="760px"
      ><template v-if="selected && selected.content.summary"
        ><div class="report-title">
          <h2>{{ selected.title }}</h2>
          <span>生成时间：{{ selected.content.generated_at }}</span>
        </div>
        <div class="report-metrics">
          <div>
            <span>采购订单</span
            ><strong>{{ selected.content.summary.orders }}</strong>
          </div>
          <div>
            <span>供应商</span
            ><strong>{{ selected.content.summary.suppliers }}</strong>
          </div>
          <div>
            <span>有效合同</span
            ><strong>{{ selected.content.summary.active_contracts }}</strong>
          </div>
          <div>
            <span>质量合格率</span
            ><strong>{{ selected.content.summary.quality_pass_rate }}%</strong>
          </div>
        </div>
        <h3>智能洞察</h3>
        <ul class="insight-list">
          <li v-for="(text, index) in selected.content.insights" :key="index">
            {{ text }}
          </li>
        </ul></template
      ></el-dialog
    >
  </div>
</template>
<script>
import { api } from "../api/client";
import Pager from "../components/Pager.vue";
const emptyForm = () => ({ title: "", report_type: "overview", notes: "" });
export default {
  components: { Pager },
  data: () => ({
    activeTab: "reports",
    reports: [],
    audits: [],
    keyword: "",
    statusFilter: "",
    auditKeyword: "",
    auditType: "",
    loading: false,
    saving: false,
    formVisible: false,
    detailVisible: false,
    editingId: "",
    selected: null,
    form: emptyForm(),
    reportPage: { page: 1, page_size: 10, total: 0 },
    auditPage: { page: 1, page_size: 10, total: 0 },
    rules: {
      title: [{ required: true, message: "请输入报告标题", trigger: "blur" }],
    },
  }),
  created() {
    this.loadReports();
  },
  methods: {
    typeName(v) {
      return (
        {
          overview: "采购运营总览",
          supplier: "供应商绩效",
          quality: "质量分析",
          contract: "合同履约",
        }[v] || v
      );
    },
    loadActive() {
      if (this.activeTab === "reports") this.loadReports();
      else this.loadAudit();
    },
    async loadReports() {
      this.loading = true;
      try {
        const params = {
          page: this.reportPage.page,
          page_size: this.reportPage.page_size,
          keyword: this.keyword,
        };
        if (this.statusFilter) params.status = this.statusFilter;
        const { data } = await api.get("/reports", { params });
        this.reports = data.items;
        this.reportPage.total = data.total;
      } catch (_) {
        this.$message.error("报告加载失败");
      } finally {
        this.loading = false;
      }
    },
    async loadAudit() {
      this.loading = true;
      try {
        const { data } = await api.get("/audit-logs", {
          params: {
            page: this.auditPage.page,
            page_size: this.auditPage.page_size,
            keyword: this.auditKeyword,
            resource_type: this.auditType,
          },
        });
        this.audits = data.items;
        this.auditPage.total = data.total;
      } catch (_) {
        this.$message.error("审计记录加载失败");
      } finally {
        this.loading = false;
      }
    },
    search() {
      this.reportPage.page = 1;
      this.loadReports();
    },
    openCreate() {
      this.editingId = "";
      this.form = emptyForm();
      this.formVisible = true;
    },
    edit(item) {
      this.editingId = item.id;
      this.form = {
        title: item.title,
        report_type: item.report_type,
        notes: item.notes,
      };
      this.formVisible = true;
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        this.saving = true;
        try {
          if (this.editingId)
            await api.patch(`/reports/${this.editingId}`, this.form);
          else await api.post("/reports", this.form);
          this.$message.success("报告定义已保存");
          this.formVisible = false;
          await this.loadReports();
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
    async generate(item) {
      try {
        const { data } = await api.post(`/reports/${item.id}/generate`);
        this.$message.success("报告已基于实时数据生成");
        await this.loadReports();
        this.selected = data;
        this.detailVisible = true;
      } catch (_) {
        this.$message.error("报告生成失败");
      }
    },
    view(item) {
      this.selected = item;
      this.detailVisible = true;
    },
    async remove(item) {
      try {
        await this.$confirm(`确定删除 ${item.title}？`, "删除确认", {
          type: "warning",
        });
        await api.delete(`/reports/${item.id}`);
        this.$message.success("报告已删除");
        await this.loadReports();
      } catch (error) {
        if (error !== "cancel") this.$message.error("删除失败");
      }
    },
  },
};
</script>

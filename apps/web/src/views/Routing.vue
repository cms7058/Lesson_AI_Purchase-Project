<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">MULTI-PLANT OPTIMIZATION</p>
        <h1>多工厂供货路径优化</h1>
        <p>
          在供应能力、工厂需求、线路容量、运输成本、交期和风险约束下计算全局最优分配。
        </p>
      </div>
      <el-button type="primary" @click="openCreate">新建优化方案</el-button>
    </div>
    <div class="process-strip">
      <span>供应商产能</span><i>＋</i><span>工厂需求</span><i>＋</i
      ><span>线路成本/约束</span><i>→</i><span>最小费用流方案</span>
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索路径方案"
        @keyup.enter.native="search"
        @clear="search"
      /><el-select
        v-model="statusFilter"
        clearable
        placeholder="全部状态"
        @change="search"
        ><el-option label="待优化" value="draft" /><el-option
          label="已优化"
          value="optimized" /><el-option
          label="不可行"
          value="infeasible" /></el-select
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
      empty-text="暂无路径方案"
      ><el-table-column
        prop="name"
        label="方案名称"
        min-width="190"
      /><el-table-column
        prop="material_code"
        label="物料编码"
        width="140"
      /><el-table-column label="供应商/工厂" width="120"
        ><template slot-scope="s"
          >{{ s.row.supplies.length }} / {{ s.row.demands.length }}</template
        ></el-table-column
      ><el-table-column label="分配量" width="100"
        ><template slot-scope="s">{{
          s.row.result.allocated || "-"
        }}</template></el-table-column
      ><el-table-column label="运输总成本" width="130"
        ><template slot-scope="s"
          ><strong
            v-if="s.row.result.total_transport_cost !== undefined"
            class="blue-number"
            >¥ {{ s.row.result.total_transport_cost }}</strong
          ><span v-else>-</span></template
        ></el-table-column
      ><el-table-column label="状态" width="100"
        ><template slot-scope="s"
          ><el-tag :type="statusType(s.row.status)">{{
            statusName(s.row.status)
          }}</el-tag></template
        ></el-table-column
      ><el-table-column label="操作" width="220" fixed="right"
        ><template slot-scope="s"
          ><el-button type="text" @click="edit(s.row)">编辑</el-button
          ><el-button type="text" @click="optimize(s.row)">优化计算</el-button
          ><el-button
            v-if="s.row.result.allocations"
            type="text"
            @click="showResult(s.row)"
            >方案</el-button
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
        @current-change="changePage"
        @size-change="changeSize"
      />
    </div>
    <el-dialog
      :title="editingId ? '编辑路径方案' : '新建路径方案'"
      :visible.sync="formVisible"
      width="940px"
      :close-on-click-modal="false"
      ><el-form ref="form" :model="form" :rules="rules" label-width="90px"
        ><el-row :gutter="14"
          ><el-col :span="10"
            ><el-form-item label="方案名称" prop="name"
              ><el-input v-model.trim="form.name" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="物料编码" prop="material_code"
              ><el-input
                v-model.trim="form.material_code"
                :disabled="!!editingId" /></el-form-item></el-col
          ><el-col :span="4"
            ><el-form-item label="交期权重"
              ><el-input-number
                v-model="form.lead_weight"
                :min="0"
                :precision="2" /></el-form-item></el-col
          ><el-col :span="4"
            ><el-form-item label="风险权重"
              ><el-input-number
                v-model="form.risk_weight"
                :min="0"
                :precision="2" /></el-form-item></el-col></el-row
        ><el-tabs
          ><el-tab-pane label="供应能力"
            ><div class="dialog-section-title">
              <strong>供应商可供能力</strong
              ><el-button
                size="mini"
                @click="form.supplies.push({ supplier: '', capacity: 1 })"
                >添加</el-button
              >
            </div>
            <el-table :data="form.supplies" border size="mini"
              ><el-table-column label="供应商"
                ><template slot-scope="s"
                  ><el-input
                    v-model.trim="s.row.supplier" /></template></el-table-column
              ><el-table-column label="最大供货量"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.capacity"
                    :min="0.01"
                    style="width: 100%" /></template></el-table-column
              ><el-table-column width="70"
                ><template slot-scope="s"
                  ><el-button
                    type="text"
                    class="danger-link"
                    :disabled="form.supplies.length === 1"
                    @click="form.supplies.splice(s.$index, 1)"
                    >移除</el-button
                  ></template
                ></el-table-column
              ></el-table
            ></el-tab-pane
          ><el-tab-pane label="工厂需求"
            ><div class="dialog-section-title">
              <strong>工厂需求数量</strong
              ><el-button
                size="mini"
                @click="form.demands.push({ factory: '', quantity: 1 })"
                >添加</el-button
              >
            </div>
            <el-table :data="form.demands" border size="mini"
              ><el-table-column label="工厂"
                ><template slot-scope="s"
                  ><el-input
                    v-model.trim="s.row.factory" /></template></el-table-column
              ><el-table-column label="需求数量"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.quantity"
                    :min="0.01"
                    style="width: 100%" /></template></el-table-column
              ><el-table-column width="70"
                ><template slot-scope="s"
                  ><el-button
                    type="text"
                    class="danger-link"
                    :disabled="form.demands.length === 1"
                    @click="form.demands.splice(s.$index, 1)"
                    >移除</el-button
                  ></template
                ></el-table-column
              ></el-table
            ></el-tab-pane
          ><el-tab-pane label="可用线路"
            ><div class="dialog-section-title">
              <strong>供应商—工厂线路</strong
              ><el-button size="mini" @click="form.lanes.push(emptyLane())"
                >添加</el-button
              >
            </div>
            <el-table :data="form.lanes" border size="mini"
              ><el-table-column label="供应商" width="140"
                ><template slot-scope="s"
                  ><el-select v-model="s.row.supplier" style="width: 100%"
                    ><el-option
                      v-for="v in form.supplies"
                      :key="v.supplier"
                      :label="v.supplier"
                      :value="
                        v.supplier
                      " /></el-select></template></el-table-column
              ><el-table-column label="工厂" width="140"
                ><template slot-scope="s"
                  ><el-select v-model="s.row.factory" style="width: 100%"
                    ><el-option
                      v-for="v in form.demands"
                      :key="v.factory"
                      :label="v.factory"
                      :value="
                        v.factory
                      " /></el-select></template></el-table-column
              ><el-table-column label="单位运费"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.unit_cost"
                    :min="0"
                    :precision="2" /></template></el-table-column
              ><el-table-column label="交期天"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.lead_days"
                    :min="0" /></template></el-table-column
              ><el-table-column label="风险分"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.risk_score"
                    :min="0"
                    :max="100" /></template></el-table-column
              ><el-table-column label="线路上限"
                ><template slot-scope="s"
                  ><el-input-number
                    v-model="s.row.max_quantity"
                    :min="0.01"
                    placeholder="不限" /></template></el-table-column
              ><el-table-column width="60"
                ><template slot-scope="s"
                  ><el-button
                    type="text"
                    class="danger-link"
                    :disabled="form.lanes.length === 1"
                    @click="form.lanes.splice(s.$index, 1)"
                    >移除</el-button
                  ></template
                ></el-table-column
              ></el-table
            ></el-tab-pane
          ></el-tabs
        ></el-form
      ><span slot="footer"
        ><el-button @click="formVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存方案</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="最优供货分配方案"
      :visible.sync="resultVisible"
      width="820px"
      ><template v-if="selected"
        ><el-alert
          :title="selected.result.message"
          :type="selected.result.feasible ? 'success' : 'error'"
          :closable="false"
          show-icon /><el-descriptions
          :column="3"
          border
          class="dialog-form-spaced"
          ><el-descriptions-item label="需求总量">{{
            selected.result.required
          }}</el-descriptions-item
          ><el-descriptions-item label="已分配">{{
            selected.result.allocated
          }}</el-descriptions-item
          ><el-descriptions-item label="运输成本"
            >¥ {{ selected.result.total_transport_cost }}</el-descriptions-item
          ></el-descriptions
        ><el-table
          :data="selected.result.allocations"
          border
          class="dialog-form-spaced"
          ><el-table-column prop="supplier" label="供应商" /><el-table-column
            prop="factory"
            label="工厂" /><el-table-column
            prop="quantity"
            label="分配量" /><el-table-column
            prop="unit_cost"
            label="单位运费" /><el-table-column
            prop="lead_days"
            label="交期(天)" /><el-table-column
            prop="cost"
            label="线路成本" /></el-table></template
    ></el-dialog>
  </div>
</template>
<script>
import { api } from "../api/client";
const emptyLane = () => ({
  supplier: "",
  factory: "",
  unit_cost: 0,
  lead_days: 0,
  risk_score: 0,
  max_quantity: 100,
});
const emptyForm = () => ({
  name: "",
  material_code: "",
  supplies: [{ supplier: "供应商A", capacity: 100 }],
  demands: [{ factory: "工厂A", quantity: 100 }],
  lanes: [
    {
      supplier: "供应商A",
      factory: "工厂A",
      unit_cost: 10,
      lead_days: 3,
      risk_score: 5,
      max_quantity: 100,
    },
  ],
  lead_weight: 1,
  risk_weight: 1,
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
      name: [{ required: true, message: "请输入方案名称", trigger: "blur" }],
      material_code: [
        { required: true, message: "请输入物料编码", trigger: "blur" },
      ],
    },
  }),
  created() {
    this.load();
  },
  methods: {
    emptyLane,
    statusName(v) {
      return (
        { draft: "待优化", optimized: "已优化", infeasible: "不可行" }[v] || v
      );
    },
    statusType(v) {
      return (
        { draft: "info", optimized: "success", infeasible: "danger" }[v] || ""
      );
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
        const { data } = await api.get("/routing-plans", { params });
        this.items = data.items;
        this.page.total = data.total;
      } catch (_) {
        this.$message.error("路径方案加载失败");
      } finally {
        this.loading = false;
      }
    },
    search() {
      this.page.page = 1;
      this.load();
    },
    changePage(v) {
      this.page.page = v;
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
        material_code: item.material_code,
        supplies: item.supplies.map((v) => ({ ...v })),
        demands: item.demands.map((v) => ({ ...v })),
        lanes: item.lanes.map((v) => ({ ...v })),
        lead_weight: item.lead_weight,
        risk_weight: item.risk_weight,
      };
      this.formVisible = true;
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        if (
          this.form.supplies.some((v) => !v.supplier) ||
          this.form.demands.some((v) => !v.factory) ||
          this.form.lanes.some((v) => !v.supplier || !v.factory)
        )
          return this.$message.warning("请完整填写节点和线路");
        this.saving = true;
        try {
          if (this.editingId) {
            const payload = { ...this.form };
            delete payload.material_code;
            await api.patch(`/routing-plans/${this.editingId}`, payload);
          } else await api.post("/routing-plans", this.form);
          this.$message.success("路径方案已保存");
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
    async optimize(item) {
      try {
        const { data } = await api.post(`/routing-plans/${item.id}/optimize`);
        await this.load();
        this.selected = data;
        this.resultVisible = true;
        if (data.result.feasible)
          this.$message.success("已计算全局最优供货路径");
        else this.$message.warning(data.result.message);
      } catch (error) {
        this.$message.error(
          (error.response &&
            error.response.data &&
            error.response.data.detail) ||
            "优化失败"
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
        await api.delete(`/routing-plans/${item.id}`);
        this.$message.success("路径方案已删除");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("删除失败");
      }
    },
  },
};
</script>

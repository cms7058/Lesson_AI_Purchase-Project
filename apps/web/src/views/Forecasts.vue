<template>
  <div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">DEMAND INTELLIGENCE</p>
        <h1>需求预测</h1>
        <p>
          利用历史需求线性趋势、库存与在途数据，自动形成未来需求和采购建议。
        </p>
      </div>
      <el-button type="primary" @click="openCreate">新建预测</el-button>
    </div>
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索预测名称"
        @keyup.enter.native="search"
        @clear="search"
      /><el-button icon="el-icon-search" @click="search">查询</el-button
      ><el-button
        @click="
          keyword = '';
          search();
        "
        >重置</el-button
      >
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      class="data-table"
      empty-text="暂无预测方案"
      ><el-table-column
        prop="name"
        label="方案名称"
        min-width="180"
      /><el-table-column
        prop="material_code"
        label="物料编码"
        width="140"
      /><el-table-column
        prop="material_name"
        label="物料名称"
        min-width="150"
      /><el-table-column label="预测合计" width="110"
        ><template slot-scope="s">{{
          s.row.result.forecast_total
        }}</template></el-table-column
      ><el-table-column label="建议采购" width="110"
        ><template slot-scope="s"
          ><strong class="blue-number">{{
            s.row.result.recommended_purchase
          }}</strong></template
        ></el-table-column
      ><el-table-column label="趋势/误差" width="130"
        ><template slot-scope="s"
          >{{ trendName(s.row.result.trend) }} / MAE
          {{ s.row.result.mae }}</template
        ></el-table-column
      ><el-table-column label="操作" width="210" fixed="right"
        ><template slot-scope="s"
          ><el-button type="text" @click="showResult(s.row)">图表</el-button
          ><el-button type="text" @click="edit(s.row)">编辑</el-button
          ><el-button type="text" @click="recalculate(s.row)">重算</el-button
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
      :title="editingId ? '编辑预测方案' : '新建预测方案'"
      :visible.sync="formVisible"
      width="800px"
      :close-on-click-modal="false"
      ><el-form ref="form" :model="form" :rules="rules" label-width="95px"
        ><el-row :gutter="14"
          ><el-col :span="10"
            ><el-form-item label="方案名称" prop="name"
              ><el-input v-model.trim="form.name" /></el-form-item></el-col
          ><el-col :span="7"
            ><el-form-item label="物料编码" prop="material_code"
              ><el-input
                v-model.trim="form.material_code"
                :disabled="!!editingId" /></el-form-item></el-col
          ><el-col :span="7"
            ><el-form-item label="物料名称" prop="material_name"
              ><el-input
                v-model.trim="
                  form.material_name
                " /></el-form-item></el-col></el-row
        ><el-row :gutter="14"
          ><el-col :span="6"
            ><el-form-item label="预测期数"
              ><el-input-number
                v-model="form.horizon"
                :min="1"
                :max="12" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="安全库存"
              ><el-input-number
                v-model="form.safety_stock"
                :min="0" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="现有库存"
              ><el-input-number
                v-model="form.on_hand"
                :min="0" /></el-form-item></el-col
          ><el-col :span="6"
            ><el-form-item label="在途数量"
              ><el-input-number
                v-model="form.in_transit"
                :min="0" /></el-form-item></el-col
        ></el-row>
        <div class="dialog-section-title">
          <strong>历史需求（至少3期）</strong
          ><el-button
            size="mini"
            icon="el-icon-plus"
            @click="form.history.push({ period: '', quantity: 0 })"
            >添加期间</el-button
          >
        </div>
        <el-table :data="form.history" border size="mini"
          ><el-table-column label="期间"
            ><template slot-scope="s"
              ><el-input
                v-model.trim="s.row.period"
                placeholder="如 2026-01" /></template></el-table-column
          ><el-table-column label="需求数量"
            ><template slot-scope="s"
              ><el-input-number
                v-model="s.row.quantity"
                :min="0"
                :precision="2"
                controls-position="right"
                style="width: 100%" /></template></el-table-column
          ><el-table-column width="70"
            ><template slot-scope="s"
              ><el-button
                type="text"
                class="danger-link"
                :disabled="form.history.length <= 3"
                @click="form.history.splice(s.$index, 1)"
                >移除</el-button
              ></template
            ></el-table-column
          ></el-table
        ></el-form
      ><span slot="footer"
        ><el-button @click="formVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >计算并保存</el-button
        ></span
      ></el-dialog
    >
    <el-dialog
      title="预测结果与采购建议"
      :visible.sync="resultVisible"
      width="720px"
      ><template v-if="selected"
        ><el-descriptions :column="3" border
          ><el-descriptions-item label="回归方程" :span="2">{{
            selected.result.equation
          }}</el-descriptions-item
          ><el-descriptions-item label="平均误差">{{
            selected.result.mae
          }}</el-descriptions-item
          ><el-descriptions-item label="预测总量">{{
            selected.result.forecast_total
          }}</el-descriptions-item
          ><el-descriptions-item label="建议采购量"
            ><strong class="blue-number">{{
              selected.result.recommended_purchase
            }}</strong></el-descriptions-item
          ><el-descriptions-item label="趋势">{{
            trendName(selected.result.trend)
          }}</el-descriptions-item></el-descriptions
        >
        <div class="forecast-chart">
          <div
            v-for="(value, index) in selected.result.predicted"
            :key="index"
            class="forecast-bar"
          >
            <span>未来第{{ index + 1 }}期</span>
            <div><i :style="{ width: barWidth(value) }" /></div>
            <strong>{{ value }}</strong>
          </div>
        </div></template
      ></el-dialog
    >
  </div>
</template>
<script>
import { api } from "../api/client";
const emptyForm = () => ({
  name: "",
  material_code: "",
  material_name: "",
  history: [
    { period: "2026-01", quantity: 100 },
    { period: "2026-02", quantity: 110 },
    { period: "2026-03", quantity: 120 },
  ],
  horizon: 3,
  safety_stock: 0,
  on_hand: 0,
  in_transit: 0,
});
export default {
  data: () => ({
    items: [],
    keyword: "",
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
      material_name: [
        { required: true, message: "请输入物料名称", trigger: "blur" },
      ],
    },
  }),
  created() {
    this.load();
  },
  methods: {
    trendName(v) {
      return { up: "上升", down: "下降", stable: "平稳" }[v] || v;
    },
    async load() {
      this.loading = true;
      try {
        const { data } = await api.get("/forecasts", {
          params: {
            page: this.page.page,
            page_size: this.page.page_size,
            keyword: this.keyword,
          },
        });
        this.items = data.items;
        this.page.total = data.total;
      } catch (_) {
        this.$message.error("预测方案加载失败");
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
        material_name: item.material_name,
        history: item.history.map((v) => ({ ...v })),
        horizon: item.horizon,
        safety_stock: item.safety_stock,
        on_hand: item.on_hand,
        in_transit: item.in_transit,
      };
      this.formVisible = true;
    },
    save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return;
        if (this.form.history.some((v) => !v.period))
          return this.$message.warning("请填写全部历史期间");
        this.saving = true;
        try {
          if (this.editingId) {
            const payload = { ...this.form };
            delete payload.material_code;
            await api.patch(`/forecasts/${this.editingId}`, payload);
          } else await api.post("/forecasts", this.form);
          this.$message.success("预测已计算并保存");
          this.formVisible = false;
          await this.load();
        } catch (error) {
          this.$message.error(
            (error.response &&
              error.response.data &&
              error.response.data.detail) ||
              "预测计算失败"
          );
        } finally {
          this.saving = false;
        }
      });
    },
    showResult(item) {
      this.selected = item;
      this.resultVisible = true;
    },
    barWidth(value) {
      const max = Math.max(...this.selected.result.predicted, 1);
      return `${(value / max) * 100}%`;
    },
    async recalculate(item) {
      try {
        await api.post(`/forecasts/${item.id}/recalculate`);
        this.$message.success("预测已重新计算");
        await this.load();
      } catch (_) {
        this.$message.error("重算失败");
      }
    },
    async remove(item) {
      try {
        await this.$confirm(`确定删除 ${item.name}？`, "删除确认", {
          type: "warning",
        });
        await api.delete(`/forecasts/${item.id}`);
        this.$message.success("预测已删除");
        await this.load();
      } catch (error) {
        if (error !== "cancel") this.$message.error("删除失败");
      }
    },
  },
};
</script>

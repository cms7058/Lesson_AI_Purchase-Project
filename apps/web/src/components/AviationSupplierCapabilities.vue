<template>
  <div>
    <el-alert
      title="公开资料参考供应商默认未核实，不会自动进入合格供应商或定标名单。"
      type="warning"
      :closable="false"
    />
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        placeholder="能力、OEM或物料范围"
        @keyup.enter.native="load"
      /><el-button @click="load">查询</el-button
      ><el-button type="primary" @click="open">新增能力</el-button>
    </div>
    <el-table v-loading="loading" :data="items" border
      ><el-table-column
        prop="supplier_name"
        label="供应商"
        min-width="180"
      /><el-table-column
        prop="capability_name"
        label="能力"
        min-width="190"
      /><el-table-column
        prop="supplier_type"
        label="类型"
        width="120"
      /><el-table-column
        prop="oem_scope"
        label="OEM/产品范围"
        min-width="200"
      /><el-table-column label="交易方式" min-width="150"
        ><template slot-scope="s">{{
          s.row.offer_types.join(" / ")
        }}</template></el-table-column
      ><el-table-column label="AOG" width="85"
        ><template slot-scope="s"
          ><el-tag :type="s.row.aog_247 ? 'danger' : 'info'">{{
            s.row.aog_247 ? "24/7" : "常规"
          }}</el-tag></template
        ></el-table-column
      ><el-table-column label="关系状态" width="105"
        ><template slot-scope="s"
          ><el-tag
            :type="
              s.row.relationship_status === 'qualified' ? 'success' : 'warning'
            "
            >{{
              s.row.relationship_status === "qualified" ? "已准入" : "未核实"
            }}</el-tag
          ></template
        ></el-table-column
      ></el-table
    ><el-pagination
      :total="total"
      :page-size="10"
      :current-page.sync="page"
      layout="prev,pager,next"
      @current-change="load"
    /><el-dialog
      title="新增航空供应能力"
      :visible.sync="visible"
      append-to-body
      width="700px"
      ><el-form :model="form" label-width="110px"
        ><el-form-item label="能力名称"
          ><el-input v-model.trim="form.capability_name" /></el-form-item
        ><el-form-item label="供应商类型"
          ><el-select v-model="form.supplier_type"
            ><el-option
              v-for="x in types"
              :key="x[0]"
              :label="x[1]"
              :value="x[0]" /></el-select></el-form-item
        ><el-form-item label="OEM范围"
          ><el-input v-model.trim="form.oem_scope" /></el-form-item
        ><el-form-item label="件号/品类范围"
          ><el-input
            v-model.trim="form.part_scope"
            type="textarea" /></el-form-item
        ><el-form-item label="交易方式"
          ><el-checkbox-group v-model="form.offer_types"
            ><el-checkbox
              v-for="x in ['purchase', 'exchange', 'loan', 'repair']"
              :key="x"
              :label="x" /></el-checkbox-group></el-form-item
        ><el-form-item label="证书能力"
          ><el-select
            v-model="form.certificates"
            multiple
            allow-create
            filterable
            style="width: 100%" /></el-form-item
        ><el-row
          ><el-col :span="12"
            ><el-form-item label="AOG 24/7"
              ><el-switch v-model="form.aog_247" /></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="响应小时"
              ><el-input-number
                v-model="form.response_hours"
                :min="1" /></el-form-item></el-col></el-row
        ><el-form-item label="证据说明"
          ><el-input
            v-model="form.evidence"
            type="textarea" /></el-form-item></el-form
      ><span slot="footer"
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存</el-button
        ></span
      ></el-dialog
    >
  </div>
</template>
<script>
import { api } from "../api/client";
const fresh = () => ({
  capability_name: "",
  supplier_type: "distributor",
  oem_scope: "",
  part_scope: "",
  offer_types: ["purchase"],
  certificates: [],
  aog_247: false,
  response_hours: 24,
  public_reference: false,
  relationship_status: "candidate",
  evidence: "",
});
export default {
  props: { supplierId: { type: String, default: "" } },
  data: () => ({
    items: [],
    total: 0,
    page: 1,
    keyword: "",
    loading: false,
    saving: false,
    visible: false,
    form: fresh(),
    types: [
      ["oem", "OEM"],
      ["authorized_distributor", "授权分销"],
      ["distributor", "分销商"],
      ["repair_station", "维修机构"],
      ["trader", "航材贸易"],
      ["pool", "共享库存"],
    ],
  }),
  created() {
    this.load();
  },
  methods: {
    async load() {
      this.loading = true;
      try {
        const r = (
          await api.get("/aviation-mro/supplier-capabilities", {
            params: {
              supplier_id: this.supplierId,
              keyword: this.keyword,
              page: this.page,
              page_size: 10,
            },
          })
        ).data;
        this.items = r.items;
        this.total = r.total;
      } catch (e) {
        this.$message.error("航空能力加载失败");
      } finally {
        this.loading = false;
      }
    },
    open() {
      if (!this.supplierId)
        return this.$message.warning("请从某个供应商行进入后新增能力");
      this.form = fresh();
      this.visible = true;
    },
    async save() {
      if (!this.form.capability_name)
        return this.$message.warning("请填写能力名称");
      this.saving = true;
      try {
        await api.post(
          `/aviation-mro/suppliers/${this.supplierId}/capabilities`,
          this.form
        );
        this.visible = false;
        await this.load();
        this.$message.success("航空供应能力已保存");
      } catch (e) {
        this.$message.error(e.response?.data?.detail || "保存失败");
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

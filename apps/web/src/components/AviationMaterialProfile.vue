<template>
  <div v-loading="loading">
    <el-alert
      title="航空扩展档案用于适航硬门槛与报价归一；演示PN和构型不具备装机依据。"
      type="warning"
      :closable="false"
    /><el-form :model="form" label-width="120px" style="margin-top: 16px"
      ><el-row :gutter="16"
        ><el-col :span="8"
          ><el-form-item label="Part Number"
            ><el-input v-model.trim="form.part_number" /></el-form-item></el-col
        ><el-col :span="8"
          ><el-form-item label="OEM"
            ><el-input v-model.trim="form.oem" /></el-form-item></el-col
        ><el-col :span="8"
          ><el-form-item label="ATA章节"
            ><el-input
              v-model.trim="form.ata_chapter"
              placeholder="如29、32、72" /></el-form-item></el-col></el-row
      ><el-form-item label="适用机型/构型"
        ><el-input v-model.trim="form.applicability" /></el-form-item
      ><el-row :gutter="16"
        ><el-col :span="8"
          ><el-form-item label="件号控制"
            ><el-checkbox v-model="form.serial_controlled"
              >序列号控制</el-checkbox
            ></el-form-item
          ></el-col
        ><el-col :span="8"
          ><el-form-item label="批次控制"
            ><el-checkbox v-model="form.batch_controlled"
              >批次控制</el-checkbox
            ></el-form-item
          ></el-col
        ><el-col :span="8"
          ><el-form-item label="连续追溯"
            ><el-checkbox v-model="form.trace_required"
              >必须完整追溯</el-checkbox
            ></el-form-item
          ></el-col
        ></el-row
      ><el-form-item label="允许件况"
        ><el-checkbox-group v-model="form.allowed_conditions"
          ><el-checkbox
            v-for="x in ['NEW', 'OH', 'SV', 'AR', 'USM']"
            :key="x"
            :label="x" /></el-checkbox-group></el-form-item
      ><el-form-item label="要求证书"
        ><el-select
          v-model="form.certificate_requirements"
          multiple
          allow-create
          filterable
          style="width: 100%"
          ><el-option
            v-for="x in certificates"
            :key="x"
            :label="x"
            :value="x" /></el-select></el-form-item
      ><el-row :gutter="16"
        ><el-col :span="8"
          ><el-form-item label="Shelf Life(天)"
            ><el-input-number
              v-model="form.shelf_life_days"
              :min="0"
              :max="36500" /></el-form-item></el-col
        ><el-col :span="8"
          ><el-form-item label="寿命限制件"
            ><el-switch v-model="form.life_limited" /></el-form-item></el-col
        ><el-col :span="8"
          ><el-form-item label="默认交易方式"
            ><el-select v-model="form.default_offer_type"
              ><el-option label="直接采购" value="purchase" /><el-option
                label="Exchange换件"
                value="exchange" /><el-option
                label="Loan借件"
                value="loan" /><el-option
                label="Repair送修"
                value="repair" /></el-select></el-form-item></el-col></el-row
      ><el-form-item v-if="form.life_limited" label="最低剩余寿命"
        ><el-input v-model.trim="form.minimum_remaining_life" /></el-form-item
      ><el-form-item label="档案说明"
        ><el-input
          v-model="form.note"
          type="textarea"
          :rows="3" /></el-form-item
      ><el-form-item
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!form.part_number"
          @click="save"
          >保存航空档案</el-button
        ></el-form-item
      ></el-form
    >
  </div>
</template>
<script>
import { api } from "../api/client";
const fresh = (code) => ({
  part_number: code || "",
  oem: "",
  ata_chapter: "",
  applicability: "",
  serial_controlled: false,
  batch_controlled: true,
  allowed_conditions: ["NEW"],
  certificate_requirements: [],
  trace_required: true,
  shelf_life_days: 0,
  life_limited: false,
  minimum_remaining_life: "",
  default_offer_type: "purchase",
  note: "",
});
export default {
  props: { material: { type: Object, required: true } },
  data: () => ({
    loading: false,
    saving: false,
    form: fresh(""),
    certificates: [
      "8130-3",
      "EASA Form 1",
      "CAAC AAC-038",
      "CoC",
      "维修履历",
      "批次追溯",
      "校准证书",
      "SDS",
    ],
  }),
  created() {
    this.load();
  },
  methods: {
    async load() {
      this.loading = true;
      try {
        this.form =
          (
            await api.get(
              `/aviation-mro/materials/${encodeURIComponent(
                this.material.code
              )}`
            )
          ).data || fresh(this.material.code);
      } catch (e) {
        this.$message.error(e.response?.data?.detail || "航空档案加载失败");
      } finally {
        this.loading = false;
      }
    },
    async save() {
      this.saving = true;
      try {
        await api.put(
          `/aviation-mro/materials/${encodeURIComponent(this.material.code)}`,
          this.form
        );
        this.$message.success("航空MRO扩展档案已保存");
      } catch (e) {
        this.$message.error(e.response?.data?.detail || "保存失败");
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

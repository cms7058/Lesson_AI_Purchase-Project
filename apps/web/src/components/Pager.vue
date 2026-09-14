<template>
  <div class="pagination-row">
    <span>共 {{ value.total }} 条</span>
    <el-pagination background layout="sizes, prev, pager, next"
      :page-sizes="[10, 20, 50]" :current-page="value.page"
      :page-size="value.page_size" :total="value.total"
      @current-change="changePage" @size-change="$emit('size', $event)" />
  </div>
</template>
<script>
export default {
  props: { page: Object, pagination: Object },
  computed: { value() { return this.pagination || this.page || { page: 1, page_size: 10, total: 0 }; } },
  methods: { changePage(value) { this.$emit("page", value); this.$emit("change", value); } },
};
</script>

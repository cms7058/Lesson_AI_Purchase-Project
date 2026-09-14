<template>
  <div>
    <div class="page-heading"><div><p class="eyebrow">已纳入开发范围</p><h1>{{ title }}</h1><p>{{ description }}</p></div><span class="planned-badge">领域骨架已建立</span></div>
    <div class="feature-list"><div v-for="(feature, index) in features" :key="feature" class="feature-row"><span>{{ String(index + 1).padStart(2, "0") }}</span><div><h3>{{ feature }}</h3><p>将在对应纵向切片中完成数据模型、API、页面、工作流和验收测试。</p></div></div></div>
  </div>
</template>

<script>
export default { props: { title: String, description: String, features: { type: Array, default: () => [] } } };
</script>


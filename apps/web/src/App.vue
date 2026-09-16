<template>
  <div>
    <router-view v-if="$route.meta.standalone" />
    <div v-else class="app-shell">
      <aside class="sidebar">
        <router-link class="brand" to="/" aria-label="返回AI助力首页">
          <BrandMark />
          <div><strong>AI助力</strong><small>项目与采购教学平台</small></div>
        </router-link>
        <nav>
          <section
            v-for="group in navGroups"
            :key="group.label"
            class="nav-group"
          >
            <button
              type="button"
              class="nav-group-title"
              @click="toggle(group.label)"
            >
              <span>{{ group.icon }} {{ group.label }}</span
              ><i :class="{ open: opened[group.label] }">⌄</i>
            </button>
            <div v-show="opened[group.label]" class="nav-children">
              <template v-for="item in group.items"
                ><div v-if="item.items" :key="item.label" class="nav-subgroup">
                  <button class="nav-group-title" @click="toggle(item.label)">
                    <span>{{ item.icon }} {{ item.label }}</span
                    ><i :class="{ open: opened[item.label] }">⌄</i>
                  </button>
                  <div v-show="opened[item.label]" style="padding-left: 14px">
                    <router-link
                      v-for="child in item.items"
                      :key="child.path"
                      :to="child.path"
                      ><span>{{ child.icon }}</span
                      >{{ child.label }}</router-link
                    >
                  </div>
                </div>
                <router-link v-else :key="item.path" :to="item.path" exact
                  ><span>{{ item.icon }}</span
                  >{{ item.label }}</router-link
                ></template
              >
            </div>
          </section>
        </nav>
      </aside>
      <main class="main-panel">
        <header class="topbar">
          <div>
            <strong>AI助力 · 智能项目与采购教学平台</strong
            ><span>演示 · 实训 · 决策复盘</span>
          </div>
          <div class="user-chip">{{ user.organization }} · {{ user.name }}</div>
        </header>
        <section class="page">
          <ListFilters @query="queryList" /><router-view ref="pageView" />
        </section>
      </main>
    </div>
    <FloatingAssistant v-if="!$route.meta.hideAssistant" />
  </div>
</template>

<script>
import ListFilters from "./components/ListFilters.vue";
import FloatingAssistant from "./components/FloatingAssistant.vue";
import BrandMark from "./components/BrandMark.vue";
export default {
  components: { ListFilters, FloatingAssistant, BrandMark },
  created() {
    if (!this.$route.meta.standalone) this.$store.dispatch("loadIdentity");
  },
  watch: {
    $route(route) {
      if (!route.meta.standalone && !this.user.role)
        this.$store.dispatch("loadIdentity");
    },
  },
  computed: {
    user() {
      return this.$store.state.user;
    },
  },
  methods: {
    toggle(label) {
      this.$set(this.opened, label, !this.opened[label]);
    },
    queryList(resource) {
      const view = this.$refs.pageView;
      if (!view) return;
      const tabs = {
        "material-categories": "categories",
        "supplier-category-links": "links",
        "staff-users": "staff",
        "buyer-authorizations": "authorizations",
        workflows: "definitions",
        "workflow-runs": "runs",
        "notification-outbox": "outbox",
        "audit-logs": "audit",
      };
      if ("active" in view.$data) view.active = tabs[resource] || resource;
      if ("activeTab" in view.$data)
        view.activeTab = tabs[resource] || resource;
      Object.values(view.$data).forEach((value) => {
        if (
          value &&
          typeof value === "object" &&
          !Array.isArray(value) &&
          "page" in value &&
          "page_size" in value
        )
          value.page = 1;
      });
      const loaders = {
        workflows: "loadWorkflows",
        "workflow-runs": "loadRuns",
        "notification-outbox": "loadOutbox",
        reports: "loadReports",
        "audit-logs": "loadAudit",
      };
      this.$nextTick(() => {
        const fn = view[loaders[resource] || "load"];
        if (fn) fn.call(view);
      });
    },
  },
  data: () => ({
    opened: {
      项目管理: true,
      AI采购中心: true,
      供应商中心: true,
      物料主数据中心: true,
      MRO需求计划中心: true,
      智能库存中心: true,
      设备与备件中心: true,
      合同与成本中心: true,
      AI决策中心: true,
      系统与知识库: true,
    },
    navGroups: [
      {
        label: "项目管理",
        icon: "▦",
        items: [
          { path: "/project-dashboard", label: "项目驾驶舱", icon: "▦" },
          { path: "/projects", label: "项目台账与计划", icon: "▤" },
          {
            path: "/project-notifications",
            label: "项目通知与预警",
            icon: "✉",
          },
        ],
      },
      {
        label: "AI采购中心",
        icon: "▤",
        items: [
          { path: "/procurement-dashboard", label: "采购驾驶舱", icon: "▦" },
          { path: "/requisitions", label: "采购申请与审批", icon: "☑" },
          { path: "/rfqs", label: "RFQ与报价中心", icon: "◌" },
          { path: "/sourcing", label: "智能寻源", icon: "⌕" },
          { path: "/orders", label: "采购订单与PO跟踪", icon: "▤" },
          { path: "/fulfillment", label: "收货质检与退货", icon: "✓" },
        ],
      },
      {
        label: "供应商中心",
        icon: "◉",
        items: [{ path: "/suppliers", label: "供应商管理与分析", icon: "◉" }],
      },
      {
        label: "物料主数据中心",
        icon: "▥",
        items: [{ path: "/materials", label: "物料分类与档案", icon: "▥" }],
      },
      {
        label: "MRO需求计划中心",
        icon: "⌁",
        items: [
          { path: "/mro-planning", label: "MRO预测与采购供货计划", icon: "▦" },
          { path: "/forecast", label: "通用需求预测", icon: "⌁" },
        ],
      },
      {
        label: "智能库存中心",
        icon: "▥",
        items: [
          { path: "/warehouse", label: "库存与仓储管理", icon: "▤" },
          {
            path: "/inventory-intelligence",
            label: "智能库存与LCC",
            icon: "∑",
          },
        ],
      },
      {
        label: "设备与备件中心",
        icon: "◇",
        items: [
          { path: "/equipment-mro", label: "设备与MRO闭环", icon: "⚙" },
          { path: "/spare-strategies", label: "备件采购策略", icon: "⌁" },
        ],
      },
      {
        label: "合同与成本中心",
        icon: "▣",
        items: [
          { path: "/contracts", label: "合同管理", icon: "▣" },
          { path: "/settlements", label: "对账发票与付款", icon: "￥" },
          { path: "/material-costs", label: "物料采购成本分析", icon: "∑" },
        ],
      },
      {
        label: "AI决策中心",
        icon: "✧",
        items: [
          { path: "/routing", label: "多工厂路径优化", icon: "⌘" },
          { path: "/reports", label: "报告、审计与分析", icon: "□" },
        ],
      },
      {
        label: "系统与知识库",
        icon: "⚙",
        items: [
          { path: "/personnel", label: "人员与权限", icon: "♙" },
          { path: "/factories", label: "工厂主数据", icon: "⌂" },
          { path: "/templates", label: "业务模板", icon: "◇" },
          { path: "/workflows", label: "自动化工作流", icon: "⌁" },
          { path: "/mail-settings", label: "邮件发送设置", icon: "✉" },
          { path: "/ai-model-settings", label: "AI模型设置", icon: "✦" },
          { path: "/knowledge", label: "AI知识库", icon: "▧" },
          { path: "/data-sources", label: "数据与API", icon: "⇄" },
        ],
      },
    ],
  }),
};
</script>

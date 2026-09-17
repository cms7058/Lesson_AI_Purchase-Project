import Vue from "vue";
import Router from "vue-router";
import { systemMe } from "../api/client";

Vue.use(Router);

const lazy = (name) => () =>
  import(/* webpackChunkName: "view-[request]" */ `../views/${name}.vue`);

const router = new Router({
  mode: "history",
  routes: [
    {
      path: "/",
      component: lazy("Home"),
      meta: { standalone: true, hideAssistant: true, public: true },
    },
    { path: "/login", component: lazy("Login"), meta: { standalone: true, hideAssistant: true, public: true } },
    { path: "/procurement-dashboard", component: lazy("Dashboard") },
    { path: "/spares", redirect: "/requisitions" },
    { path: "/spare-strategies", component: lazy("SpareStrategies") },
    { path: "/equipment-mro", component: lazy("EquipmentMRO") },
    { path: "/warehouse", component: lazy("WarehouseManagement") },
    {
      path: "/inventory-intelligence",
      component: lazy("InventoryIntelligence"),
    },
    { path: "/projects", component: lazy("Projects") },
    { path: "/project-dashboard", component: lazy("ProjectDashboard") },
    { path: "/project-notifications", component: lazy("ProjectNotifications") },
    { path: "/assistant", component: lazy("Assistant") },
    { path: "/rfqs", component: lazy("Rfqs") },
    { path: "/requisitions", component: lazy("Requisitions") },
    { path: "/orders", component: lazy("Orders") },
    { path: "/fulfillment", component: lazy("Fulfillment") },
    { path: "/settlements", component: lazy("Settlements") },
    { path: "/data-sources", component: lazy("DataSources") },
    { path: "/quotations", redirect: "/rfqs" },
    {
      path: "/supplier",
      component: lazy("SupplierPortal"),
      meta: { supplierPortal: true, standalone: true, public: true },
    },
    { path: "/mail-settings", component: lazy("MailSettings") },
    { path: "/ai-model-settings", component: lazy("AIModelSettings") },
    { path: "/knowledge", component: lazy("KnowledgeBase") },
    { path: "/learning-center", component: lazy("LearningCenter"), meta: { denyRoles: ["student"] } },
    { path: "/learning", component: lazy("LearningCenter"), meta: { standalone: true, hideAssistant: true, public: true } },
    { path: "/training-admin", component: lazy("TrainingAdmin"), meta: { denyRoles: ["student"] } },
    { path: "/supplier-accounts", redirect: "/suppliers" },
    { path: "/templates", component: lazy("Templates") },
    { path: "/workflows", component: lazy("Workflows") },
    { path: "/forecast", component: lazy("Forecasts") },
    { path: "/mro-planning", component: lazy("MroPlanning") },
    { path: "/sourcing", component: lazy("Sourcing") },
    {
      path: "/suppliers",
      component: lazy("MasterData"),
      props: { mode: "suppliers" },
    },
    {
      path: "/factories",
      component: lazy("MasterData"),
      props: { mode: "factories" },
    },
    { path: "/materials", component: lazy("MaterialManagement") },
    { path: "/material-costs", component: lazy("MaterialCosts") },
    { path: "/personnel", component: lazy("Personnel"), meta: { denyRoles: ["student"] } },
    { path: "/routing", component: lazy("Routing") },
    { path: "/contracts", component: lazy("Contracts") },
    { path: "/reports", component: lazy("Reports") },
    { path: "*", redirect: "/" },
  ],
});

router.beforeEach(async (to, from, next) => {
  if (to.meta.public) return next();
  const token = localStorage.getItem("ai-assist-system-token");
  let user = null;
  try { user = JSON.parse(localStorage.getItem("ai-assist-system-user") || "null"); }
  catch (_) { localStorage.removeItem("ai-assist-system-user"); }
  if (!token || !user || !user.role) return next({ path: "/login", query: { redirect: to.fullPath } });
  if (to.meta.denyRoles && to.meta.denyRoles.length) {
    try {
      const verified = await systemMe();
      localStorage.setItem("ai-assist-system-user", JSON.stringify(verified));
      if (to.meta.denyRoles.includes(verified.role)) return next("/procurement-dashboard");
    } catch (_) {
      localStorage.removeItem("ai-assist-system-token");
      localStorage.removeItem("ai-assist-system-user");
      return next({ path: "/login", query: { redirect: to.fullPath } });
    }
  }
  return next();
});

export default router;

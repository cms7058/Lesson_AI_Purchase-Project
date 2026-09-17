import Vue from "vue";
import Router from "vue-router";

Vue.use(Router);

const lazy = (name) => () =>
  import(/* webpackChunkName: "view-[request]" */ `../views/${name}.vue`);

export default new Router({
  mode: "history",
  routes: [
    {
      path: "/",
      component: lazy("Home"),
      meta: { standalone: true, hideAssistant: true },
    },
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
      meta: { supplierPortal: true, standalone: true },
    },
    { path: "/mail-settings", component: lazy("MailSettings") },
    { path: "/ai-model-settings", component: lazy("AIModelSettings") },
    { path: "/knowledge", component: lazy("KnowledgeBase") },
    { path: "/learning-center", component: lazy("LearningCenter") },
    { path: "/learning", component: lazy("LearningCenter"), meta: { standalone: true, hideAssistant: true } },
    { path: "/training-admin", component: lazy("TrainingAdmin") },
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
    { path: "/personnel", component: lazy("Personnel") },
    { path: "/routing", component: lazy("Routing") },
    { path: "/contracts", component: lazy("Contracts") },
    { path: "/reports", component: lazy("Reports") },
    { path: "*", redirect: "/" },
  ],
});

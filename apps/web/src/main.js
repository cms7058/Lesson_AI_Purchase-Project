import Vue from "vue";
import ContractFieldManager from "./components/ContractFieldManager.vue";
import ContractDynamicFields from "./components/ContractDynamicFields.vue";
import ElementUI from "element-ui";
import "element-ui/lib/theme-chalk/index.css";

import App from "./App.vue";
import router from "./router";
import store from "./store";
import "./styles/main.css";

Vue.config.productionTip = false;
Vue.component("contract-field-manager", ContractFieldManager);
Vue.component("contract-dynamic-fields", ContractDynamicFields);
Vue.use(ElementUI);

new Vue({ router, store, render: (h) => h(App) }).$mount("#app");

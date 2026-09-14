import Vue from "vue";
import Vuex from "vuex";
import { api } from "../api/client";

Vue.use(Vuex);

export default new Vuex.Store({
  state: { user: { name: "采购经理", organization: "示例制造集团", role: null } },
  mutations: { setIdentity(state, identity) { state.user = {...state.user, ...identity, name: {admin:"系统管理员",procurement_manager:"采购经理",buyer:"采购员",analyst:"分析员",auditor:"审计员"}[identity.role] || "用户"}; } },
  actions: { async loadIdentity({commit}) { try { commit("setIdentity", (await api.get("/identity")).data); } catch (_) { commit("setIdentity", {role:null}); } } },
  modules: {}
});

import Vue from "vue";
import Vuex from "vuex";
import { systemLogin, systemLogout, systemMe } from "../api/client";

Vue.use(Vuex);

const savedUser = () => {
  try { return JSON.parse(localStorage.getItem("ai-assist-system-user") || "null"); }
  catch (_) { localStorage.removeItem("ai-assist-system-user"); return null; }
};

export default new Vuex.Store({
  state: { user: savedUser() || { name: "", organization: "AI助力教学平台", role: null } },
  mutations: {
    setIdentity(state, identity) { state.user = { organization: "AI助力教学平台", ...identity }; if (identity && identity.role) localStorage.setItem("ai-assist-system-user", JSON.stringify(state.user)); },
    clearIdentity(state) { state.user = { name: "", organization: "AI助力教学平台", role: null }; localStorage.removeItem("ai-assist-system-user"); },
  },
  actions: {
    async login({ commit }, credentials) { const result = await systemLogin(credentials); localStorage.setItem("ai-assist-system-token", result.token); commit("setIdentity", result.user); return result.user; },
    async loadIdentity({ commit }) { try { commit("setIdentity", await systemMe()); } catch (error) { localStorage.removeItem("ai-assist-system-token"); commit("clearIdentity"); throw error; } },
    async logout({ commit }) { try { await systemLogout(); } catch (_) { /* 本地退出不依赖服务端会话 */ } localStorage.removeItem("ai-assist-system-token"); commit("clearIdentity"); },
  },
  modules: {}
});

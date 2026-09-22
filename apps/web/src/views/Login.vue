<template>
  <main class="system-login-page">
    <section class="system-login-copy">
      <BrandMark/><p>AI ASSISTED LEARNING PLATFORM</p>
      <h1>AI助力<br><em>智能项目与采购教学平台</em></h1>
      <span>项目管理 · 智能采购 · MRO备件 · 在线实训</span>
      <div class="login-flow"><b>业务场景</b><i>→</i><b>数据分析</b><i>→</i><b>AI辅助决策</b></div>
    </section>
    <el-card class="system-login-card" shadow="never">
      <div class="login-heading"><span>SYSTEM LOGIN</span><h2>登录系统</h2><p>管理员和已启用的学员账号均可登录。</p></div>
      <el-form ref="form" :model="form" :rules="rules" @keyup.enter.native="submit">
        <el-form-item prop="username"><el-input v-model.trim="form.username" prefix-icon="el-icon-user" placeholder="用户名" autocomplete="username"/></el-form-item>
        <el-form-item prop="password"><el-input v-model="form.password" type="password" show-password prefix-icon="el-icon-lock" placeholder="密码" autocomplete="current-password"/></el-form-item>
        <el-button type="primary" class="login-button" :loading="loading" @click="submit">登录</el-button>
      </el-form>
      <div class="system-login-links"><router-link to="/">返回首页</router-link><router-link to="/learning">进入学员学习中心</router-link></div>
    </el-card>
  </main>
</template>

<script>
import BrandMark from "../components/BrandMark.vue";
export default {
  components: { BrandMark },
  data: () => ({ loading: false, form: { username: "", password: "" }, rules: { username: [{ required: true, message: "请输入用户名", trigger: "blur" }], password: [{ required: true, message: "请输入密码", trigger: "blur" }] } }),
  created() { if (localStorage.getItem("ai-assist-system-token")) this.$router.replace("/procurement-dashboard"); },
  methods: {
    submit() { this.$refs.form.validate(async valid => { if (!valid) return; this.loading = true; try { const user = await this.$store.dispatch("login", this.form); const target = this.$route.query.redirect || "/procurement-dashboard"; this.$message.success(`${user.name}，登录成功`); this.$router.replace(user.role === "student" && ["/personnel", "/learning-center", "/training-admin"].includes(target) ? "/procurement-dashboard" : target); } catch (e) { const detail = e.response && e.response.data && e.response.data.detail; this.$message.error(detail || "登录失败"); } finally { this.loading = false; } }); },
  },
};
</script>

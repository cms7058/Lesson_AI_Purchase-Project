<template>
  <div :class="['learning-center', { standalone: $route.meta.standalone }]">
    <div v-if="$route.meta.standalone" class="learning-brand"><BrandMark/><div><strong>AI助力 · 学员学习中心</strong><small>在线考试与课程资料</small></div><router-link to="/">返回首页</router-link></div>
    <el-card v-if="!token" class="learning-login" shadow="never">
      <div class="login-heading"><span>LEARNING PORTAL</span><h1>学员登录</h1><p>使用管理员在“系统人员管理”中分配的学习账号登录。</p></div>
      <el-form ref="login" :model="login" :rules="loginRules" @keyup.enter.native="doLogin">
        <el-form-item prop="username"><el-input v-model.trim="login.username" prefix-icon="el-icon-user" placeholder="学习账号" autocomplete="username"/></el-form-item>
        <el-form-item prop="password"><el-input v-model="login.password" type="password" show-password prefix-icon="el-icon-lock" placeholder="密码" autocomplete="current-password"/></el-form-item>
        <el-button type="primary" :loading="loading" class="login-button" @click="doLogin">登录学习中心</el-button>
      </el-form>
    </el-card>

    <template v-else>
      <div class="learning-head"><div><p class="eyebrow">学员在线学习空间</p><h1>{{ user.name }}，欢迎学习</h1><p>{{ user.department || '培训学员' }} · 试卷由系统计时、自动评分并提供逐题解析。</p></div><div class="learning-actions"><el-tag type="success">账号 {{ user.username }}</el-tag><el-button @click="logout">退出登录</el-button></div></div>
      <el-tabs v-model="active" type="card" @tab-click="changeTab"><el-tab-pane label="在线考试" name="exam"/><el-tab-pane label="课件与授课文件" name="materials"/><el-tab-pane label="我的考试记录" name="history"/></el-tabs>

      <template v-if="active==='exam'">
        <div v-if="!attempt && !result" class="exam-intro">
          <div><span class="exam-icon">✓</span><h2>{{ exam.title || '学员测试试卷' }}</h2><p>共 {{ exam.question_count || 20 }} 题，满分 {{ exam.total_score || 100 }} 分；单选15题、多选5题。</p></div>
          <div class="exam-rules"><div><strong>{{ exam.duration_minutes || 45 }}</strong><span>分钟限时</span></div><div><strong>自动</strong><span>交卷评分</span></div><div><strong>逐题</strong><span>答案解析</span></div></div>
          <el-alert title="开始后由服务器记录截止时间。倒计时结束将自动提交当前答案；多选题少选、多选或错选均不得分。" type="warning" :closable="false" show-icon/>
          <div class="exam-intro-actions"><el-button @click="downloadPaper">下载空白试卷</el-button><el-button type="primary" :loading="loading" @click="startExam">开始答题</el-button></div>
        </div>

        <div v-if="attempt && !result" class="exam-layout">
          <aside class="exam-nav"><div class="timer" :class="{ urgent: remainingSeconds <= 300 }"><small>剩余时间</small><strong>{{ timerText }}</strong><span>{{ answeredCount }}/{{ exam.questions.length }} 已答</span></div><div class="question-map"><button v-for="q in exam.questions" :key="q.number" :class="{ answered: hasAnswer(q.number) }" @click="scrollToQuestion(q.number)">{{ q.number }}</button></div><el-button type="primary" :loading="submitting" @click="confirmSubmit">提交试卷</el-button></aside>
          <main class="question-list">
            <section v-for="q in exam.questions" :id="`exam-question-${q.number}`" :key="q.number" class="question-card">
              <div class="question-title"><span>{{ q.number }}</span><div><el-tag size="mini" :type="q.type==='multi'?'warning':''">{{ q.type==='multi'?'多选':'单选' }} · {{ q.points }}分</el-tag><strong>{{ q.text }}</strong></div></div>
              <el-checkbox-group v-if="q.type==='multi'" v-model="answers[String(q.number)]" class="answer-options" @change="persistAnswers"><el-checkbox v-for="option in q.options" :key="option.key" :label="option.key"><b>{{ option.key }}.</b> {{ option.text }}</el-checkbox></el-checkbox-group>
              <el-radio-group v-else v-model="answers[String(q.number)]" class="answer-options" @change="persistAnswers"><el-radio v-for="option in q.options" :key="option.key" :label="option.key"><b>{{ option.key }}.</b> {{ option.text }}</el-radio></el-radio-group>
            </section>
          </main>
        </div>

        <div v-if="result" class="exam-result">
          <div class="score-ring"><strong>{{ result.score }}</strong><span>得分</span></div><div class="result-summary"><p class="eyebrow">交卷完成</p><h2>{{ result.score >= 60 ? '考试通过' : '继续学习，再接再厉' }}</h2><p>答对 {{ result.correct_count }}/20 题<span v-if="result.timed_out"> · 已超时自动交卷</span></p><div><el-button @click="downloadPaper">下载试卷</el-button><el-button type="primary" @click="downloadAnalysis">下载答题解析</el-button><el-button @click="restart">再考一次</el-button></div></div>
          <el-table :data="result.review" stripe border class="review-table"><el-table-column prop="number" label="题号" width="65"/><el-table-column label="结果" width="80"><template slot-scope="s"><el-tag :type="s.row.correct?'success':'danger'">{{ s.row.correct?'正确':'错误' }}</el-tag></template></el-table-column><el-table-column label="作答/答案" width="125"><template slot-scope="s">{{ s.row.user_answer || '未答' }} / {{ s.row.answer }}</template></el-table-column><el-table-column prop="question" label="题目" min-width="260"/><el-table-column prop="explanation" label="解析" min-width="280"/></el-table>
        </div>
      </template>

      <template v-if="active==='materials'">
        <div class="material-grid" v-loading="loading"><el-card v-for="item in materials" :key="item.id" shadow="hover" class="material-card"><div class="material-cover"><span>PDF</span><el-tag size="mini">{{ categoryName(item.category) }}</el-tag></div><h3>{{ item.title }}</h3><p>{{ item.description || '课程配套PDF资料' }}</p><small>{{ item.original_filename }} · {{ fileSize(item.file_size) }}</small><div><el-button type="text" icon="el-icon-view" @click="previewMaterial(item)">在线查看</el-button><el-button type="text" icon="el-icon-download" @click="downloadMaterial(item)">下载</el-button></div></el-card><el-empty v-if="!loading && !materials.length" description="讲师尚未发布课件或授课文件"/></div>
      </template>

      <template v-if="active==='history'">
        <el-table v-loading="loading" :data="history" class="data-table" empty-text="暂无考试记录"><el-table-column prop="paper_title" label="试卷" min-width="250"/><el-table-column label="状态" width="100"><template slot-scope="s"><el-tag :type="s.row.status==='submitted'?'success':'warning'">{{ s.row.status==='submitted'?'已交卷':'答题中' }}</el-tag></template></el-table-column><el-table-column label="得分" width="90"><template slot-scope="s"><strong>{{ s.row.score == null ? '—' : s.row.score }}</strong></template></el-table-column><el-table-column label="答对" width="100"><template slot-scope="s">{{ s.row.correct_count == null ? '—' : `${s.row.correct_count}/20` }}</template></el-table-column><el-table-column label="开始时间" min-width="170"><template slot-scope="s">{{ formatTime(s.row.started_at) }}</template></el-table-column><el-table-column label="交卷时间" min-width="170"><template slot-scope="s">{{ formatTime(s.row.submitted_at) }}</template></el-table-column><el-table-column label="解析" width="100"><template slot-scope="s"><el-button v-if="s.row.status==='submitted'" type="text" @click="downloadAnalysis(s.row.id)">下载</el-button></template></el-table-column></el-table>
      </template>
    </template>
    <el-dialog :title="previewTitle" :visible.sync="previewVisible" width="90%" top="3vh" @closed="releasePreview"><iframe v-if="previewUrl" :src="previewUrl" class="pdf-preview" title="PDF在线预览"/></el-dialog>
  </div>
</template>

<script>
import BrandMark from "../components/BrandMark.vue";
import { fetchLearnerMaterials, fetchLearningAttempts, fetchLearningBlob, fetchLearningExam, learningLogin, learningLogout, startLearningExam, submitLearningExam } from "../api/client";

const TOKEN_KEY = "ai-assist-learning-token";
const USER_KEY = "ai-assist-learning-user";

export default {
  components: { BrandMark },
  data: () => ({ token: localStorage.getItem(TOKEN_KEY) || "", user: JSON.parse(localStorage.getItem(USER_KEY) || "{}"), login: { username: "", password: "" }, loginRules: { username: [{ required: true, message: "请输入学习账号", trigger: "blur" }], password: [{ required: true, message: "请输入密码", trigger: "blur" }] }, active: "exam", exam: { questions: [] }, attempt: null, result: null, answers: {}, remainingSeconds: 0, timer: null, submitting: false, loading: false, materials: [], history: [], previewVisible: false, previewUrl: "", previewTitle: "" }),
  computed: { timerText() { const seconds = Math.max(0, this.remainingSeconds); return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`; }, answeredCount() { return this.exam.questions.filter(q => this.hasAnswer(q.number)).length; } },
  created() { if (this.token) this.initialize(); },
  beforeDestroy() { this.stopTimer(); this.releasePreview(); },
  methods: {
    error(e, fallback) { const d = e.response && e.response.data && e.response.data.detail; this.$message.error(d || fallback); if (e.response && e.response.status === 401) this.clearSession(); },
    doLogin() { this.$refs.login.validate(async valid => { if (!valid) return; this.loading = true; try { const r = await learningLogin(this.login); this.token = r.token; this.user = r.user; localStorage.setItem(TOKEN_KEY, r.token); localStorage.setItem(USER_KEY, JSON.stringify(r.user)); this.login.password = ""; await this.initialize(); this.$message.success("登录成功"); } catch (e) { this.error(e, "登录失败"); } finally { this.loading = false; } }); },
    async initialize() { try { this.exam = await fetchLearningExam(this.token); } catch (e) { this.error(e, "学习中心加载失败"); } },
    async logout() { try { await learningLogout(this.token); } catch (_) { /* 会话已失效时仍允许本地退出 */ } this.clearSession(); },
    clearSession() { this.stopTimer(); this.token = ""; this.user = {}; this.attempt = null; this.result = null; localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
    changeTab() { if (this.active === "materials") this.loadMaterials(); if (this.active === "history") this.loadHistory(); },
    async startExam() { this.loading = true; try { this.attempt = await startLearningExam(this.token); const saved = localStorage.getItem(`exam-answers-${this.attempt.id}`); this.answers = saved ? JSON.parse(saved) : {}; this.exam.questions.forEach(q => { if (!(String(q.number) in this.answers)) this.$set(this.answers, String(q.number), q.type === "multi" ? [] : ""); }); const server = new Date(this.attempt.server_time).getTime(); const end = new Date(this.attempt.expires_at).getTime(); this.remainingSeconds = Math.max(0, Math.floor((end - server) / 1000)); this.startTimer(); } catch (e) { this.error(e, "考试启动失败"); } finally { this.loading = false; } },
    startTimer() { this.stopTimer(); this.timer = window.setInterval(() => { this.remainingSeconds -= 1; if (this.remainingSeconds <= 0) { this.remainingSeconds = 0; this.stopTimer(); this.submit(false); } }, 1000); },
    stopTimer() { if (this.timer) window.clearInterval(this.timer); this.timer = null; },
    persistAnswers() { if (this.attempt) localStorage.setItem(`exam-answers-${this.attempt.id}`, JSON.stringify(this.answers)); },
    hasAnswer(number) { const value = this.answers[String(number)]; return Array.isArray(value) ? value.length > 0 : !!value; },
    scrollToQuestion(number) { const node = document.getElementById(`exam-question-${number}`); if (node) node.scrollIntoView({ behavior: "smooth", block: "start" }); },
    async confirmSubmit() { try { await this.$confirm(`已完成 ${this.answeredCount}/20 题，提交后不能修改，确定交卷吗？`, "提交试卷", { type: "warning" }); this.submit(true); } catch (_) { /* 用户取消 */ } },
    async submit(manual) { if (!this.attempt || this.submitting) return; this.submitting = true; try { const result = await submitLearningExam(this.token, this.attempt.id, this.answers); localStorage.removeItem(`exam-answers-${this.attempt.id}`); this.stopTimer(); this.result = result; this.attempt = null; this.$message.success(manual ? `交卷成功，得分 ${result.score}` : `考试时间已到，系统已自动交卷，得分 ${result.score}`); } catch (e) { this.error(e, "交卷失败，请重试"); } finally { this.submitting = false; } },
    restart() { this.result = null; this.answers = {}; },
    async loadMaterials() { this.loading = true; try { this.materials = await fetchLearnerMaterials(this.token); } catch (e) { this.error(e, "课件加载失败"); } finally { this.loading = false; } },
    async loadHistory() { this.loading = true; try { this.history = await fetchLearningAttempts(this.token); } catch (e) { this.error(e, "考试记录加载失败"); } finally { this.loading = false; } },
    async fetchAndDownload(path, filename) { try { const blob = await fetchLearningBlob(this.token, path); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url); } catch (e) { this.error(e, "文件下载失败"); } },
    downloadPaper() { this.fetchAndDownload("/learning/exam/paper.pdf", "AI赋能项目采购与备件管理_测试试卷.pdf"); },
    downloadAnalysis(attemptId) { const id = attemptId || (this.result && this.result.id); if (id) this.fetchAndDownload(`/learning/exam/${id}/analysis.pdf`, `答题解析_${this.user.name || '学员'}.pdf`); },
    async previewMaterial(item) { try { const blob = await fetchLearningBlob(this.token, `/learning/materials/${item.id}/file`); this.releasePreview(); this.previewUrl = URL.createObjectURL(blob); this.previewTitle = item.title; this.previewVisible = true; } catch (e) { this.error(e, "PDF在线查看失败"); } },
    downloadMaterial(item) { this.fetchAndDownload(`/learning/materials/${item.id}/file?download=true`, item.original_filename); },
    releasePreview() { if (this.previewUrl) URL.revokeObjectURL(this.previewUrl); this.previewUrl = ""; },
    categoryName(value) { return ({ courseware: "课程课件", teaching: "授课文件", case: "实训案例", reference: "参考资料" }[value] || value); },
    fileSize(value) { return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`; },
    formatTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—"; },
  },
};
</script>

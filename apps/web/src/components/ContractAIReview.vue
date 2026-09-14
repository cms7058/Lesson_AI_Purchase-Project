<template>
  <div class="contract-review" v-loading="loading">
    <div class="review-intro">
      <div><p class="eyebrow">AI CONTRACT CONTROL</p><h3>{{ contract.contract_no }} · {{ contract.title }}</h3><p>{{ contract.supplier_name }} · {{ contract.currency }} {{ money(contract.amount) }}</p></div>
      <el-tag :type="contract.status==='draft'?'info':'success'">{{ statusName(contract.status) }}</el-tag>
    </div>
    <el-alert title="先检查关键条款与主数据，再由已配置大模型补充语义观察；AI不替代采购、法务和授权审批。" type="info" :closable="false" show-icon/>

    <section class="review-section">
      <div class="section-title"><div><h4>合同文件与版本</h4><span>支持 UTF-8 TXT、DOCX、可检索文本 PDF，单文件不超过 10MB</span></div><div v-if="contract.status==='draft'" class="upload-row"><input ref="file" type="file" accept=".txt,.docx,.pdf" @change="selectFile"><el-button size="small" :disabled="!selectedFile" :loading="uploading" @click="upload">上传新版本</el-button></div></div>
      <el-table :data="workspace.documents" size="small" empty-text="尚未上传合同正文">
        <el-table-column label="版本" width="70"><template slot-scope="scope">V{{ scope.row.version }}</template></el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="190" show-overflow-tooltip/>
        <el-table-column prop="extraction_mode" label="解析方式" width="105"/>
        <el-table-column label="正文字符" width="95"><template slot-scope="scope">{{ scope.row.text_length.toLocaleString() }}</template></el-table-column>
        <el-table-column label="审查状态" width="95"><template slot-scope="scope"><el-tag size="mini" :type="scope.row.reviewed?'success':'warning'">{{ scope.row.reviewed?'已审查':'待审查' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="170"><template slot-scope="scope"><el-button type="text" @click="download(scope.row)">下载原件</el-button><el-button v-if="contract.status==='draft'&&!scope.row.reviewed" type="text" class="danger-link" @click="removeDocument(scope.row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="review-actions"><span v-if="workspace.documents.length">默认审查最新版本 V{{ workspace.documents[0].version }}</span><el-button type="primary" :disabled="!workspace.documents.length" :loading="reviewing" @click="runReview">执行 AI 审查</el-button></div>
    </section>

    <template v-if="workspace.latest_review">
      <el-alert v-if="!workspace.current_document_reviewed" title="最新文件尚未审查，下方结果属于历史版本，请重新执行AI审查。" type="warning" :closable="false" show-icon/>
      <div class="score-grid">
        <div><span>风险评分</span><strong :class="workspace.latest_review.risk_level">{{ workspace.latest_review.risk_score }}</strong><small>/ 100</small></div>
        <div><span>关键条款</span><strong>{{ result.statistics.clause_found }}/{{ result.statistics.clause_total }}</strong><small> 已识别</small></div>
        <div><span>高风险</span><strong class="high">{{ result.statistics.high }}</strong><small> 项</small></div>
        <div><span>审查引擎</span><strong class="engine">{{ workspace.latest_review.engine==='rules+llm'?'规则 + 大模型':'确定性规则' }}</strong><small> V{{ workspace.latest_review.document_version }}</small></div>
      </div>
      <section class="review-section">
        <div class="section-title"><div><h4>关键条款覆盖</h4><span>{{ result.summary }}</span></div></div>
        <el-table :data="result.clauses" size="small" max-height="340">
          <el-table-column prop="name" label="条款" width="150"/><el-table-column label="状态" width="85"><template slot-scope="scope"><el-tag size="mini" :type="scope.row.status==='found'?'success':'danger'">{{ scope.row.status==='found'?'已识别':'缺失' }}</el-tag></template></el-table-column><el-table-column prop="evidence" label="原文证据" min-width="260" show-overflow-tooltip><template slot-scope="scope">{{ scope.row.evidence||'未发现对应证据' }}</template></el-table-column><el-table-column prop="recommendation" label="整改建议" min-width="260" show-overflow-tooltip/>
        </el-table>
      </section>
      <section class="review-section">
        <div class="section-title"><div><h4>风险事项与整改建议</h4><span>{{ result.ai_note }}</span></div></div>
        <el-table :data="result.risks" size="small" max-height="360" empty-text="未识别到风险事项">
          <el-table-column prop="title" label="风险点" width="190"/><el-table-column label="等级" width="75"><template slot-scope="scope"><el-tag size="mini" :type="riskType(scope.row.severity)">{{ severityName(scope.row.severity) }}</el-tag></template></el-table-column><el-table-column prop="source" label="来源" width="90"><template slot-scope="scope">{{ sourceName(scope.row.source) }}</template></el-table-column><el-table-column prop="evidence" label="证据" min-width="230" show-overflow-tooltip/><el-table-column prop="recommendation" label="建议" min-width="260" show-overflow-tooltip/>
        </el-table>
        <p class="disclaimer">{{ result.disclaimer }}</p>
      </section>
    </template>
    <el-empty v-else description="上传合同文件并执行AI审查后，将显示条款覆盖、风险证据和整改建议" :image-size="80"/>

    <section class="review-section history-section">
      <div class="section-title"><div><h4>审查版本历史</h4><span>每次审查独立留痕，可回看当时的风险结论</span></div><el-button size="small" @click="loadHistory">刷新历史</el-button></div>
      <el-table :data="history.items" size="small" empty-text="暂无审查历史"><el-table-column label="文档版本" width="95"><template slot-scope="scope">V{{ scope.row.document_version }}</template></el-table-column><el-table-column prop="created_at" label="审查时间" min-width="170"><template slot-scope="scope">{{ formatTime(scope.row.created_at) }}</template></el-table-column><el-table-column label="风险" width="90"><template slot-scope="scope"><el-tag size="mini" :type="riskType(scope.row.risk_level)">{{ severityName(scope.row.risk_level) }}</el-tag></template></el-table-column><el-table-column prop="risk_score" label="评分" width="75"/><el-table-column prop="created_by" label="操作人" min-width="120"/></el-table>
    </section>
  </div>
</template>

<script>
import { api } from "../api/client";

export default {
  props: { contract: { type: Object, required: true } },
  data: () => ({ loading: false, uploading: false, reviewing: false, selectedFile: null, workspace: { documents: [], latest_review: null, current_document_reviewed: false }, history: { items: [], total: 0 } }),
  computed: { result() { return this.workspace.latest_review ? this.workspace.latest_review.result : { statistics: {}, clauses: [], risks: [] }; } },
  created() { this.load(); },
  methods: {
    money(value) { return Number(value || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
    statusName(value) { return { draft: "草稿", pending_approval: "待审批", active: "履约中", expired: "已到期", terminated: "已终止" }[value] || value; },
    riskType(value) { return { high: "danger", medium: "warning", low: "success" }[value] || "info"; },
    severityName(value) { return { high: "高", medium: "中", low: "低" }[value] || value; },
    sourceName(value) { return { rule: "规则", master_data: "主数据", llm: "大模型" }[value] || value; },
    formatTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-"; },
    async load() { this.loading = true; try { const [workspace, history] = await Promise.all([api.get(`/contracts/${this.contract.id}/review-workspace`), api.get(`/contracts/${this.contract.id}/ai-reviews`, { params: { page: 1, page_size: 20 } })]); this.workspace = workspace.data; this.history = history.data; } catch (error) { this.$message.error(error.response?.data?.detail || "合同审查工作区加载失败"); } finally { this.loading = false; } },
    loadHistory() { return this.load(); },
    selectFile(event) { this.selectedFile = event.target.files && event.target.files[0] || null; },
    async upload() { if (!this.selectedFile) return; this.uploading = true; try { const form = new FormData(); form.append("file", this.selectedFile); await api.post(`/contracts/${this.contract.id}/documents`, form, { headers: { "Content-Type": "multipart/form-data" } }); this.$message.success("合同新版本已上传并完成文本解析"); this.selectedFile = null; this.$refs.file.value = ""; await this.load(); } catch (error) { this.$message.error(error.response?.data?.detail || "合同上传失败"); } finally { this.uploading = false; } },
    async runReview() { this.reviewing = true; try { await api.post(`/contracts/${this.contract.id}/ai-review`, {}); this.$message.success("AI审查完成，已保存风险证据与整改建议"); await this.load(); this.$emit("reviewed"); } catch (error) { this.$message.error(error.response?.data?.detail || "AI审查失败"); } finally { this.reviewing = false; } },
    download(row) { window.open(`${api.defaults.baseURL}/contract-documents/${row.id}/download`, "_blank", "noopener"); },
    async removeDocument(row) { try { await this.$confirm(`删除合同 V${row.version} 文件吗？`, "删除确认", { type: "warning" }); await api.delete(`/contract-documents/${row.id}`); this.$message.success("未审查版本已删除"); await this.load(); } catch (error) { if (error !== "cancel") this.$message.error(error.response?.data?.detail || "文件删除失败"); } }
  }
};
</script>

<style scoped>
.contract-review{color:#26354a}.review-intro,.section-title,.review-actions{display:flex;align-items:center;justify-content:space-between;gap:16px}.review-intro{padding:0 0 16px}.review-intro h3,.section-title h4{margin:0 0 4px}.review-intro p,.section-title span{margin:0;color:#7a8798;font-size:13px}.eyebrow{color:#2f6bff!important;font-size:11px!important;letter-spacing:1.2px}.review-section{margin-top:18px;padding:16px;border:1px solid #e7ecf3;border-radius:10px;background:#fff}.section-title{margin-bottom:12px}.upload-row{display:flex;align-items:center;gap:8px}.upload-row input{width:220px;font-size:12px}.review-actions{justify-content:flex-end;margin-top:12px;color:#7a8798;font-size:13px}.score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px}.score-grid>div{padding:15px;border:1px solid #e7ecf3;border-radius:10px;background:#f8fafc}.score-grid span{display:block;color:#718096;font-size:12px;margin-bottom:8px}.score-grid strong{font-size:25px;color:#24415f}.score-grid strong.high{color:#d64545}.score-grid strong.medium{color:#e59a20}.score-grid strong.low{color:#20a56a}.score-grid strong.engine{font-size:16px}.score-grid small{color:#8b97a8;margin-left:3px}.disclaimer{margin:12px 0 0;color:#9a6b25;font-size:12px;line-height:1.6}.history-section{margin-bottom:4px}.danger-link{color:#f56c6c}@media(max-width:1000px){.score-grid{grid-template-columns:repeat(2,1fr)}.section-title{align-items:flex-start;flex-direction:column}.upload-row{width:100%}}
</style>

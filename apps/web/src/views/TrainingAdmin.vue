<template>
  <div>
    <div class="page-heading"><div><p class="eyebrow">课件、授课文件与考试记录</p><h1>教学资料管理</h1><p>上传PDF课件和授课文件，控制学员可见状态，并查看在线考试成绩。</p></div><el-button v-if="active==='materials'" type="primary" icon="el-icon-upload2" @click="openUpload">上传PDF资料</el-button></div>
    <div class="process-strip"><span>讲师上传PDF</span><i>→</i><span>发布给学员</span><i>→</i><span>学员在线预览或下载</span><i>→</i><span>考试提交后自动评分与解析</span></div>
    <el-tabs v-model="active" type="card" @tab-click="load"><el-tab-pane label="课件与授课文件" name="materials"/><el-tab-pane label="考试记录" name="attempts"/></el-tabs>

    <template v-if="active==='materials'">
      <div class="table-toolbar"><el-input v-model.trim="keyword" clearable placeholder="搜索资料标题或文件名" @keyup.enter.native="search" @clear="search"/><el-select v-model="category" clearable placeholder="全部分类" @change="search"><el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value"/></el-select><el-select v-model="status" clearable placeholder="全部状态" @change="search"><el-option label="已发布" value="active"/><el-option label="已归档" value="archived"/></el-select><el-button icon="el-icon-search" @click="search">查询</el-button></div>
      <el-table v-loading="loading" :data="items" class="data-table" empty-text="暂无PDF教学资料">
        <el-table-column prop="title" label="资料标题" min-width="220"/><el-table-column label="分类" width="110"><template slot-scope="s"><el-tag>{{ categoryName(s.row.category) }}</el-tag></template></el-table-column><el-table-column prop="original_filename" label="PDF文件" min-width="220" show-overflow-tooltip/><el-table-column label="大小" width="100"><template slot-scope="s">{{ fileSize(s.row.file_size) }}</template></el-table-column><el-table-column label="状态" width="90"><template slot-scope="s"><el-tag :type="s.row.status==='active'?'success':'info'">{{ s.row.status==='active'?'已发布':'已归档' }}</el-tag></template></el-table-column><el-table-column label="上传时间" width="165"><template slot-scope="s">{{ formatTime(s.row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="250" fixed="right"><template slot-scope="s"><el-button type="text" @click="preview(s.row)">在线查看</el-button><el-button type="text" @click="download(s.row)">下载</el-button><el-button type="text" @click="toggleStatus(s.row)">{{ s.row.status==='active'?'归档':'发布' }}</el-button><el-button type="text" class="danger-link" @click="remove(s.row)">删除</el-button></template></el-table-column>
      </el-table>
    </template>
    <template v-else>
      <el-alert title="考试以服务器时间计时；交卷后自动保存得分、答对题数和是否超时。" type="info" :closable="false" show-icon/>
      <el-table v-loading="loading" :data="items" class="data-table" empty-text="暂无考试记录">
        <el-table-column prop="student_name" label="学员" min-width="140"/><el-table-column prop="paper_title" label="试卷" min-width="240"/><el-table-column label="状态" width="100"><template slot-scope="s"><el-tag :type="s.row.status==='submitted'?'success':s.row.status==='in_progress'?'warning':'info'">{{ statusName(s.row.status) }}</el-tag></template></el-table-column><el-table-column label="得分" width="90"><template slot-scope="s"><strong>{{ s.row.score == null ? '—' : s.row.score }}</strong></template></el-table-column><el-table-column label="答对" width="90"><template slot-scope="s">{{ s.row.correct_count == null ? '—' : `${s.row.correct_count}/20` }}</template></el-table-column><el-table-column label="计时" width="90"><template slot-scope="s"><el-tag v-if="s.row.timed_out" type="danger">超时</el-tag><span v-else>正常</span></template></el-table-column><el-table-column label="开始时间" min-width="165"><template slot-scope="s">{{ formatTime(s.row.started_at) }}</template></el-table-column><el-table-column label="交卷时间" min-width="165"><template slot-scope="s">{{ formatTime(s.row.submitted_at) }}</template></el-table-column>
      </el-table>
    </template>
    <div class="pagination-row"><span>共 {{ pagination.total }} 条</span><el-pagination background layout="sizes, prev, pager, next" :page-sizes="[10,20,50]" :current-page="pagination.page" :page-size="pagination.page_size" :total="pagination.total" @current-change="changePage" @size-change="changeSize"/></div>

    <el-dialog title="上传PDF课件或授课文件" :visible.sync="uploadVisible" width="620px" :close-on-click-modal="false"><el-form ref="uploadForm" :model="upload" :rules="rules" label-width="95px"><el-form-item label="资料标题" prop="title"><el-input v-model.trim="upload.title"/></el-form-item><el-form-item label="资料分类" prop="category"><el-select v-model="upload.category" style="width:100%"><el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value"/></el-select></el-form-item><el-form-item label="资料说明"><el-input v-model="upload.description" type="textarea" :rows="3" maxlength="1000" show-word-limit/></el-form-item><el-form-item label="PDF文件" prop="file"><input ref="file" type="file" accept="application/pdf,.pdf" @change="pickFile"/><p class="tip">仅支持PDF，最大80MB；发布后学员可在线查看和下载。</p></el-form-item></el-form><span slot="footer"><el-button @click="uploadVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="uploadFile">上传并发布</el-button></span></el-dialog>
    <el-dialog :title="previewTitle" :visible.sync="previewVisible" width="88%" top="4vh" @closed="releasePreview"><iframe v-if="previewUrl" :src="previewUrl" class="pdf-preview" title="PDF在线预览"/></el-dialog>
  </div>
</template>

<script>
import { deleteTrainingMaterial, fetchExamAttempts, fetchManagerBlob, fetchTrainingMaterials, updateTrainingMaterial, uploadTrainingMaterial } from "../api/client";

const uploadBlank = () => ({ title: "", category: "courseware", description: "", file: null });

export default {
  data: () => ({ active: "materials", keyword: "", category: "", status: "", items: [], loading: false, saving: false, uploadVisible: false, previewVisible: false, previewUrl: "", previewTitle: "", upload: uploadBlank(), pagination: { page: 1, page_size: 10, total: 0 }, categories: [{ value: "courseware", label: "课程课件" }, { value: "teaching", label: "授课文件" }, { value: "case", label: "实训案例" }, { value: "reference", label: "参考资料" }], rules: { title: [{ required: true, message: "请输入资料标题", trigger: "blur" }], category: [{ required: true, message: "请选择资料分类", trigger: "change" }], file: [{ required: true, message: "请选择PDF文件", trigger: "change" }] } }),
  created() { this.load(); },
  beforeDestroy() { this.releasePreview(); },
  methods: {
    error(e, fallback) { const d = e.response && e.response.data && e.response.data.detail; this.$message.error((Array.isArray(d) ? d.map(x => x.msg).join("；") : d) || e.message || fallback); },
    categoryName(value) { const item = this.categories.find(x => x.value === value); return item ? item.label : value; },
    statusName(value) { return ({ submitted: "已交卷", in_progress: "答题中", expired: "已超时" }[value] || value); },
    formatTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—"; },
    fileSize(value) { return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`; },
    async load() { this.loading = true; try { const params = { page: this.pagination.page, page_size: this.pagination.page_size }; const r = this.active === "materials" ? await fetchTrainingMaterials({ ...params, keyword: this.keyword, category: this.category, status: this.status }) : await fetchExamAttempts(params); this.items = r.items; this.pagination.total = r.total; } catch (e) { this.error(e, "教学数据加载失败"); } finally { this.loading = false; } },
    search() { this.pagination.page = 1; this.load(); }, changePage(page) { this.pagination.page = page; this.load(); }, changeSize(size) { this.pagination.page_size = size; this.pagination.page = 1; this.load(); },
    openUpload() { this.upload = uploadBlank(); this.uploadVisible = true; this.$nextTick(() => { if (this.$refs.file) this.$refs.file.value = ""; }); },
    pickFile(event) { const file = event.target.files[0] || null; if (file && !file.name.toLowerCase().endsWith(".pdf")) { this.$message.error("仅支持PDF文件"); event.target.value = ""; this.upload.file = null; return; } this.upload.file = file; if (file && !this.upload.title) this.upload.title = file.name.replace(/\.pdf$/i, ""); this.$nextTick(() => this.$refs.uploadForm && this.$refs.uploadForm.clearValidate("file")); },
    uploadFile() { const selected = this.upload.file || (this.$refs.file && this.$refs.file.files && this.$refs.file.files[0]); if (!selected) { this.$message.error("请选择PDF文件"); return; } this.upload.file = selected; this.$refs.uploadForm.validate(async valid => { if (!valid) return; this.saving = true; try { await uploadTrainingMaterial({ ...this.upload, file: selected }); this.$message.success("PDF资料已上传并发布"); this.uploadVisible = false; this.load(); } catch (e) { this.error(e, "上传失败"); } finally { this.saving = false; } }); },
    async preview(row) { try { const blob = await fetchManagerBlob(`/training-materials/${row.id}/file`); this.releasePreview(); this.previewUrl = URL.createObjectURL(blob); this.previewTitle = row.title; this.previewVisible = true; } catch (e) { this.error(e, "PDF预览失败"); } },
    async download(row) { try { const blob = await fetchManagerBlob(`/training-materials/${row.id}/file?download=true`); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = row.original_filename; a.click(); URL.revokeObjectURL(url); } catch (e) { this.error(e, "下载失败"); } },
    releasePreview() { if (this.previewUrl) URL.revokeObjectURL(this.previewUrl); this.previewUrl = ""; },
    async toggleStatus(row) { try { await updateTrainingMaterial(row.id, { status: row.status === "active" ? "archived" : "active" }); this.$message.success(row.status === "active" ? "资料已归档，学员不可见" : "资料已发布"); this.load(); } catch (e) { this.error(e, "状态更新失败"); } },
    async remove(row) { try { await this.$confirm(`确定删除“${row.title}”及其PDF原文件吗？`, "删除确认", { type: "warning" }); await deleteTrainingMaterial(row.id); this.$message.success("资料已删除"); this.load(); } catch (e) { if (e !== "cancel") this.error(e, "删除失败"); } },
  },
};
</script>

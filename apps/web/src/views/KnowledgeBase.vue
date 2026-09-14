<template>
  <div>
    <div class="page-heading">
      <div>
        <h1>AI知识库</h1>
        <p>采购与项目知识分域维护；AI回答仅检索已生效资料，并显示来源依据。</p>
      </div>
      <div>
        <el-button @click="openUpload">导入文件</el-button>
        <el-button type="primary" @click="open()">新增知识</el-button>
      </div>
    </div>
    <el-alert
      title="项目助手与采购助手共用对话入口，但分别检索项目域和采购域知识；“共享”资料可被两个助手使用。"
      type="info"
      :closable="false"
    />
    <div class="table-toolbar">
      <el-input
        v-model.trim="keyword"
        clearable
        placeholder="搜索标题、标签、来源或正文"
        @keyup.enter.native="search"
        @clear="search"
      />
      <el-select
        v-model="domain"
        clearable
        placeholder="全部知识域"
        @change="search"
      >
        <el-option
          v-for="item in domains"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-select
        v-model="status"
        clearable
        placeholder="全部状态"
        @change="search"
      >
        <el-option label="草稿" value="draft" /><el-option
          label="生效"
          value="active"
        /><el-option label="归档" value="archived" />
      </el-select>
      <el-button icon="el-icon-search" @click="search">查询</el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      stripe
      border
      empty-text="暂无知识资料"
    >
      <el-table-column prop="title" label="标题" min-width="210" />
      <el-table-column label="知识域" width="100"
        ><template slot-scope="s"
          ><el-tag
            :type="
              s.row.domain === 'project'
                ? 'success'
                : s.row.domain === 'shared'
                ? 'warning'
                : ''
            "
            >{{ domainName(s.row.domain) }}</el-tag
          ></template
        ></el-table-column
      >
      <el-table-column label="类型" width="100"
        ><template slot-scope="s">{{
          typeName(s.row.document_type)
        }}</template></el-table-column
      >
      <el-table-column
        prop="source_name"
        label="来源"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        prop="tags"
        label="标签"
        min-width="140"
        show-overflow-tooltip
      />
      <el-table-column label="状态" width="85"
        ><template slot-scope="s">{{
          statusName(s.row.status)
        }}</template></el-table-column
      >
      <el-table-column prop="version" label="版本" width="65" />
      <el-table-column label="操作" width="145" fixed="right"
        ><template slot-scope="s"
          ><el-button type="text" @click="open(s.row)">查看/编辑</el-button
          ><el-button type="text" class="danger-link" @click="remove(s.row)"
            >删除</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, sizes, prev, pager, next"
      :page-sizes="[10, 20, 50]"
      @current-change="changePage"
      @size-change="changeSize"
    />

    <el-dialog
      :title="form.id ? '编辑知识' : '新增知识'"
      :visible.sync="visible"
      width="780px"
      :close-on-click-modal="false"
    >
      <el-form ref="form" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="标题" prop="title"
          ><el-input v-model.trim="form.title"
        /></el-form-item>
        <el-row :gutter="14">
          <el-col :span="8"
            ><el-form-item label="知识域" prop="domain"
              ><el-select v-model="form.domain"
                ><el-option
                  v-for="item in domains"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value" /></el-select></el-form-item
          ></el-col>
          <el-col :span="8"
            ><el-form-item label="类型"
              ><el-select v-model="form.document_type"
                ><el-option
                  v-for="item in types"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value" /></el-select></el-form-item
          ></el-col>
          <el-col :span="8"
            ><el-form-item label="状态"
              ><el-select v-model="form.status"
                ><el-option label="草稿" value="draft" /><el-option
                  label="生效"
                  value="active" /><el-option
                  label="归档"
                  value="archived" /></el-select></el-form-item
          ></el-col>
        </el-row>
        <el-form-item label="来源"
          ><el-input v-model.trim="form.source_name"
        /></el-form-item>
        <el-form-item label="标签"
          ><el-input
            v-model.trim="form.tags"
            placeholder="例如：询价, TOC, 项目风险"
        /></el-form-item>
        <el-form-item label="正文" prop="content"
          ><el-input
            v-model="form.content"
            type="textarea"
            :rows="12"
            maxlength="500000"
            show-word-limit
        /></el-form-item>
      </el-form>
      <span slot="footer"
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存</el-button
        ></span
      >
    </el-dialog>

    <el-dialog
      title="导入知识文件"
      :visible.sync="uploadVisible"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form label-width="90px">
        <el-form-item label="标题"
          ><el-input v-model.trim="upload.title"
        /></el-form-item>
        <el-row
          ><el-col :span="12"
            ><el-form-item label="知识域"
              ><el-select v-model="upload.domain"
                ><el-option
                  v-for="item in domains"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value" /></el-select></el-form-item></el-col
          ><el-col :span="12"
            ><el-form-item label="类型"
              ><el-select v-model="upload.document_type"
                ><el-option
                  v-for="item in types"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value" /></el-select></el-form-item></el-col
        ></el-row>
        <el-form-item label="标签"
          ><el-input v-model.trim="upload.tags"
        /></el-form-item>
        <el-form-item label="文件"
          ><input
            ref="file"
            type="file"
            accept=".txt,.md,.pdf,.docx"
            @change="pickFile"
          />
          <p class="tip">
            支持TXT、Markdown、可提取文本的PDF和DOCX，最大10MB；扫描PDF请先OCR。
          </p></el-form-item
        >
      </el-form>
      <span slot="footer"
        ><el-button @click="uploadVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="uploadFile"
          >解析并生效</el-button
        ></span
      >
    </el-dialog>
  </div>
</template>
<script>
import { api } from "../api/client";

const blank = () => ({
  id: "",
  title: "",
  domain: "procurement",
  document_type: "guide",
  source_name: "manual",
  tags: "",
  content: "",
  status: "active",
  version: null,
});
export default {
  data: () => ({
    items: [],
    total: 0,
    page: 1,
    pageSize: 10,
    keyword: "",
    domain: "",
    status: "",
    loading: false,
    saving: false,
    visible: false,
    uploadVisible: false,
    form: blank(),
    selectedFile: null,
    upload: {
      title: "",
      domain: "procurement",
      document_type: "guide",
      tags: "",
    },
    domains: [
      { value: "procurement", label: "采购知识" },
      { value: "project", label: "项目知识" },
      { value: "shared", label: "共享知识" },
    ],
    types: [
      { value: "policy", label: "制度" },
      { value: "procedure", label: "流程" },
      { value: "guide", label: "指南" },
      { value: "case", label: "案例" },
      { value: "faq", label: "问答" },
      { value: "training", label: "培训" },
    ],
    rules: {
      title: [{ required: true, message: "请填写标题", trigger: "blur" }],
      domain: [{ required: true, message: "请选择知识域", trigger: "change" }],
      content: [
        {
          required: true,
          min: 10,
          message: "正文至少10个字符",
          trigger: "blur",
        },
      ],
    },
  }),
  created() {
    this.load();
  },
  methods: {
    domainName(value) {
      return this.domains.find((item) => item.value === value)?.label || value;
    },
    typeName(value) {
      return this.types.find((item) => item.value === value)?.label || value;
    },
    statusName(value) {
      return (
        { draft: "草稿", active: "生效", archived: "归档" }[value] || value
      );
    },
    error(e) {
      const d = e.response?.data?.detail;
      this.$message.error(
        Array.isArray(d) ? d.map((x) => x.msg).join("；") : d || "操作失败"
      );
    },
    async load() {
      this.loading = true;
      try {
        const r = (
          await api.get("/knowledge", {
            params: {
              keyword: this.keyword,
              domain: this.domain,
              status: this.status,
              page: this.page,
              page_size: this.pageSize,
            },
          })
        ).data;
        this.items = r.items;
        this.total = r.total;
      } catch (e) {
        this.error(e);
      } finally {
        this.loading = false;
      }
    },
    search() {
      this.page = 1;
      this.load();
    },
    changePage(value) {
      this.page = value;
      this.load();
    },
    changeSize(value) {
      this.pageSize = value;
      this.page = 1;
      this.load();
    },
    open(row) {
      this.form = row ? { ...row } : blank();
      this.visible = true;
      this.$nextTick(() => this.$refs.form?.clearValidate());
    },
    async save() {
      try {
        await this.$refs.form.validate();
      } catch (_) {
        return;
      }
      this.saving = true;
      try {
        if (this.form.id)
          await api.put(`/knowledge/${this.form.id}`, this.form);
        else await api.post("/knowledge", this.form);
        this.visible = false;
        await this.load();
        this.$message.success("知识资料已保存");
      } catch (e) {
        this.error(e);
      } finally {
        this.saving = false;
      }
    },
    async remove(row) {
      try {
        await this.$confirm(`删除《${row.title}》？`, "删除确认", {
          type: "warning",
        });
        await api.delete(`/knowledge/${row.id}`, {
          params: { version: row.version },
        });
        await this.load();
      } catch (e) {
        if (e !== "cancel") this.error(e);
      }
    },
    openUpload() {
      this.upload = {
        title: "",
        domain: "procurement",
        document_type: "guide",
        tags: "",
      };
      this.selectedFile = null;
      this.uploadVisible = true;
    },
    pickFile(event) {
      this.selectedFile = event.target.files[0] || null;
      if (this.selectedFile && !this.upload.title)
        this.upload.title = this.selectedFile.name.replace(/\.[^.]+$/, "");
    },
    async uploadFile() {
      if (!this.upload.title || !this.selectedFile)
        return this.$message.warning("请填写标题并选择文件");
      const data = new FormData();
      Object.entries(this.upload).forEach(([key, value]) =>
        data.append(key, value)
      );
      data.append("file", this.selectedFile);
      this.saving = true;
      try {
        await api.post("/knowledge/upload", data, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        this.uploadVisible = false;
        await this.load();
        this.$message.success("文件已解析并加入知识库");
      } catch (e) {
        this.error(e);
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>
<style scoped>
.danger-link {
  color: #f56c6c;
}
.tip {
  color: #8492a6;
  font-size: 12px;
}
</style>

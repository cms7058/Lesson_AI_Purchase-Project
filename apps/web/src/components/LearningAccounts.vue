<template>
  <div>
    <div class="table-toolbar">
      <el-input v-model.trim="keyword" clearable placeholder="搜索登录名、人员编号或姓名" @keyup.enter.native="search" @clear="search" />
      <el-button icon="el-icon-search" @click="search">查询</el-button>
      <el-button type="primary" icon="el-icon-plus" @click="openCreate">新增学习账号</el-button>
      <el-button type="text" @click="$router.push('/learning')">打开学员登录页</el-button>
    </div>
    <el-alert title="学习账号与人员档案一一关联；停用人员后，其学习账号将无法登录。密码只可重置，不会明文显示。" type="info" :closable="false" show-icon />
    <el-table v-loading="loading" :data="items" class="data-table" empty-text="暂无学习账号">
      <el-table-column prop="staff_code" label="人员编号" width="125" />
      <el-table-column prop="staff_name" label="姓名" width="120" />
      <el-table-column prop="department" label="部门/班级" min-width="150" />
      <el-table-column prop="username" label="登录账号" min-width="180" />
      <el-table-column label="状态" width="90"><template slot-scope="s"><el-tag :type="s.row.active ? 'success' : 'info'">{{ s.row.active ? '启用' : '停用' }}</el-tag></template></el-table-column>
      <el-table-column label="最近登录" min-width="165"><template slot-scope="s">{{ formatTime(s.row.last_login_at) }}</template></el-table-column>
      <el-table-column label="操作" width="150"><template slot-scope="s"><el-button type="text" @click="edit(s.row)">编辑/重置密码</el-button><el-button type="text" class="danger-link" @click="remove(s.row)">删除</el-button></template></el-table-column>
    </el-table>
    <div class="pagination-row"><span>共 {{ pagination.total }} 条</span><el-pagination background layout="sizes, prev, pager, next" :page-sizes="[10,20,50]" :current-page="pagination.page" :page-size="pagination.page_size" :total="pagination.total" @current-change="changePage" @size-change="changeSize" /></div>

    <el-dialog :title="editingId ? '编辑学习账号' : '新增学习账号'" :visible.sync="visible" width="560px" :close-on-click-modal="false">
      <el-form ref="form" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="关联人员" prop="staff_id"><el-select v-model="form.staff_id" filterable style="width:100%" placeholder="请选择人员"><el-option v-for="item in staff" :key="item.id" :label="`${item.user_code} · ${item.name} · ${item.department}`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="登录账号" prop="username"><el-input v-model.trim="form.username" autocomplete="off" /></el-form-item>
        <el-form-item :label="editingId ? '重置密码' : '初始密码'" :prop="editingId ? '' : 'password'"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" :placeholder="editingId ? '留空表示不修改，至少8位' : '至少8位'" /></el-form-item>
        <el-form-item label="账号状态"><el-switch v-model="form.active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <span slot="footer"><el-button @click="visible=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></span>
    </el-dialog>
  </div>
</template>

<script>
import { createLearningAccount, deleteLearningAccount, fetchLearningAccounts, fetchStaffUsers, updateLearningAccount } from "../api/client";

const blank = () => ({ staff_id: "", username: "", password: "", active: true });

export default {
  data: () => ({
    keyword: "", items: [], staff: [], loading: false, saving: false, visible: false, editingId: "", form: blank(),
    pagination: { page: 1, page_size: 10, total: 0 },
    rules: {
      staff_id: [{ required: true, message: "请选择关联人员", trigger: "change" }],
      username: [{ required: true, message: "请输入登录账号", trigger: "blur" }, { min: 3, message: "至少3个字符", trigger: "blur" }],
      password: [{ required: true, message: "请输入初始密码", trigger: "blur" }, { min: 8, message: "密码至少8位", trigger: "blur" }],
    },
  }),
  created() { this.loadStaff(); this.load(); },
  methods: {
    error(e, fallback) { const d = e.response && e.response.data && e.response.data.detail; this.$message.error(d || fallback); },
    formatTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚未登录"; },
    async loadStaff() { try { this.staff = (await fetchStaffUsers({ page: 1, page_size: 100, status: "active" })).items; } catch (e) { this.error(e, "人员列表加载失败"); } },
    async load() { this.loading = true; try { const r = await fetchLearningAccounts({ keyword: this.keyword, ...this.pagination }); this.items = r.items; this.pagination.total = r.total; } catch (e) { this.error(e, "学习账号加载失败"); } finally { this.loading = false; } },
    search() { this.pagination.page = 1; this.load(); },
    changePage(page) { this.pagination.page = page; this.load(); },
    changeSize(size) { this.pagination.page_size = size; this.pagination.page = 1; this.load(); },
    openCreate() { this.editingId = ""; this.form = blank(); this.visible = true; },
    edit(row) { this.editingId = row.id; this.form = { staff_id: row.staff_id, username: row.username, password: "", active: row.active }; this.visible = true; },
    save() { this.$refs.form.validate(async valid => { if (!valid) return; this.saving = true; try { const payload = { ...this.form }; if (this.editingId && !payload.password) delete payload.password; if (this.editingId) await updateLearningAccount(this.editingId, payload); else await createLearningAccount(payload); this.$message.success("学习账号已保存"); this.visible = false; await this.load(); } catch (e) { this.error(e, "账号保存失败"); } finally { this.saving = false; } }); },
    async remove(row) { try { await this.$confirm(`确定删除学习账号 ${row.username} 吗？已有考试记录时系统会阻止删除。`, "删除确认", { type: "warning" }); await deleteLearningAccount(row.id); this.$message.success("删除成功"); await this.load(); } catch (e) { if (e !== "cancel") this.error(e, "删除失败"); } },
  },
};
</script>

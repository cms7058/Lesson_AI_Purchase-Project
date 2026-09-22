<template>
  <section class="ai-chat">
    <p class="ai-notice">
      {{
        supplierMode
          ? "仅查询本企业订单与受邀询价，需先登录供应商账号。"
          : "只读查询 · 实时数据库 · 不自动审批、改价或修改权限"
      }}
    </p>
    <div>
      <el-button size="mini" :disabled="sending" @click="messages = []"
        >清空对话</el-button
      >
    </div>
    <div class="ai-history" ref="history" aria-live="polite">
      <el-empty
        v-if="!messages.length"
        description="可输入：查询待送货订单、查询物料编码 MAT-001 的价格"
        :image-size="60"
      />
      <article
        v-for="(item, index) in messages"
        :key="index"
        :class="['ai-message', item.role]"
      >
        <strong>{{ item.role === "user" ? "我" : "AI助力助手" }}</strong>
        <p>{{ item.text }}</p>
        <div
          v-if="item.citations && item.citations.length"
          class="ai-citations"
        >
          <strong>知识依据</strong
          ><el-tag
            v-for="source in item.citations"
            :key="source.id"
            size="mini"
            type="info"
            >{{ source.title }} · {{ source.source }}</el-tag
          >
        </div>
        <div v-if="item.result" v-loading="item.loading" class="ai-result">
          <p class="ai-scope">
            已识别条件：{{ conditions(item.result.filters) }} ·
            {{ item.result.total }} 条 · 第 {{ item.result.page }} 页
          </p>
          <el-collapse v-if="item.result.available_fields.length"
            ><el-collapse-item title="调整组合查询条件">
              <div
                v-for="(f, i) in item.draftFilters"
                :key="i"
                class="ai-filter-row"
              >
                <el-select
                  v-model="f.field"
                  size="small"
                  @change="
                    f.op = 'eq';
                    f.value = '';
                  "
                  ><el-option
                    v-for="col in item.result.available_fields"
                    :key="col.key"
                    :label="col.label"
                    :value="col.key"
                /></el-select>
                <el-select v-model="f.op" size="small"
                  ><el-option label="等于" value="eq" /><el-option
                    label="不等于"
                    value="ne" /><el-option
                    v-if="fieldType(item, f) === 'text'"
                    label="包含"
                    value="contains" /><template
                    v-if="
                      ['number', 'date', 'datetime'].includes(
                        fieldType(item, f)
                      )
                    "
                    ><el-option label="大于等于" value="gte" /><el-option
                      label="小于等于"
                      value="lte" /></template
                ></el-select>
                <el-select
                  v-if="fieldType(item, f) === 'boolean'"
                  v-model="f.value"
                  size="small"
                  ><el-option :value="true" label="是" /><el-option
                    :value="false"
                    label="否"
                /></el-select>
                <el-date-picker
                  v-else-if="['date', 'datetime'].includes(fieldType(item, f))"
                  v-model="f.value"
                  :type="fieldType(item, f)"
                  :value-format="
                    fieldType(item, f) === 'date'
                      ? 'yyyy-MM-dd'
                      : `yyyy-MM-dd'T'HH:mm:ss`
                  "
                  size="small"
                />
                <el-input
                  v-else
                  v-model="f.value"
                  size="small"
                  placeholder="条件值（状态使用数据库编码）"
                />
                <el-button type="text" @click="item.draftFilters.splice(i, 1)"
                  >移除</el-button
                >
              </div>
              <el-button
                size="small"
                :disabled="item.draftFilters.length >= 12"
                @click="
                  item.draftFilters.push({
                    field: item.result.available_fields[0].key,
                    op: 'eq',
                    value: '',
                  })
                "
                >添加条件</el-button
              ><el-button size="small" type="primary" @click="refine(item)"
                >应用条件</el-button
              >
              <p>所有条件同时满足；清空条件后应用即可查询全部。</p>
            </el-collapse-item></el-collapse
          >
          <template v-if="item.result.chart.data.length"
            ><h4>{{ item.result.chart.title }}</h4>
            <AnalysisChart :option="chart(item.result.chart)"
          /></template>
          <el-table
            :data="item.result.rows"
            stripe
            border
            max-height="350"
            size="small"
            ><el-table-column
              v-for="col in item.result.columns"
              :key="col.key"
              :prop="col.key"
              :label="col.label"
              :min-width="col.key === '明细' ? 350 : 145"
              show-overflow-tooltip
          /></el-table>
          <el-pagination
            :current-page="item.result.page"
            :page-size="item.result.page_size"
            :total="item.result.total"
            layout="total, prev, pager, next"
            @current-change="loadPage(item, $event)"
          />
        </div>
      </article>
    </div>
    <div class="ai-compose">
      <el-input
        v-model="message"
        type="textarea"
        :rows="2"
        maxlength="8000"
        placeholder="输入问题（Enter 发送，Shift+Enter 换行）"
        @keydown.native="handleComposerKeydown"
      /><el-button type="primary" :loading="sending" @click="send"
        >发送</el-button
      >
    </div>
  </section>
</template>
<script>
import axios from "axios";
import { api } from "../api/client";
import AnalysisChart from "./AnalysisChart.vue";
export default {
  components: { AnalysisChart },
  props: { supplierMode: Boolean, pageGuide: { type: String, default: "" } },
  data: () => ({ message: "", messages: [], sending: false, identity: "" }),
  created() {
    if (this.pageGuide) this.messages.push({ role: "assistant", text: this.pageGuide, guide: true });
  },
  methods: {
    handleComposerKeydown(event) {
      if (
        event.key !== "Enter" ||
        event.shiftKey ||
        event.isComposing ||
        event.keyCode === 229 ||
        event.target.composing
      )
        return;
      event.preventDefault();
      if (!event.repeat) this.send();
    },
    conditions(filters) {
      return filters.length
        ? filters.map((x) => x.field + " " + x.op + " " + x.value).join("；")
        : "全部记录（未应用其他条件）";
    },
    chart(c) {
      return {
        tooltip: { trigger: "axis" },
        grid: { left: 65, right: 20, bottom: 90 },
        xAxis: {
          type: "category",
          data: c.data.map((x) => x.name),
          axisLabel: { rotate: 25, overflow: "truncate", width: 100 },
        },
        yAxis: { type: "value", minInterval: 1 },
        series: [
          {
            type: "bar",
            data: c.data.map((x) => x.value),
            itemStyle: { color: "#2878ff" },
          },
        ],
      };
    },
    async request(payload) {
      if (this.supplierMode) {
        const token = sessionStorage.getItem("supplier_token");
        if (!token) throw new Error("请先登录供应商账号");
        return (
          await axios.post(
            (process.env.VUE_APP_API_BASE_URL || "/api/v1") + "/assistant/chat",
            payload,
            { timeout: 40000, headers: { Authorization: "Bearer " + token } }
          )
        ).data;
      }
      return (await api.post("/assistant/chat", payload, { timeout: 40000 }))
        .data;
    },
    error(e) {
      return typeof e.response?.data?.detail === "string"
        ? e.response.data.detail
        : e.message || "查询失败，请重试";
    },
    async send() {
      if (this.sending || !this.message.trim()) return;
      const identity = this.supplierMode
        ? sessionStorage.getItem("supplier_token")
        : this.$store.state.user.role;
      if (this.identity !== identity) {
        this.messages = [];
        this.identity = identity;
      }
      const message = this.message.trim();
      this.messages.push({ role: "user", text: message });
      this.message = "";
      this.sending = true;
      try {
        const data = await this.request({
          message,
          context_module: this.$route.path,
          history: this.messages
            .slice(0, -1)
            .slice(-12)
            .map((m) => ({ role: m.role, content: m.text })),
        });
        this.messages.push({
          role: "assistant",
          text: data.message,
          result: data.result,
          citations: data.citations || [],
          loading: false,
          question: message,
          draftFilters: JSON.parse(JSON.stringify(data.result?.filters || [])),
        });
      } catch (e) {
        this.messages.push({ role: "assistant", text: this.error(e) });
      } finally {
        this.sending = false;
        this.$nextTick(() => {
          const last = this.$refs.history.querySelector(
            ".ai-message:last-child"
          );
          if (last)
            this.$refs.history.scrollTop =
              last.offsetTop - this.$refs.history.offsetTop;
        });
      }
    },
    fieldType(item, f) {
      return (
        item.result.available_fields.find((x) => x.key === f.field)?.type ||
        "text"
      );
    },
    async refine(item) {
      if (item.draftFilters.some((f) => f.value === "" || f.value === null))
        return this.$message.warning("请填写条件值");
      await this.loadPage(item, 1, item.draftFilters);
    },
    async loadPage(item, page, filters) {
      if (item.loading) return;
      item.loading = true;
      try {
        const data = await this.request({
          message: item.question,
          resource: item.result.resource,
          filters: filters || item.result.filters,
          page,
          page_size: item.result.page_size,
        });
        item.result = data.result;
        item.draftFilters = JSON.parse(JSON.stringify(data.result.filters));
      } catch (e) {
        this.$message.error(this.error(e));
      } finally {
        item.loading = false;
      }
    },
  },
};
</script>

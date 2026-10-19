<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { RefreshCw, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Courses from './Courses.vue';
import People from './People.vue';
import Questions from './Questions.vue';
import Knowledge from './Knowledge.vue';
import Teaching from './Teaching.vue';
import Commerce from './Commerce.vue';
import { currentSection } from './navigation';
import { useTask, localDate } from './api';
import type { Gateway, Meta, Page } from './types';
import './style.css';

const props = defineProps<{ api: Gateway; section?: string }>();
const tab = computed(() => currentSection(props.section));
const meta = ref<Meta>();
const records = ref<Page<any>>({ items: [], total: 0, page: 1, page_size: 25 });
const { busy, error, run } = useTask();
async function loadAudit(page = 1) { records.value = await props.api('audit.list', { page }); }
watch(tab, value => { if (value === 'audit') void run(() => loadAudit()); });
async function connect() { meta.value = await props.api('meta'); if (tab.value === 'audit') await loadAudit(); }
onMounted(() => run(connect));
const operationNames: Record<string, string> = { 'courses.save': '保存课程', 'courses.delete': '删除课程', 'courses.assign': '批量归类',
  'modules.save': '保存模块', 'modules.delete': '删除模块', 'products.save': '保存服务', 'grants.create': '发放服务',
  'grants.revoke': '撤销服务', 'students.access.save': '配置功能权限', 'uploads.start': '开始上传', 'uploads.complete': '保存附件', 'uploads.cancel': '取消上传',
  'knowledge.save': '保存知识目录', 'knowledge.delete': '删除知识目录', 'questions.save': '保存题目', 'questions.delete': '删除题目', 'questions.assign': '题目批量归类',
  'students.status.save': '调整学员状态', 'quota.save': '配置每周额度', 'addons.save': '保存 AI 加量商品',
  'ai.config.save': '保存 AI 配置', 'teaching.chat': '教学对话', 'teaching.generate': '生成题目',
  'teaching.report': '生成学情报告', 'teaching.restore': '恢复待审核题目', 'teaching.notification.send': '发送学习提醒',
  'teaching.notification.config.save': '保存通知配置', 'pipeline.review': '审核题目入库',
  'pipeline.retry': '重试内容任务', 'pipeline.delete': '删除内容任务',
  'courses.transcript.get': '查看字幕', 'courses.transcript.save': '保存字幕',
  'courses.transcript.retranscribe': '重新识别字幕', 'courses.outline.regenerate': '重新生成大纲' };
</script>

<template>
  <main class="um-admin" :aria-busy="busy">
    <div class="workspace-heading"><div><span class="brand">科晟智慧</span><h1>UniMind 管理</h1></div><span class="operator">{{ meta?.operator.name || '连接中' }}</span></div>
    <p v-if="error" class="error" role="alert">{{ error }} <button :disabled="busy" @click="run(connect)">重试</button></p>
    <p v-if="meta && !meta.content_configured" class="notice">内容归属尚未配置，教学内容暂为只读。</p>
    <template v-if="meta">
      <Courses v-if="tab === 'courses' || tab === 'modules'" :key="tab" :view="tab" :api="api" :meta="meta" />
      <People v-else-if="tab === 'people'" :api="api" />
      <Commerce v-else-if="tab === 'products' || tab === 'orders' || tab === 'settings'" :key="tab" :view="tab" :api="api" />
      <Teaching v-else-if="tab === 'workbench' || tab === 'tasks'" :key="tab" :view="tab" :api="api" :meta="meta" />
      <Questions v-else-if="tab === 'questions'" :api="api" :meta="meta" />
      <Knowledge v-else-if="tab === 'knowledge'" :api="api" :meta="meta" />
      <section v-else class="workspace-section">
        <div class="section-heading"><h2>操作记录 <span>{{ records.total }}</span></h2><button class="icon" title="刷新" :disabled="busy" @click="run(() => loadAudit(records.page))"><RefreshCw :size="17" /></button></div>
        <div class="table-scroll"><table><thead><tr><th>发生时间</th><th>操作人</th><th>操作</th><th>对象编号</th><th>请求编号</th></tr></thead><tbody><tr v-for="row in records.items" :key="row.id"><td>{{ localDate(row.created_at) }}</td><td>{{ row.operator }}</td><td>{{ operationNames[row.detail.operation] || row.detail.operation }}</td><td>{{ row.detail.target ?? '－' }}</td><td class="mono">{{ row.request_id }}</td></tr><tr v-if="!records.items.length"><td colspan="5" class="empty">暂无操作记录</td></tr></tbody></table></div>
        <footer class="pagination"><span>共 {{ records.total }} 条</span><button class="icon" title="上一页" :disabled="busy || records.page <= 1" @click="run(() => loadAudit(records.page - 1))"><ChevronLeft :size="17" /></button><span>{{ records.page }}</span><button class="icon" title="下一页" :disabled="busy || records.page * records.page_size >= records.total" @click="run(() => loadAudit(records.page + 1))"><ChevronRight :size="17" /></button></footer>
      </section>
    </template>
  </main>
</template>

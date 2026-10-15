<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { BookOpen, Users, Layers, Package, History, RefreshCw, ListChecks, FolderTree } from 'lucide-vue-next';
import Courses from './Courses.vue';
import People from './People.vue';
import Questions from './Questions.vue';
import Knowledge from './Knowledge.vue';
import { useTask, localDate } from './api';
import type { Gateway, Meta, Page } from './types';
import './style.css';

const props = defineProps<{ api: Gateway }>();
const sections = [{ id: 'courses', name: '课程', icon: BookOpen }, { id: 'modules', name: '模块', icon: Layers },
  { id: 'questions', name: '题库', icon: ListChecks }, { id: 'knowledge', name: '知识目录', icon: FolderTree },
  { id: 'people', name: '学员', icon: Users }, { id: 'products', name: '学习服务', icon: Package }, { id: 'audit', name: '操作记录', icon: History }];
const tab = ref('courses');
const meta = ref<Meta>();
const records = ref<Page<any>>({ items: [], total: 0, page: 1, page_size: 25 });
const { busy, error, run } = useTask();
async function loadAudit(page = 1) { records.value = await props.api('audit.list', { page }); }
function navigate(value: string) { tab.value = value; if (value === 'audit') void run(() => loadAudit()); }
onMounted(() => run(async () => { meta.value = await props.api('meta'); }));
const operationNames: Record<string, string> = { 'courses.save': '保存课程', 'courses.delete': '删除课程', 'courses.assign': '批量归类',
  'modules.save': '保存模块', 'modules.delete': '删除模块', 'products.save': '保存服务', 'grants.create': '发放服务',
  'grants.revoke': '撤销服务', 'students.access.save': '配置功能权限', 'uploads.start': '开始上传', 'uploads.complete': '保存附件', 'uploads.cancel': '取消上传',
  'knowledge.save': '保存知识目录', 'knowledge.delete': '删除知识目录', 'questions.save': '保存题目', 'questions.delete': '删除题目', 'questions.assign': '题目批量归类' };
</script>

<template>
  <main class="um-admin" :aria-busy="busy">
    <div class="workspace-heading"><div><span class="brand">科晟智慧</span><h1>UniMind 管理</h1></div><span class="operator">{{ meta?.operator.name || '连接中' }}</span></div>
    <nav aria-label="UniMind 管理导航"><button v-for="section in sections" :key="section.id" :class="{ active: tab === section.id }" :aria-current="tab === section.id ? 'page' : undefined" @click="navigate(section.id)"><component :is="section.icon" :size="17" />{{ section.name }}</button></nav>
    <p v-if="error" class="error" role="alert">{{ error }} <button :disabled="busy" @click="run(async () => { meta = await api('meta'); })">重新连接</button></p>
    <p v-if="meta && !meta.content_configured" class="notice">内容归属尚未配置，教学内容暂为只读。</p>
    <template v-if="meta">
      <Courses v-if="tab === 'courses' || tab === 'modules'" :key="tab" :view="tab" :api="api" :meta="meta" />
      <People v-else-if="tab === 'people' || tab === 'products'" :key="tab" :view="tab" :api="api" />
      <Questions v-else-if="tab === 'questions'" :api="api" :meta="meta" />
      <Knowledge v-else-if="tab === 'knowledge'" :api="api" :meta="meta" />
      <section v-else class="workspace-section">
        <div class="section-heading"><h2>操作记录 <span>{{ records.total }}</span></h2><button class="icon" title="刷新" :disabled="busy" @click="run(() => loadAudit(records.page))"><RefreshCw :size="17" /></button></div>
        <div class="table-scroll"><table><thead><tr><th>发生时间</th><th>操作人</th><th>操作</th><th>对象编号</th><th>请求编号</th></tr></thead><tbody><tr v-for="row in records.items" :key="row.id"><td>{{ localDate(row.created_at) }}</td><td>{{ row.operator }}</td><td>{{ operationNames[row.detail.operation] || row.detail.operation }}</td><td>{{ row.detail.target ?? '－' }}</td><td class="mono">{{ row.request_id }}</td></tr><tr v-if="!records.items.length"><td colspan="5" class="empty">暂无操作记录</td></tr></tbody></table></div>
        <footer class="pagination"><span>共 {{ records.total }} 条</span><button :disabled="busy || records.page <= 1" @click="run(() => loadAudit(records.page - 1))">上一页</button><span>{{ records.page }}</span><button :disabled="busy || records.page * 25 >= records.total" @click="run(() => loadAudit(records.page + 1))">下一页</button></footer>
      </section>
    </template>
  </main>
</template>

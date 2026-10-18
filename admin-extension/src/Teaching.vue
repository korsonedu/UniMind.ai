<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RefreshCw, Send, Plus, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import TeachingData from './TeachingData.vue';
import { localDate, useTask } from './api';
import { difficulties } from './catalog';
import type { Gateway, Meta, Page, Payload } from './types';

type Job = { id: number; title: string; status: string; progress: number; task_type: string; payload: any; result?: any; error_message?: string; created_at: string };
type Message = { id: number; role: string; content: string; metadata: any };
type Candidate = { question?: string; text?: string; q_type?: string; subjective_type?: string; kp_id?: number; kp_name?: string; answer?: string; grading_points?: any; options?: any; difficulty_level?: string };
const props = defineProps<{ api: Gateway; meta: Meta; view: 'workbench' | 'tasks' }>();
const { busy, error, run } = useTask();
const stats = ref<any>();
const jobs = ref<Page<Job>>({ items: [], total: 0, page: 1, page_size: 20 });
const status = ref('');
const search = ref('');
const metrics = ref<any>();
const current = ref<Job>();
const panel = ref<'generate' | 'student' | 'notification' | 'assets' | 'notification-config' | ''>('');
const mode = ref<'quick' | 'arc' | 'bulk'>('quick');
const knowledge = ref<any[]>([]);
const kpQuery = ref('');
const selectedKps = ref<number[]>([]);
const subject = ref('');
const kpCode = ref('');
const count = ref(5);
const difficulty = ref('normal');
const types = ref<string[]>([]);
const difficultyDist = ref('{"easy": 1, "normal": 2, "hard": 1}');
const typeDist = ref('{"objective": 4, "subjective": 6}');
const conversations = ref<any[]>([]);
const conversationId = ref(crypto.randomUUID() as string);
const messages = ref<Message[]>([]);
const message = ref('');
const historyPage = ref(1);
const historyTotal = ref(0);
const activeJob = ref<Job>();
const candidates = ref<Candidate[]>([]);
const selected = ref<number[]>([]);
const candidateTask = ref<number>();
const editing = ref<number>();
const candidateEdit = ref<Candidate>({});
const candidateOptions = ref('');
const changes = ref<Record<string, Candidate>>({});
const people = ref<any[]>([]);
const studentId = ref<number | ''>('');
const studentQuery = ref('');
const studentReport = ref<any>();
const dateFrom = ref('');
const dateTo = ref('');
const noticeTitle = ref('学习提醒');
const noticeContent = ref('');
const noticePreview = ref<any>();
const noticeConfig = ref<any>();
const confirmation = ref<{ title: string; text: string; action: () => Promise<void> }>();
const assetKind = ref('courses');
const assetQuery = ref('');
const assets = ref<Page<any>>({ items: [], total: 0, page: 1, page_size: 20 });
const success = ref('');
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
const pendingRequests = new Map<string, string>();
const canWrite = computed(() => props.meta.content_configured && !busy.value);
const working = computed(() => !!activeJob.value && ['pending', 'running'].includes(activeJob.value.status));
const statusNames: Record<string, string> = { draft: '草稿', pending: '待执行', running: '执行中', review: '待审核', completed: '已完成', failed: '失败', cancelled: '已取消' };
const latestAssistant = computed(() => [...messages.value].reverse().find(row => row.role === 'assistant'));
const confirmations = computed<any[]>(() => latestAssistant.value?.metadata?.confirmations || []);
async function write<T = any>(operation: string, payload: Payload = {}): Promise<T> {
  const key = JSON.stringify([operation, payload]);
  const id = String(payload.request_id || pendingRequests.get(key) || crypto.randomUUID());
  pendingRequests.set(key, id);
  const result = await props.api<T>(operation, { ...payload, request_id: id });
  pendingRequests.delete(key);
  return result;
}
async function loadJobs(page = 1) { jobs.value = await props.api('pipeline.list', { page, page_size: 20, status: status.value, search: search.value }); }
async function loadConversations() { conversations.value = (await props.api('teaching.conversations', { page_size: 100 })).items; }
function reviewQuestions(task: Job) {
  candidates.value = task.result?.questions || [];
  candidateTask.value = task.id;
  selected.value = [];
  changes.value = {};
}
async function selectConversation(id: string) {
  if (!confirmDiscard()) return;
  conversationId.value = id;
  const data = await props.api<any>('teaching.history', { conversation_id: id, page_size: 100 });
  messages.value = data.items; historyPage.value = 1; historyTotal.value = data.total;
  const task = data.tasks.find((row: Job) => ['pending', 'running'].includes(row.status));
  activeJob.value = task;
  const review = data.tasks.find((row: Job) => row.status === 'review' && row.result?.questions?.length);
  if (review) reviewQuestions(review);
  else { candidates.value = []; candidateTask.value = undefined; }
  if (task) poll();
}
async function olderHistory() {
  const data = await props.api<any>('teaching.history', { conversation_id: conversationId.value, page: historyPage.value + 1, page_size: 100 });
  messages.value = [...data.items, ...messages.value]; historyPage.value = data.page; historyTotal.value = data.total;
}
function confirmDiscard() { return !(message.value.trim() || Object.keys(changes.value).length) || window.confirm('当前有未提交的内容，确认切换？'); }
function newConversation() {
  if (!confirmDiscard()) return;
  clearTimeout(timer);
  conversationId.value = crypto.randomUUID(); messages.value = []; message.value = ''; activeJob.value = undefined; candidates.value = []; candidateTask.value = undefined; changes.value = {};
}
async function send() {
  const text = message.value.trim();
  if (!text || working.value) return;
  const task = await write<Job>('teaching.chat', { conversation_id: conversationId.value, message: text });
  message.value = '';
  activeJob.value = task;
  messages.value.push({ id: -task.id, role: 'user', content: text, metadata: {} });
  await loadConversations();
  poll();
}
function poll() {
  clearTimeout(timer);
  if (disposed || !activeJob.value) return;
  const jobId = activeJob.value.id;
  timer = setTimeout(async () => {
    try {
      const job = await props.api<Job>('pipeline.detail', { id: jobId });
      if (disposed || activeJob.value?.id !== jobId) return;
      activeJob.value = job;
      if (current.value?.id === job.id) current.value = job;
      if (['pending', 'running'].includes(job.status)) { poll(); return; }
      if (job.status === 'failed') error.value = job.error_message || '任务失败，可在内容任务中重试。';
      if (job.payload?.kind === 'chat') {
        const data = await props.api<any>('teaching.history', { conversation_id: conversationId.value, page_size: 100 });
        messages.value = data.items; historyPage.value = 1; historyTotal.value = data.total;
      }
      if (job.status === 'review' && job.result?.questions?.length) reviewQuestions(job);
      if (job.payload?.kind === 'report') studentReport.value = job.result;
      await loadJobs(jobs.value.page);
      stats.value = await props.api('teaching.stats');
    } catch (e) { if (!disposed) error.value = e instanceof Error ? e.message : '进度查询失败，点击刷新可恢复。'; }
  }, 1800);
}
async function watchJob(job: Job) {
  activeJob.value = job;
  if (['pending', 'running'].includes(job.status)) poll();
  if (job.status === 'review') reviewQuestions(job);
}
async function generate(payload?: Payload) {
  const data: Payload = payload || { kind: mode.value, kp_ids: selectedKps.value, count: count.value,
    difficulty: difficulty.value, types: types.value, subject: subject.value, kp_code: kpCode.value };
  if (data.kind === 'bulk') {
    data.difficulty_dist = JSON.parse(difficultyDist.value);
    data.type_dist = JSON.parse(typeDist.value);
  }
  const job = await write<Job>('teaching.generate', data);
  panel.value = ''; success.value = `任务 #${job.id} 已提交，完成后请审核题目。`;
  await watchJob(job); await loadJobs();
}
async function findKnowledge() { knowledge.value = (await props.api('teaching.knowledge', { query: kpQuery.value, page_size: 100 })).items; }
async function findPeople() { people.value = (await props.api('teaching.students', { search: studentQuery.value, page_size: 100 })).items; }
async function restoreDraft(item: Message) {
  const job = await write<Job>('teaching.restore', { message_id: item.id });
  if (job.status === 'review') reviewQuestions(job);
  else success.value = '该历史结果已经处理，不再重复恢复。';
}
async function saveNoticeConfig() {
  noticeConfig.value = await write('teaching.notification.config.save', { enabled: noticeConfig.value.enabled, channel: noticeConfig.value.channel, due_threshold: noticeConfig.value.due_threshold });
  success.value = '到期提醒配置已保存。'; panel.value = '';
}
async function openPanel(value: typeof panel.value) {
  panel.value = value; error.value = '';
  if (value === 'generate') await findKnowledge();
  if (['student', 'notification'].includes(value)) await findPeople();
  if (value === 'assets') await loadAssets();
  if (value === 'notification-config') noticeConfig.value = await props.api('teaching.notification.config');
}
function dates() { return { date_from: dateFrom.value ? new Date(dateFrom.value).toISOString() : undefined, date_to: dateTo.value ? new Date(dateTo.value).toISOString() : undefined }; }
async function loadStudent() { studentReport.value = await props.api('teaching.student', { student_id: studentId.value, ...dates() }); }
async function makeReport() {
  const job = await write<Job>('teaching.report', { student_id: studentId.value, ...dates() });
  await watchJob(job); success.value = `学情报告任务 #${job.id} 已提交。`;
}
async function previewNotification() {
  noticePreview.value = await props.api('teaching.notification.preview', { student_id: studentId.value, title: noticeTitle.value, content: noticeContent.value });
}
async function sendNotification(preview: any) {
  await write('teaching.notification.send', { ...preview, confirmed: true });
  noticePreview.value = undefined; panel.value = ''; success.value = '通知已发送。';
}
async function loadAssets(page = 1) { assets.value = await props.api('teaching.browse', { kind: assetKind.value, query: assetQuery.value, page }); }
async function openJob(row: Job) {
  if (Object.keys(changes.value).length && !window.confirm('有未保存的题目修改，确认切换任务？')) return;
  current.value = await props.api('pipeline.detail', { id: row.id });
  if (current.value?.status === 'review') reviewQuestions(current.value);
  await watchJob(current.value!);
}
function editCandidate(index: number) {
  editing.value = index;
  candidateEdit.value = { ...candidates.value[index], ...changes.value[String(index)] };
  candidateOptions.value = candidateEdit.value.options ? JSON.stringify(candidateEdit.value.options, null, 2) : '';
}
function saveCandidate() {
  if (editing.value == null) return;
  const options = candidateOptions.value.trim() ? JSON.parse(candidateOptions.value) : null;
  changes.value[String(editing.value)] = { ...candidateEdit.value, options };
  candidates.value[editing.value] = changes.value[String(editing.value)]!;
  editing.value = undefined;
}
async function reviewTask(action: 'approve' | 'reject') {
  const id = candidateTask.value;
  if (!id) return;
  await write('pipeline.review', { id, action, confirmed: true, question_indices: selected.value, edited_questions: changes.value });
  confirmation.value = undefined; candidates.value = []; candidateTask.value = undefined; changes.value = {}; current.value = undefined;
  success.value = action === 'approve' ? '所选题目已入库。' : '任务已拒绝。';
  await loadJobs(); stats.value = await props.api('teaching.stats');
}
function confirmReview(action: 'approve' | 'reject') {
  confirmation.value = { title: action === 'approve' ? '确认题目入库' : '拒绝本次结果',
    text: action === 'approve' ? `确认将选中的 ${selected.value.length} 道题目存入正式题库？` : '确认拒绝本次生成结果？', action: () => reviewTask(action) };
}
function removeTask(job: Job) {
  confirmation.value = { title: '删除内容任务', text: `确认删除任务 #${job.id}「${job.title}」？已入库题目会保留。`, action: async () => {
    await write('pipeline.delete', { id: job.id, confirmed: true }); confirmation.value = undefined; current.value = undefined; await loadJobs();
  } };
}
async function retryTask(job: Job) {
  const result = await write<Job>('pipeline.retry', { id: job.id }); current.value = result; await watchJob(result); await loadJobs();
}
async function refresh() {
  await loadJobs(jobs.value.page);
  if (activeJob.value) { const job = await props.api<Job>('pipeline.detail', { id: activeJob.value.id }); await watchJob(job); }
}
function leave(event: BeforeUnloadEvent) { if (message.value.trim() || Object.keys(changes.value).length) { event.preventDefault(); event.returnValue = ''; } }
onMounted(() => { window.addEventListener('beforeunload', leave); run(async () => {
  if (!props.meta.content_configured) return;
  stats.value = await props.api('teaching.stats'); await loadJobs(); await loadConversations();
}); });
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); window.removeEventListener('beforeunload', leave); });
watch(() => props.view, () => run(async () => { current.value = undefined; await loadJobs(); }));
</script>

<template>
  <section class="workspace-section teaching" :aria-busy="busy" :data-dirty="!!message.trim() || !!Object.keys(changes).length">
    <div class="section-heading"><h2>{{ view === 'tasks' ? '内容任务' : '教学工作台' }}</h2><div class="actions"><button title="刷新" :disabled="busy" @click="run(refresh)"><RefreshCw :size="16" />刷新</button></div></div>
    <p v-if="!meta.content_configured" class="notice">请先配置科晟内容归属，再使用教学工作台。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="success" class="teaching-success" role="status">{{ success }}</p>
    <div v-if="stats" class="teaching-stats"><span><strong>{{ stats.questions }}</strong> 正式题目</span><span><strong>{{ stats.knowledge_points }}</strong> 考点</span><span><strong>{{ stats.students }}</strong> 学员</span><span><strong>{{ stats.review_tasks }}</strong> 待审核任务</span></div>
    <template v-if="view === 'workbench'">
      <details v-if="stats" class="teaching-results"><summary>题库分布</summary><TeachingData :value="{ '学科': stats.by_subject, '难度': stats.by_difficulty, '题型': stats.by_type }" /></details>
      <div class="toolbar"><button :disabled="!canWrite" @click="run(() => openPanel('generate'))">出题与批量初始化</button><button :disabled="!canWrite" @click="run(() => openPanel('student'))">学情与报告</button><button :disabled="!canWrite" @click="run(() => openPanel('notification'))">通知学员</button><button :disabled="!canWrite" @click="run(() => openPanel('notification-config'))">到期提醒配置</button><button :disabled="busy || !meta.content_configured" @click="run(() => openPanel('assets'))">浏览教学资产</button></div>
      <div class="teaching-chat-layout"><aside class="teaching-conversations"><button :disabled="busy" @click="newConversation"><Plus :size="15" />新建对话</button><button v-for="item in conversations" :key="item.id" :class="{ active: conversationId === item.id }" :disabled="busy" @click="run(() => selectConversation(item.id))">{{ item.title || '未命名对话' }}</button><p v-if="!conversations.length" class="empty">暂无对话记录</p></aside>
        <div class="teaching-chat"><button v-if="messages.length < historyTotal" :disabled="busy" @click="run(olderHistory)">加载更早消息</button><div class="teaching-messages"><p v-if="!messages.length" class="empty">可以查找考点、生成题目、查看学情或准备通知。题目入库和发送通知会请你确认。</p><article v-for="item in messages" :key="item.id" :class="['teaching-message', item.role]"><small>{{ item.role === 'user' ? meta.operator.name : '教学助手' }}</small><p>{{ item.content }}</p><details v-if="item.metadata?.visuals?.length || item.metadata?.all_visuals?.length || item.metadata?.visual"><summary>查看学情与结构化结果</summary><TeachingData :value="item.metadata.visuals || item.metadata.all_visuals || item.metadata.visual" /></details><button v-if="item.role === 'assistant' && (item.metadata?.generated_questions?.length || item.metadata?.questions?.length)" :disabled="!canWrite" @click="run(() => restoreDraft(item))">恢复这批题目进行审核</button><button v-if="item.metadata?.pipeline_task_id" :disabled="busy" @click="run(() => openJob({ id: item.metadata.pipeline_task_id } as Job))">查看关联管线 #{{ item.metadata.pipeline_task_id }}</button></article></div>
          <div v-for="(item, index) in confirmations" :key="index" class="teaching-confirmation"><template v-if="item.type === 'notification'"><p>待确认通知：{{ item.payload.recipient }}</p><strong>{{ item.payload.title }}</strong><p>{{ item.payload.content }}</p><button :disabled="!canWrite" @click="noticePreview = item.payload">核对并发送</button></template><template v-else-if="item.type === 'arc'"><p>助手建议启动 ARC 精修，{{ item.payload.kp_ids?.length }} 个考点，目标 {{ item.payload.count }} 题。</p><button :disabled="!canWrite" @click="run(() => generate(item.payload))">确认启动精修</button></template></div>
          <form class="teaching-composer" @submit.prevent="run(send)"><textarea v-model="message" rows="3" aria-label="教学任务" placeholder="描述教学任务…" :disabled="busy || !meta.content_configured" /><button class="primary" :disabled="!canWrite || working || !message.trim()"><Send :size="16" />发送</button></form>
        </div>
      </div>
    </template>
    <div v-if="activeJob" class="teaching-progress" role="status"><div><strong>#{{ activeJob.id }} {{ activeJob.title }}</strong><span>{{ statusNames[activeJob.status] }} · {{ activeJob.progress }}%</span></div><progress max="100" :value="activeJob.progress" /><small>{{ activeJob.payload?.status_text || activeJob.error_message }}</small></div>
    <template v-if="view === 'tasks'">
      <form class="toolbar" @submit.prevent="run(() => loadJobs())"><input v-model="search" aria-label="搜索任务" placeholder="搜索任务标题" /><select v-model="status" aria-label="任务状态" :disabled="busy" @change="run(() => loadJobs())"><option value="">全部状态</option><option v-for="(label, value) in statusNames" :key="value" :value="value">{{ label }}</option></select><button :disabled="busy">查询</button><button type="button" :disabled="busy" @click="run(async () => { metrics = await api('pipeline.metrics'); })">查看近14天指标</button></form>
      <details v-if="metrics" open class="teaching-results"><summary>管线指标</summary><TeachingData :value="metrics" /></details>
      <div class="table-scroll"><table><thead><tr><th>任务</th><th>状态</th><th>进度</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="job in jobs.items" :key="job.id"><td>{{ job.title }}<small>#{{ job.id }}</small></td><td>{{ statusNames[job.status] }}</td><td>{{ job.progress }}%</td><td>{{ localDate(job.created_at) }}</td><td><div class="row-actions"><button :disabled="busy" @click="run(() => openJob(job))">详情</button><button v-if="['failed', 'cancelled'].includes(job.status)" :disabled="!canWrite" @click="run(() => retryTask(job))">重试</button><button v-if="!['pending', 'running'].includes(job.status)" class="danger" :disabled="!canWrite" @click="removeTask(job)">删除</button></div></td></tr><tr v-if="!jobs.items.length"><td colspan="5" class="empty">暂无任务</td></tr></tbody></table></div>
      <footer class="pagination"><span>共 {{ jobs.total }} 个任务</span><button title="上一页" :disabled="busy || jobs.page <= 1" @click="run(() => loadJobs(jobs.page - 1))"><ChevronLeft :size="17" /></button><span>{{ jobs.page }}</span><button title="下一页" :disabled="busy || jobs.page * jobs.page_size >= jobs.total" @click="run(() => loadJobs(jobs.page + 1))"><ChevronRight :size="17" /></button></footer>

    </template>
    <article v-if="current" class="teaching-results"><div class="section-heading"><h3>#{{ current.id }} {{ current.title }}</h3><button @click="current = undefined">关闭详情</button></div><p>{{ statusNames[current.status] }} · {{ current.payload?.status_text }}</p><p v-if="current.error_message" class="error">{{ current.error_message }}</p><TeachingData v-if="current.result" :value="Object.fromEntries(Object.entries(current.result).filter(([key]) => key !== 'questions'))" /><details><summary>执行参数与阶段</summary><TeachingData :value="current.payload" /></details><details v-if="current.status !== 'review' && current.result?.questions?.length"><summary>查看生成题目</summary><article v-for="(question,index) in current.result.questions" :key="index" class="teaching-question"><strong>第 {{ Number(index) + 1 }} 题 · {{ question.kp_name }}</strong><p>{{ question.question || question.text }}</p><TeachingData :value="question.options" /><p>答案：{{ question.answer }}</p><TeachingData :value="question.grading_points" /></article></details></article>
    <section v-if="candidates.length" class="teaching-review"><div class="section-heading"><h3>任务 #{{ candidateTask }} · 待审核题目 {{ candidates.length }} 道</h3><div class="actions"><button :disabled="busy" @click="selected = candidates.map((_, index) => index)">全选</button><button :disabled="busy" @click="selected = []">清空选择</button></div></div><article v-for="(question, index) in candidates" :key="index" class="teaching-question"><header><label><input v-model="selected" type="checkbox" :value="index" :disabled="busy" />第 {{ index + 1 }} 题 · {{ question.kp_name || `考点 #${question.kp_id}` }}</label><button :disabled="busy" @click="editCandidate(index)">编辑</button></header><p>{{ question.question || question.text }}</p><TeachingData v-if="question.options" :value="question.options" /><details><summary>答案与评分标准</summary><p>{{ question.answer }}</p><TeachingData :value="question.grading_points" /></details></article><div class="dialog-actions"><span>已选 {{ selected.length }} 题，入库前请核对题干、答案和考点。</span><button class="danger" :disabled="!canWrite" @click="confirmReview('reject')">拒绝结果</button><button class="primary" :disabled="!canWrite || !selected.length" @click="confirmReview('approve')">确认所选题目入库</button></div></section>

    <Dialog v-if="panel" :title="{ generate: '出题与批量初始化', student: '学情与报告', notification: '通知学员', assets: '浏览教学资产', 'notification-config': '到期提醒配置' }[panel]" :busy="busy" @close="panel = ''"><div class="dialog-body"><p v-if="error" class="error">{{ error }}</p>
      <template v-if="panel === 'generate'"><label>生成方式<select v-model="mode" :disabled="busy"><option value="quick">快速出题，人工审核</option><option value="arc">ARC 精修，人工审核</option><option value="bulk">学科批量初始化，人工审核</option></select></label><template v-if="mode !== 'bulk'"><form class="toolbar" @submit.prevent="run(findKnowledge)"><input v-model="kpQuery" aria-label="搜索考点" placeholder="搜索考点" /><button :disabled="busy">查找</button></form><div class="teaching-knowledge"><label v-for="node in knowledge" :key="node.id"><input v-if="node.level === 'kp'" v-model="selectedKps" type="checkbox" :value="node.id" :disabled="busy" /><span>{{ node.name }}<small>{{ node.subject }} · {{ node.code }} · #{{ node.id }}</small></span></label><p v-if="!knowledge.length" class="empty">没有匹配目录，试试其他关键词。</p></div><p>已选 {{ selectedKps.length }} 个考点</p></template><template v-else><label>学科<input v-model="subject" required :disabled="busy" /></label><label>限定考点编码（可选）<input v-model="kpCode" :disabled="busy" /></label><label>难度权重（JSON）<textarea v-model="difficultyDist" rows="3" :disabled="busy" /></label><label>题型权重（JSON）<textarea v-model="typeDist" rows="3" :disabled="busy" /></label></template><div class="form-grid"><label>目标题数<input v-model.number="count" type="number" min="1" :max="mode === 'bulk' ? 1000 : 100" :disabled="busy" /></label><label v-if="mode !== 'bulk'">难度<select v-model="difficulty" :disabled="busy"><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }}</option></select></label></div><div v-if="mode !== 'bulk'" class="actions"><label class="checkbox"><input v-model="types" type="checkbox" value="objective" />客观题</label><label class="checkbox"><input v-model="types" type="checkbox" value="subjective:short" />简答题</label></div><p class="notice">结果先进入待审核状态，选择题目并确认后才写入正式题库。</p></template>
      <template v-if="['student','notification'].includes(panel)"><form class="toolbar" @submit.prevent="run(findPeople)"><input v-model="studentQuery" aria-label="搜索学员" placeholder="姓名或邮箱" /><button :disabled="busy">搜索</button></form><label>学员<select v-model="studentId" :disabled="busy"><option value="" disabled>选择学员</option><option v-for="person in people" :key="person.id" :value="person.id">{{ person.name }} · {{ person.email }} · #{{ person.id }}</option></select></label><template v-if="panel === 'student'"><div class="form-grid"><label>开始时间<input v-model="dateFrom" type="datetime-local" :disabled="busy" /></label><label>结束时间<input v-model="dateTo" type="datetime-local" :disabled="busy" /></label></div><div class="actions"><button :disabled="busy || !studentId" @click="run(loadStudent)">查看学情</button><button :disabled="!canWrite || !studentId" @click="run(makeReport)">生成报告任务</button></div><div v-if="studentReport" class="teaching-results"><TeachingData :value="studentReport" /></div></template><template v-else><label>通知标题<input v-model="noticeTitle" :disabled="busy" /></label><label>通知内容<textarea v-model="noticeContent" rows="5" :disabled="busy" /></label></template></template>
      <template v-if="panel === 'notification-config' && noticeConfig"><p v-if="!noticeConfig.supported" class="notice">{{ noticeConfig.message }}</p><template v-else><label class="checkbox"><input v-model="noticeConfig.enabled" type="checkbox" :disabled="busy" />启用到期复习提醒</label><label>通知渠道<select v-model="noticeConfig.channel" :disabled="busy"><option value="email">邮件</option><option value="feishu">飞书</option></select></label><label>触发阈值（到期题数）<input v-model.number="noticeConfig.due_threshold" type="number" min="1" max="100" :disabled="busy" /></label><p class="notice">保存后由现有提醒任务按此配置执行，渠道仍需现有服务端配置支持。</p></template></template>
      <template v-if="panel === 'assets'"><form class="toolbar" @submit.prevent="run(() => loadAssets())"><select v-model="assetKind" aria-label="资产类型" :disabled="busy" @change="run(() => loadAssets())"><option value="courses">课程</option><option value="questions">正式题库</option><option value="articles">文章</option></select><input v-model="assetQuery" aria-label="搜索资产" placeholder="搜索标题或题干" /><button :disabled="busy">搜索</button></form><article v-for="item in assets.items" :key="item.id" class="teaching-question"><strong>#{{ item.id }} {{ item.title }}</strong><p>{{ item.description }}</p><details v-if="item.content || item.answer"><summary>查看内容</summary><p>{{ item.content || item.answer }}</p></details></article><p v-if="!assets.total" class="empty">暂无匹配内容</p><footer class="pagination"><span>共 {{ assets.total }} 条</span><button :disabled="busy || assets.page <= 1" @click="run(() => loadAssets(assets.page - 1))">上一页</button><span>{{ assets.page }}</span><button :disabled="busy || assets.page * assets.page_size >= assets.total" @click="run(() => loadAssets(assets.page + 1))">下一页</button></footer></template>
    </div><footer class="dialog-actions"><button :disabled="busy" @click="panel = ''">关闭</button><button v-if="panel === 'notification-config' && noticeConfig?.supported" class="primary" :disabled="!canWrite" @click="run(saveNoticeConfig)">保存提醒配置</button><button v-if="panel === 'generate'" class="primary" :disabled="!canWrite || (mode === 'bulk' ? !subject : !selectedKps.length)" @click="run(() => generate())">提交生成任务</button><button v-if="panel === 'notification'" class="primary" :disabled="!canWrite || !studentId || !noticeContent.trim()" @click="run(previewNotification)">预览接收人与内容</button></footer></Dialog>
    <Dialog v-if="noticePreview" title="确认发送通知" :busy="busy" @close="noticePreview = undefined"><div class="dialog-body"><p v-if="error" class="error">{{ error }}</p><p>接收人：{{ noticePreview.recipient }}（#{{ noticePreview.student_id }}）</p><h3>{{ noticePreview.title }}</h3><p class="teaching-preserve">{{ noticePreview.content }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="noticePreview = undefined">取消</button><button class="primary" :disabled="!canWrite" @click="run(() => sendNotification(noticePreview))">确认发送</button></footer></Dialog>
    <Dialog v-if="editing != null" title="编辑待审核题目" :busy="busy" @close="editing = undefined"><form @submit.prevent="run(async () => saveCandidate())"><div class="dialog-body"><p v-if="error" class="error">{{ error }}</p><label>题干<textarea v-model="candidateEdit.question" rows="5" required /></label><div class="form-grid"><label>考点 ID<input v-model.number="candidateEdit.kp_id" type="number" min="1" required /></label><label>题型<select v-model="candidateEdit.q_type"><option value="objective">客观题</option><option value="subjective">主观题</option></select></label><label>主观题类型<select v-model="candidateEdit.subjective_type"><option value="noun">名词解释</option><option value="short">简答</option><option value="essay">论述</option><option value="calculate">计算</option></select></label><label>难度<select v-model="candidateEdit.difficulty_level"><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }}</option></select></label></div><label>选项（JSON 数组或对象）<textarea v-model="candidateOptions" rows="5" /></label><label>参考答案<textarea v-model="candidateEdit.answer" rows="5" required /></label><label>评分要点<textarea v-model="candidateEdit.grading_points" rows="4" /></label></div><footer class="dialog-actions"><button type="button" @click="editing = undefined">取消</button><button class="primary">应用修改</button></footer></form></Dialog>
    <Dialog v-if="confirmation" :title="confirmation.title" :busy="busy" @close="confirmation = undefined"><div class="dialog-body"><p v-if="error" class="error">{{ error }}</p><p>{{ confirmation.text }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="confirmation = undefined">取消</button><button class="primary" :disabled="!canWrite" @click="run(confirmation.action)">确认</button></footer></Dialog>
  </section>
</template>

<style scoped>
.teaching-stats{display:flex;gap:30px;flex-wrap:wrap;padding:8px 0 24px;color:var(--um-muted)}.teaching-stats strong{font-size:23px;color:var(--um-ink);font-weight:600;margin-right:5px}.teaching-chat-layout{display:grid;grid-template-columns:200px minmax(0,1fr);gap:26px;margin:20px 0}.teaching-conversations{display:flex;flex-direction:column;gap:7px;max-height:560px;overflow:auto}.teaching-conversations button{text-align:left;justify-content:flex-start;white-space:normal;overflow-wrap:anywhere;border-color:transparent}.teaching-conversations button.active{background:#f0f5f4;color:var(--um-accent)}.teaching-chat{min-width:0}.teaching-messages{min-height:260px;max-height:560px;overflow:auto;padding:0 10px 16px}.teaching-message{margin:0 0 22px}.teaching-message small{color:var(--um-muted)}.teaching-message p,.teaching-question p,.teaching-confirmation p,.teaching-preserve{white-space:pre-wrap;overflow-wrap:anywhere;margin:7px 0}.teaching-message.user{background:#f5f7f7;border-radius:5px;padding:13px 16px;margin-left:30px}.teaching-composer{display:flex;gap:12px;align-items:flex-end;padding:14px;border:1px solid var(--um-line);border-radius:6px}.teaching-composer textarea{width:100%;border:0;resize:vertical;font:inherit;color:inherit;min-width:0;outline-offset:3px}.teaching-progress{padding:16px 0;margin:15px 0}.teaching-progress>div{display:flex;gap:15px;justify-content:space-between}.teaching-progress progress{display:block;width:100%;height:6px;margin:10px 0;accent-color:var(--um-accent)}.teaching-progress small{color:var(--um-muted)}.teaching-results{background:#f6f8f8;padding:18px;margin:18px 0;overflow-wrap:anywhere}.teaching-review{margin-top:32px}.teaching-question{padding:20px 0;border-bottom:1px solid var(--um-line);overflow-wrap:anywhere}.teaching-question header{display:flex;justify-content:space-between;gap:15px;align-items:center}.teaching-question header label{display:flex;gap:8px;align-items:center}.teaching-question details{margin-top:12px}.teaching-knowledge{max-height:260px;overflow:auto}.teaching-knowledge label{display:flex;gap:10px;padding:8px 0;align-items:flex-start}.teaching-knowledge small{display:block;color:var(--um-muted)}.teaching-confirmation{padding:14px;background:#fcf7e9;margin:12px 0}.teaching-success{color:var(--um-accent)}.teaching :deep(summary){cursor:pointer;color:var(--um-muted);margin:10px 0}.teaching :deep(input),.teaching :deep(select){max-width:100%}
@media(max-width:700px){.teaching-chat-layout{grid-template-columns:1fr;gap:15px}.teaching-conversations{flex-direction:row;max-height:100px;overflow:auto}.teaching-conversations button{min-width:130px}.teaching-stats{gap:15px}.teaching-message.user{margin-left:0}.teaching-composer{flex-direction:column;align-items:stretch}.teaching-progress>div{flex-direction:column;gap:4px}}
</style>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Plus, Pencil, Trash2, RefreshCw, Search, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { useTask } from './api';
import { catalogOptions, difficulties, subjectiveTypes } from './catalog';
import type { Gateway, Meta, Page, QuestionRow, QuestionDetail, KnowledgeNode } from './types';

const props = defineProps<{ api: Gateway; meta: Meta }>();
const { busy, error, run } = useTask();
const rows = ref<Page<QuestionRow>>({ items: [], total: 0, page: 1, page_size: 25 });
const nodes = ref<KnowledgeNode[]>([]);
const search = ref('');
const knowledge = ref<number | string>('');
const type = ref('');
const difficulty = ref('');
const selected = ref<number[]>([]);
const target = ref<number | ''>('');
const assignment = ref(false);
const form = ref<QuestionDetail>();
const options = ref<string[]>([]);
const rubric = ref('');
const originalRubric = ref('');
const deletion = ref<QuestionRow>();
const catalog = computed(() => catalogOptions(nodes.value));
const points = computed(() => catalog.value.filter(node => node.level === 'kp'));
const canWrite = computed(() => props.meta.content_configured && !busy.value);
async function load(page = 1) {
  rows.value = await props.api('questions.list', { page, search: search.value, knowledge_point: knowledge.value, q_type: type.value, difficulty_level: difficulty.value });
  selected.value = [];
}
onMounted(() => run(async () => { nodes.value = (await props.api('knowledge.list')).items; await load(); }));
async function edit(row?: QuestionRow) {
  const item = row ? await props.api<QuestionDetail>('questions.detail', { id: row.id }) : {
    text: '', q_type: 'objective', subjective_type: 'short', difficulty_level: 'normal',
    knowledge_point: null, options: ['', '', '', ''], correct_answer: '', grading_points: '', ai_answer: '', rubric: null,
  };
  error.value = '';
  const raw = item.options;
  options.value = Array.isArray(raw) ? [...raw] : raw ? Object.keys(raw).sort().map(key => raw[key]) : ['', '', '', ''];
  originalRubric.value = item.rubric == null ? '' : JSON.stringify(item.rubric, null, 2);
  rubric.value = originalRubric.value;
  form.value = { ...item };
}
function changeType() {
  if (!form.value) return;
  if (form.value.q_type === 'subjective' && !form.value.subjective_type) form.value.subjective_type = 'short';
  if (form.value.q_type === 'objective' && options.value.length < 2) options.value = ['', '', '', ''];
}
async function save() {
  const payload: Record<string, unknown> = { ...form.value, request_id: crypto.randomUUID() };
  if (form.value!.q_type === 'objective') payload.options = options.value;
  if (rubric.value !== originalRubric.value) {
    try { payload.rubric = rubric.value.trim() ? JSON.parse(rubric.value) : null; }
    catch { throw new Error('评分标准的 JSON 格式不正确，请核对后重试。'); }
  } else delete payload.rubric;
  await props.api('questions.save', payload);
  form.value = undefined;
  await load(rows.value.page);
}
async function remove() {
  await props.api('questions.delete', { id: deletion.value!.id, request_id: crypto.randomUUID() });
  deletion.value = undefined;
  await load(rows.value.page);
}
async function assign() {
  await props.api('questions.assign', { questions: selected.value, knowledge_point: target.value, request_id: crypto.randomUUID() });
  assignment.value = false;
  await load(rows.value.page);
}
function typeName(row: QuestionRow) { return row.q_type === 'objective' ? '客观题' : subjectiveTypes.find(item => item.value === row.subjective_type)?.label || '主观题'; }
function toggleAll(event: Event) { selected.value = (event.target as HTMLInputElement).checked ? rows.value.items.map(row => row.id) : []; }
</script>

<template>
  <section class="workspace-section" :aria-busy="busy">
    <div class="section-heading"><h2>题库 <span>{{ rows.total }}</span></h2><div class="actions"><button class="icon" title="刷新" :disabled="busy" @click="run(() => load(rows.page))"><RefreshCw :size="17" /></button><button class="primary" :disabled="!canWrite" @click="run(() => edit())"><Plus :size="17" />新增题目</button></div></div>
    <p v-if="error && !form && !deletion && !assignment" class="error" role="alert">{{ error }}</p>
    <form class="toolbar" @submit.prevent="run(() => load())">
      <label class="search-field"><Search :size="17" /><input v-model="search" aria-label="搜索题目" placeholder="搜索题目内容" /></label>
      <select v-model="knowledge" class="catalog-filter" aria-label="筛选知识目录" :disabled="busy" @change="run(() => load())"><option value="">全部知识目录</option><option value="unassigned">待归类</option><option v-for="node in catalog" :key="node.id" :value="node.id">{{ node.label }}</option></select>
      <select v-model="type" aria-label="筛选题型" :disabled="busy" @change="run(() => load())"><option value="">全部题型</option><option value="objective">客观题</option><option value="subjective">主观题</option></select>
      <select v-model="difficulty" aria-label="筛选难度" :disabled="busy" @change="run(() => load())"><option value="">全部难度</option><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }}</option></select>
      <button type="submit" :disabled="busy">查询</button>
    </form>
    <div v-if="selected.length" class="selection-bar"><span>已选 {{ selected.length }} 题</span><select v-model="target" class="catalog-filter" aria-label="目标考点"><option value="" disabled>选择目标考点</option><option v-for="node in points" :key="node.id" :value="node.id">{{ node.label }}</option></select><button :disabled="!canWrite || !target" @click="assignment = true; error = ''">批量归类</button></div>
    <div class="table-scroll"><table><thead><tr><th class="check"><input type="checkbox" aria-label="选择本页全部题目" :checked="!!rows.items.length && selected.length === rows.items.length" :disabled="busy" @change="toggleAll" /></th><th>题目内容</th><th>知识点</th><th>题型</th><th>难度</th><th>答案</th><th class="right">操作</th></tr></thead><tbody>
      <tr v-for="row in rows.items" :key="row.id"><td><input v-model="selected" type="checkbox" :value="row.id" :aria-label="`选择题目${row.id}`" :disabled="busy" /></td><td class="title-cell"><span class="question-excerpt">{{ row.text }}</span><small>#{{ row.id }}</small></td><td>{{ row.knowledge_name || '待归类' }}<small class="cell-secondary">{{ row.subject }}</small></td><td>{{ typeName(row) }}</td><td>{{ difficulties.find(item => item.value === row.difficulty_level)?.label }}</td><td :class="row.has_answer ? 'status-good' : 'warning'">{{ row.has_answer ? '已填写' : '待补充' }}</td><td><div class="row-actions"><button class="icon" title="编辑题目" :disabled="!canWrite" @click="run(() => edit(row))"><Pencil :size="16" /></button><button class="icon danger" title="删除题目" :disabled="!canWrite" @click="deletion = row; error = ''"><Trash2 :size="16" /></button></div></td></tr>
      <tr v-if="!rows.items.length"><td colspan="7" class="empty">{{ busy ? '加载中' : '暂无匹配题目' }}</td></tr>
    </tbody></table></div>
    <footer class="pagination"><span>共 {{ rows.total }} 题</span><button class="icon" title="上一页" :disabled="busy || rows.page <= 1" @click="run(() => load(rows.page - 1))"><ChevronLeft :size="17" /></button><span>{{ rows.page }}</span><button class="icon" title="下一页" :disabled="busy || rows.page * rows.page_size >= rows.total" @click="run(() => load(rows.page + 1))"><ChevronRight :size="17" /></button></footer>
    <Dialog v-if="form" :title="form.id ? '编辑题目' : '新增题目'" :busy="busy" @close="form = undefined">
      <form @submit.prevent="run(save)"><div class="dialog-body">
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <label>所属考点<select v-model="form.knowledge_point" required :disabled="busy"><option :value="null" disabled>请选择考点</option><option v-for="node in points" :key="node.id" :value="node.id">{{ node.label }}</option></select></label>
        <label>题目内容<textarea v-model="form.text" rows="5" required :disabled="busy" /></label>
        <div class="form-grid"><label>题型<select v-model="form.q_type" :disabled="busy" @change="changeType"><option value="objective">客观题</option><option value="subjective">主观题</option></select></label><label>难度<select v-model="form.difficulty_level" :disabled="busy"><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }}</option></select></label></div>
        <template v-if="form.q_type === 'objective'">
          <fieldset class="question-options" :disabled="busy"><legend>选项</legend><label v-for="(_, index) in options" :key="index">{{ String.fromCharCode(65 + index) }}<input v-model="options[index]" required /><button v-if="options.length > 2" type="button" class="icon danger" :title="`删除选项${String.fromCharCode(65 + index)}`" @click="options.splice(index, 1); form.correct_answer = ''"><Trash2 :size="15" /></button></label><button v-if="options.length < 4" type="button" @click="options.push('')"><Plus :size="16" />添加选项</button></fieldset>
          <label>标准答案<select v-model="form.correct_answer" required :disabled="busy"><option value="" disabled>请选择正确选项</option><option v-for="(_, index) in options" :key="index" :value="String.fromCharCode(65 + index)">{{ String.fromCharCode(65 + index) }}</option></select></label>
        </template>
        <template v-else>
          <label>主观题类型<select v-model="form.subjective_type" required :disabled="busy"><option v-for="item in subjectiveTypes" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
          <label>参考答案<textarea v-model="form.correct_answer" rows="5" required :disabled="busy" /></label>
          <label>得分点<textarea v-model="form.grading_points" rows="4" :required="!rubric.trim()" :disabled="busy" /></label>
          <details class="rubric-editor"><summary>结构化评分标准</summary><label>评分标准（JSON）<textarea v-model="rubric" class="mono" rows="6" :disabled="busy" /></label></details>
        </template>
        <label>解析<textarea v-model="form.ai_answer" rows="4" :disabled="busy" /></label>
      </div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="form = undefined">取消</button><button class="primary" :disabled="busy">保存题目</button></footer></form>
    </Dialog>
    <Dialog v-if="deletion" title="确认删除题目" :busy="busy" @close="deletion = undefined"><div class="dialog-body"><p>删除题目 #{{ deletion.id }}？已有业务或学习记录引用的题目无法删除。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="deletion = undefined">取消</button><button class="destructive" :disabled="busy" @click="run(remove)">确认删除</button></footer></Dialog>
    <Dialog v-if="assignment" title="确认批量归类" :busy="busy" @close="assignment = false"><div class="dialog-body"><p>将 {{ selected.length }} 道题目归入「{{ points.find(node => node.id === target)?.name }}」？</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="assignment = false">取消</button><button class="primary" :disabled="busy" @click="run(assign)">确认归类</button></footer></Dialog>
  </section>
</template>

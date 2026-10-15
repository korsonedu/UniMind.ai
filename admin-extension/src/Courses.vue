<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Plus, Pencil, Trash2, RefreshCw, Search, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { useTask } from './api';
import { upload } from './upload';
import type { Gateway, Meta, Module, Course, Page } from './types';

const props = defineProps<{ api: Gateway; meta: Meta; view: string }>();
const { busy, error, run } = useTask();
const modules = ref<Module[]>([]);
const courses = ref<Page<Course>>({ items: [], total: 0, page: 1, page_size: 25 });
const search = ref('');
const filter = ref<number | string>('');
const target = ref<number | ''>('');
const selected = ref<number[]>([]);
const courseForm = ref<Partial<Course>>();
const moduleForm = ref<Partial<Module>>();
const deletion = ref<{ kind: 'courses' | 'modules'; id: number; name: string }>();
const assignment = ref(false);
const files = ref<Record<string, File>>({});
const progress = ref<Record<string, number>>({});
const canWrite = computed(() => props.meta.content_configured && !busy.value);
const media = [
  { field: 'video_file', name: '视频', existing: 'video_name', accept: '.mp4,.m4v,.webm,.mov' },
  { field: 'cover_image', name: '封面', existing: 'cover_name', accept: '.jpg,.jpeg,.png,.gif,.webp' },
  { field: 'courseware', name: '课件', existing: 'courseware_name', accept: '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx' },
  { field: 'reference_materials', name: '参考资料', existing: 'reference_name', accept: '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx' },
] as const;
async function load(page = 1) {
  modules.value = (await props.api('modules.list')).items;
  if (props.view === 'courses') {
    courses.value = await props.api('courses.list', { page, search: search.value, module: filter.value });
    selected.value = [];
  }
}
onMounted(() => run(() => load()));
function editCourse(row?: Course) {
  error.value = '';
  files.value = {};
  progress.value = {};
  courseForm.value = row ? { ...row } : { title: '', description: '', module: null, sort_order: 0, elo_reward: 50, ai_outline_enabled: true };
}
function editModule(row?: Module) {
  error.value = '';
  moduleForm.value = row ? { ...row } : { name: '', subject: '', description: '', is_public: false, sort_order: 0 };
}
function pick(field: string, event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file) files.value[field] = file; else delete files.value[field];
  delete progress.value[field];
}
async function saveCourse() {
  const result = await props.api<Course>('courses.save', { ...courseForm.value, request_id: crypto.randomUUID() });
  courseForm.value = { ...result };
  for (const [field, file] of Object.entries(files.value)) {
    await upload(props.api, result.id, field, file, percent => { progress.value[field] = percent; });
    delete files.value[field];
  }
  courseForm.value = undefined;
  await load(courses.value.page);
}
async function saveModule() {
  await props.api('modules.save', { ...moduleForm.value, request_id: crypto.randomUUID() });
  moduleForm.value = undefined;
  await load();
}
async function remove() {
  const item = deletion.value!;
  await props.api(`${item.kind}.delete`, { id: item.id, request_id: crypto.randomUUID() });
  deletion.value = undefined;
  await load();
}
async function assign() {
  await props.api('courses.assign', { courses: selected.value, module: target.value, request_id: crypto.randomUUID() });
  assignment.value = false;
  await load(courses.value.page);
}
function toggleAll(event: Event) {
  selected.value = (event.target as HTMLInputElement).checked ? courses.value.items.map(row => row.id) : [];
}
</script>

<template>
  <section class="workspace-section" :aria-busy="busy">
    <div class="section-heading"><h2>{{ view === 'courses' ? '课程' : '模块' }} <span>{{ view === 'courses' ? courses.total : modules.length }}</span></h2><div class="actions"><button class="icon" title="刷新" :disabled="busy" @click="run(() => load(courses.page))"><RefreshCw :size="17" /></button><button class="primary" :disabled="!canWrite" @click="view === 'courses' ? editCourse() : editModule()"><Plus :size="17" />{{ view === 'courses' ? '新增课程' : '新增模块' }}</button></div></div>
    <p v-if="error && !courseForm && !moduleForm && !deletion && !assignment" class="error" role="alert">{{ error }}</p>
    <template v-if="view === 'courses'">
      <form class="toolbar" @submit.prevent="run(() => load())"><label class="search-field"><Search :size="17" /><input v-model="search" aria-label="搜索课程" placeholder="搜索课程名称" /></label><select v-model="filter" aria-label="筛选模块" :disabled="busy" @change="run(() => load())"><option value="">全部模块</option><option value="unassigned">待归类</option><option v-for="item in modules" :key="item.id" :value="item.id">{{ item.subject ? `${item.subject} / ` : '' }}{{ item.name }}</option></select><button type="submit" :disabled="busy">查询</button></form>
      <div v-if="selected.length" class="selection-bar"><span>已选 {{ selected.length }} 门</span><select v-model="target" aria-label="目标模块"><option value="" disabled>选择目标模块</option><option v-for="item in modules" :key="item.id" :value="item.id">{{ item.subject ? `${item.subject} / ` : '' }}{{ item.name }}</option></select><button :disabled="!canWrite || !target" @click="assignment = true">批量归类</button></div>
      <div class="table-scroll"><table><thead><tr><th class="check"><input type="checkbox" aria-label="选择本页全部课程" :checked="!!courses.items.length && selected.length === courses.items.length" @change="toggleAll" /></th><th>课程名称</th><th>所属模块</th><th>视频</th><th>排序</th><th class="right">操作</th></tr></thead><tbody><tr v-for="row in courses.items" :key="row.id"><td><input v-model="selected" type="checkbox" :value="row.id" :aria-label="`选择${row.title}`" /></td><td class="title-cell">{{ row.title }}<small>#{{ row.id }}</small></td><td><span :class="{ warning: !row.module }">{{ row.module_name || '待归类' }}</span></td><td><span :class="row.video_name ? 'status-good' : 'muted'">{{ row.video_name ? '已上传' : '未上传' }}</span></td><td>{{ row.sort_order }}</td><td><div class="row-actions"><button class="icon" title="编辑课程" :disabled="!canWrite" @click="editCourse(row)"><Pencil :size="16" /></button><button class="icon danger" title="删除课程" :disabled="!canWrite" @click="deletion = { kind: 'courses', id: row.id, name: row.title }; error = ''"><Trash2 :size="16" /></button></div></td></tr><tr v-if="!courses.items.length"><td colspan="6" class="empty">{{ busy ? '加载中' : '暂无课程' }}</td></tr></tbody></table></div>
      <footer class="pagination"><span>共 {{ courses.total }} 门</span><button class="icon" title="上一页" :disabled="busy || courses.page <= 1" @click="run(() => load(courses.page - 1))"><ChevronLeft :size="17" /></button><span>{{ courses.page }}</span><button class="icon" title="下一页" :disabled="busy || courses.page * courses.page_size >= courses.total" @click="run(() => load(courses.page + 1))"><ChevronRight :size="17" /></button></footer>
    </template>
    <div v-else class="table-scroll"><table><thead><tr><th>模块名称</th><th>学科</th><th>课程数</th><th>排序</th><th class="right">操作</th></tr></thead><tbody><tr v-for="row in modules" :key="row.id"><td class="title-cell">{{ row.name }}<small>{{ row.description || `#${row.id}` }}</small></td><td>{{ row.subject || '待归类学科' }}</td><td>{{ row.course_count }}</td><td>{{ row.sort_order }}</td><td><div class="row-actions"><button class="icon" title="编辑模块" :disabled="!canWrite" @click="editModule(row)"><Pencil :size="16" /></button><button class="icon danger" title="删除模块" :disabled="!canWrite" @click="deletion = { kind: 'modules', id: row.id, name: row.name }; error = ''"><Trash2 :size="16" /></button></div></td></tr><tr v-if="!modules.length"><td colspan="5" class="empty">{{ busy ? '加载中' : '暂无模块' }}</td></tr></tbody></table></div>
    <Dialog v-if="courseForm" :title="courseForm.id ? '编辑课程' : '新增课程'" :busy="busy" @close="courseForm = undefined">
      <form @submit.prevent="run(saveCourse)">
        <div class="dialog-body">
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <label>课程名称<input v-model="courseForm.title" required maxlength="200" :disabled="busy" /></label>
          <label>所属模块<select v-model="courseForm.module" required :disabled="busy"><option :value="null" disabled>请选择模块</option><option v-for="item in modules" :key="item.id" :value="item.id">{{ item.subject ? `${item.subject} / ` : '' }}{{ item.name }}</option></select></label>
          <label>课程介绍<textarea v-model="courseForm.description" rows="3" :disabled="busy" /></label>
          <div class="form-grid"><label>排序<input v-model.number="courseForm.sort_order" type="number" min="0" required :disabled="busy" /></label><label>完成奖励<input v-model.number="courseForm.elo_reward" type="number" min="0" required :disabled="busy" /></label></div>
          <label class="checkbox"><input v-model="courseForm.ai_outline_enabled" type="checkbox" :disabled="busy" />启用 AI 大纲</label>
          <fieldset class="media-fields" :disabled="busy || !meta.uploads_enabled">
            <legend>视频与附件</legend><p v-if="!meta.uploads_enabled" class="notice">OSS 文件存储尚未配置。</p>
            <label v-for="item in media" :key="item.field">{{ item.name }}<span class="filename">{{ files[item.field]?.name || String(courseForm[item.existing] || '未上传').split('/').pop() }}</span><input type="file" :accept="item.accept" @change="pick(item.field, $event)" /><progress v-if="progress[item.field] !== undefined" :value="progress[item.field]" max="100" :aria-label="`${item.name}上传进度`" /></label>
          </fieldset>
        </div>
        <footer class="dialog-actions"><span v-if="busy" role="status">保存中，请稍候</span><button type="button" :disabled="busy" @click="courseForm = undefined">取消</button><button class="primary" :disabled="busy">保存课程</button></footer>
      </form>
    </Dialog>
    <Dialog v-if="moduleForm" :title="moduleForm.id ? '编辑模块' : '新增模块'" :busy="busy" @close="moduleForm = undefined">
      <form @submit.prevent="run(saveModule)"><div class="dialog-body">
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <label>所属学科<input v-model="moduleForm.subject" list="module-subjects" required maxlength="100" :disabled="busy" /></label>
        <datalist id="module-subjects"><option v-for="subject in [...new Set(modules.map(item => item.subject).filter(Boolean))]" :key="subject" :value="subject" /></datalist>
        <label>模块名称<input v-model="moduleForm.name" required maxlength="100" :disabled="busy" /></label>
        <label>模块说明<textarea v-model="moduleForm.description" rows="4" :disabled="busy" /></label>
        <label>排序<input v-model.number="moduleForm.sort_order" type="number" min="0" required :disabled="busy" /></label>
      </div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="moduleForm = undefined">取消</button><button class="primary" :disabled="busy">保存模块</button></footer></form>
    </Dialog>
    <Dialog v-if="deletion" title="确认删除" :busy="busy" @close="deletion = undefined"><div class="dialog-body"><p>删除「{{ deletion.name }}」？此操作无法撤销。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="deletion = undefined">取消</button><button class="destructive" :disabled="busy" @click="run(remove)">确认删除</button></footer></Dialog>
    <Dialog v-if="assignment" title="确认批量归类" :busy="busy" @close="assignment = false"><div class="dialog-body"><p>将 {{ selected.length }} 门课程归入「{{ modules.find(item => item.id === target)?.name }}」？</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="assignment = false">取消</button><button class="primary" :disabled="busy" @click="run(assign)">确认归类</button></footer></Dialog>
  </section>
</template>

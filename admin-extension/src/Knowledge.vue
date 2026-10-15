<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Plus, Pencil, Trash2, RefreshCw, Search, ChevronRight, ChevronDown } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { useTask } from './api';
import { catalogOptions, levels } from './catalog';
import type { Gateway, Meta, KnowledgeNode } from './types';

const props = defineProps<{ api: Gateway; meta: Meta }>();
const { busy, error, run } = useTask();
const nodes = ref<KnowledgeNode[]>([]);
const search = ref('');
const subject = ref('');
const closed = ref<number[]>([]);
const form = ref<Partial<KnowledgeNode>>();
const deletion = ref<KnowledgeNode>();
const options = computed(() => catalogOptions(nodes.value));
const subjects = computed(() => [...new Set(nodes.value.map(node => node.subject).filter((value): value is string => !!value))]);
const visible = computed(() => options.value.filter(node =>
  (!subject.value || node.subject === subject.value) &&
  (!search.value || node.label.toLowerCase().includes(search.value.toLowerCase())) &&
  (!!search.value || !node.ancestors.some(id => closed.value.includes(id)))));
const parents = computed(() => options.value.filter(node => node.id !== form.value?.id &&
  !node.ancestors.includes(form.value?.id || 0) &&
  levels.findIndex(level => level.value === node.level) < levels.findIndex(level => level.value === form.value?.level)));
const canWrite = computed(() => props.meta.content_configured && !busy.value);
async function load() { nodes.value = (await props.api('knowledge.list')).items; }
onMounted(() => run(load));
function edit(node?: KnowledgeNode, parent?: KnowledgeNode) {
  error.value = '';
  form.value = node ? { ...node } : { name: '', code: '', level: parent ? levels[Math.min(3, levels.findIndex(level => level.value === parent.level) + 1)].value : 'sub', parent: parent?.id || null, subject: parent?.subject || '', description: '', order: 0 };
}
function changeLevel() {
  if (form.value?.parent && !parents.value.some(node => node.id === form.value?.parent)) form.value.parent = null;
}
function toggle(id: number) { closed.value = closed.value.includes(id) ? closed.value.filter(key => key !== id) : [...closed.value, id]; }
async function save() {
  await props.api('knowledge.save', { ...form.value, request_id: crypto.randomUUID() });
  form.value = undefined;
  await load();
}
async function remove() {
  await props.api('knowledge.delete', { id: deletion.value!.id, request_id: crypto.randomUUID() });
  deletion.value = undefined;
  await load();
}
</script>

<template>
  <section class="workspace-section" :aria-busy="busy">
    <div class="section-heading"><h2>知识目录 <span>{{ nodes.length }}</span></h2><div class="actions"><button class="icon" title="刷新" :disabled="busy" @click="run(load)"><RefreshCw :size="17" /></button><button class="primary" :disabled="!canWrite" @click="edit()"><Plus :size="17" />新增目录</button></div></div>
    <p v-if="error && !form && !deletion" class="error" role="alert">{{ error }}</p>
    <div class="toolbar"><label class="search-field"><Search :size="17" /><input v-model="search" aria-label="搜索知识目录" placeholder="名称或编码" /></label><select v-model="subject" aria-label="筛选学科"><option value="">全部学科</option><option v-for="item in subjects" :key="item" :value="item">{{ item }}</option></select></div>
    <div class="table-scroll"><table><thead><tr><th>知识目录</th><th>学科</th><th>层级</th><th>题目数</th><th>排序</th><th class="right">操作</th></tr></thead><tbody>
      <tr v-for="node in visible" :key="node.id">
        <td class="title-cell"><div class="catalog-name" :style="{ paddingLeft: `${Math.min(node.depth, 4) * 18}px` }"><button v-if="nodes.some(item => item.parent === node.id)" class="icon" :title="closed.includes(node.id) ? '展开目录' : '收起目录'" :aria-expanded="!closed.includes(node.id)" @click="toggle(node.id)"><component :is="closed.includes(node.id) ? ChevronRight : ChevronDown" :size="16" /></button><span v-else class="catalog-spacer" /><span>{{ node.name }}<small>{{ node.code || `#${node.id}` }}</small></span></div></td>
        <td>{{ node.subject || '待归类' }}</td><td>{{ levels.find(level => level.value === node.level)?.label }}</td><td>{{ node.question_count }}</td><td>{{ node.order }}</td>
        <td><div class="row-actions"><button v-if="node.level !== 'kp'" class="icon" title="新增下级" :disabled="!canWrite" @click="edit(undefined, node)"><Plus :size="16" /></button><button class="icon" title="编辑目录" :disabled="!canWrite" @click="edit(node)"><Pencil :size="16" /></button><button class="icon danger" title="删除目录" :disabled="!canWrite" @click="deletion = node; error = ''"><Trash2 :size="16" /></button></div></td>
      </tr><tr v-if="!visible.length"><td colspan="6" class="empty">{{ busy ? '加载中' : '暂无匹配目录' }}</td></tr>
    </tbody></table></div>
    <Dialog v-if="form" :title="form.id ? '编辑知识目录' : '新增知识目录'" :busy="busy" @close="form = undefined">
      <form @submit.prevent="run(save)"><div class="dialog-body">
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <label>名称<input v-model="form.name" required maxlength="100" :disabled="busy" /></label>
        <div class="form-grid"><label>层级<select v-model="form.level" :disabled="busy" @change="changeLevel"><option v-for="level in levels" :key="level.value" :value="level.value">{{ level.label }}</option></select></label><label>编码<input v-model="form.code" maxlength="50" :disabled="busy" /></label></div>
        <label>上级目录<select v-model="form.parent" :disabled="busy"><option :value="null">顶层目录</option><option v-for="node in parents" :key="node.id" :value="node.id">{{ node.label }}</option></select></label>
        <label>所属学科<input :value="form.parent ? nodes.find(node => node.id === form?.parent)?.subject : form.subject" list="knowledge-subjects" maxlength="100" required :disabled="busy || !!form.parent" @input="form.subject = ($event.target as HTMLInputElement).value" /></label>
        <datalist id="knowledge-subjects"><option v-for="item in subjects" :key="item" :value="item" /></datalist>
        <label>说明<textarea v-model="form.description" rows="4" :disabled="busy" /></label>
        <label>排序<input v-model.number="form.order" type="number" min="0" required :disabled="busy" /></label>
      </div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="form = undefined">取消</button><button class="primary" :disabled="busy">保存目录</button></footer></form>
    </Dialog>
    <Dialog v-if="deletion" title="确认删除目录" :busy="busy" @close="deletion = undefined"><div class="dialog-body"><p>删除「{{ deletion.name }}」？有下级节点、内容或学习记录引用的目录无法删除。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="deletion = undefined">取消</button><button class="destructive" :disabled="busy" @click="run(remove)">确认删除</button></footer></Dialog>
  </section>
</template>

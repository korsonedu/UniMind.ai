<script setup lang="ts">
import { ref } from 'vue';
import Dialog from './Dialog.vue';
import { useTask } from './api';
import { cohortStates, type Cohort, type Gateway } from './types';
const props = defineProps<{ api: Gateway; cohorts: Cohort[] }>();
const emit = defineEmits<{ saved: [] }>();
const { busy, error, run } = useTask();
const form = ref<Partial<Cohort>>();
function edit(row?: Cohort) { error.value = ''; form.value = row ? { ...row } : { name: '', starts_on: '', ends_on: '', exam_date: null, is_active: false }; }
async function save() {
  await props.api('cohorts.save', { ...form.value, exam_date: form.value?.exam_date || null, request_id: crypto.randomUUID() });
  form.value = undefined; emit('saved');
}
</script>

<template>
  <div class="section-heading"><h3>学员批次</h3><button :disabled="busy" @click="edit()">新建批次</button></div>
  <p class="muted">多个批次可同时存在，学员按绑定批次的服务日期获得课程权益。目标届别与实际考试日期分别设置。</p>
  <div class="table-scroll"><table><thead><tr><th>批次</th><th>考试日期</th><th>服务日期（上海）</th><th>状态</th><th>操作</th></tr></thead><tbody>
    <tr v-for="row in cohorts" :key="row.id"><td>{{ row.name }}<small>{{ row.target_year }}届</small></td><td>{{ row.exam_date || '待设置' }}</td><td>{{ row.starts_on }} 至 {{ row.ends_on }}</td><td>{{ cohortStates[row.state] }}</td><td><button :disabled="busy" @click="edit(row)">编辑</button></td></tr>
    <tr v-if="!cohorts.length"><td colspan="5" class="empty">尚未配置批次，不自动指定考试年度。</td></tr>
  </tbody></table></div>
  <Dialog v-if="form" :title="form.id ? '编辑学员批次' : '新建学员批次'" :busy="busy" @close="form = undefined">
    <form @submit.prevent="run(save)"><div class="dialog-body">
      <p class="notice">修改批次会影响已绑定学员的后续访问，历史记录与当周已用次数保留。</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <label>批次名称<input v-model="form.name" required maxlength="100" :disabled="busy" /></label>
      <label>目标届别<input v-model.number="form.target_year" type="number" min="1" max="32767" required :disabled="busy" /></label>
      <label>实际考试日期（可暂不设置）<input v-model="form.exam_date" type="date" :disabled="busy" /></label>
      <label>服务开始日期（上海）<input v-model="form.starts_on" type="date" required :disabled="busy" /></label>
      <label>服务结束日期（含当日）<input v-model="form.ends_on" type="date" :min="form.starts_on" required :disabled="busy" /></label>
      <label class="checkbox"><input v-model="form.is_active" type="checkbox" :disabled="busy" />启用批次</label>
    </div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="form = undefined">取消</button><button class="primary" :disabled="busy">保存批次</button></footer></form>
  </Dialog>
</template>

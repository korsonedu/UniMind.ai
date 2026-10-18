<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { RefreshCw, Search, ChevronLeft, ChevronRight, ArrowUpRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { useTask, localDate } from './api';
import type { Gateway, Page, Person, Grant, AIUsage } from './types';
const props = defineProps<{ api: Gateway }>();
const { busy, error, run } = useTask();
const people = ref<Page<Person>>({ items: [], total: 0, page: 1, page_size: 25 });
const search = ref('');
const notice = ref('');
type Student = Person & { ai_usage: AIUsage; grants: Grant[]; feature_options: { key: string; name: string }[]; enabled_features: string[] };
const student = ref<Student>();
const accessForm = ref<string[]>();
const statusChange = ref<boolean>();
const revoke = ref<Grant>();
async function load(page = 1) { people.value = await props.api('students.list', { page, search: search.value }); }
async function openStudent(id: number) { error.value = ''; student.value = await props.api('students.detail', { id }); }
onMounted(() => run(() => load()));
async function saveStatus() {
  const id = student.value!.id;
  await props.api('students.status.save', { id, is_course_student: statusChange.value, request_id: crypto.randomUUID() });
  statusChange.value = undefined;
  await openStudent(id); await load(people.value.page); notice.value = '学员状态已更新。';
}
async function saveAccess() {
  await props.api('students.access.save', { id: student.value!.id, enabled_features: accessForm.value, request_id: crypto.randomUUID() });
  accessForm.value = undefined; await openStudent(student.value!.id); notice.value = '功能权限已保存。';
}
async function revokeGrant() {
  await props.api('grants.revoke', { id: revoke.value!.id, request_id: crypto.randomUUID() });
  revoke.value = undefined; await openStudent(student.value!.id);
}
const sourceNames: Record<string, string> = { payment: '历史购买', course: '课程配套', admin: '管理员赠送' };
function grantStatus(grant: Grant) { return grant.revoked ? '已撤销' : new Date(grant.expires_at).getTime() <= Date.now() ? '已到期' : '生效中'; }
</script>

<template>
  <section class="workspace-section" :aria-busy="busy">
    <div class="section-heading"><h2>学员 <span>{{ people.total }}</span></h2><button class="icon" title="刷新" :disabled="busy" @click="run(() => load(people.page))"><RefreshCw :size="17" /></button></div>
    <p v-if="notice && !student" class="notice" role="status">{{ notice }}</p>
    <p v-if="error && !student" class="error" role="alert">{{ error }}</p>
    <form class="toolbar" @submit.prevent="run(() => load())"><label class="search-field"><Search :size="17" /><input v-model="search" aria-label="搜索学员" placeholder="邮箱、用户名或昵称" /></label><button :disabled="busy">查询</button></form>
    <div class="table-scroll"><table><thead><tr><th>学员</th><th>邮箱</th><th>服务状态</th><th>账号状态</th><th class="right">操作</th></tr></thead><tbody>
      <tr v-for="row in people.items" :key="row.id"><td class="title-cell">{{ row.nickname || row.username }}<small>#{{ row.id }} · {{ row.username }}</small></td><td>{{ row.email || '未填写' }}<small v-if="!row.email_verified" class="cell-secondary">邮箱未验证</small></td><td>{{ row.is_admin ? '管理员' : row.is_course_student ? '课程学员' : '非课程学员' }}</td><td>{{ row.is_active ? '正常' : '已停用' }}</td><td><div class="row-actions"><button :disabled="busy" @click="run(() => openStudent(row.id))">查看详情<ArrowUpRight :size="15" /></button></div></td></tr>
      <tr v-if="!people.items.length"><td colspan="5" class="empty">{{ busy ? '加载中' : '暂无匹配学员' }}</td></tr>
    </tbody></table></div>
    <footer class="pagination"><span>共 {{ people.total }} 人</span><button class="icon" title="上一页" :disabled="busy || people.page <= 1" @click="run(() => load(people.page - 1))"><ChevronLeft :size="17" /></button><span>{{ people.page }}</span><button class="icon" title="下一页" :disabled="busy || people.page * people.page_size >= people.total" @click="run(() => load(people.page + 1))"><ChevronRight :size="17" /></button></footer>
    <Dialog v-if="student" :title="student.nickname || student.username" :busy="busy" @close="student = undefined">
      <div class="dialog-body student-detail">
        <div class="student-summary"><div><span class="muted">邮箱</span><p>{{ student.email || '未填写' }}</p></div><div><span class="muted">服务状态</span><p>{{ student.is_admin ? '管理员' : student.is_course_student ? '课程学员' : '非课程学员' }}</p></div><div><span class="muted">本周已用 / 基础额度</span><p>{{ student.ai_usage.used }} / {{ student.ai_usage.unlimited ? '不限量' : student.ai_usage.limit ?? '待配置' }}</p></div><div><span class="muted">下次恢复</span><p>{{ localDate(student.ai_usage.resets_at) }}</p></div></div>
        <p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="error && statusChange === undefined && !accessForm && !revoke" class="error" role="alert">{{ error }}</p>
        <div v-if="!student.is_admin" class="actions"><button :disabled="busy" @click="statusChange = !student!.is_course_student; error = ''">{{ student.is_course_student ? '调整为非课程学员' : '设为课程学员' }}</button></div>
        <p class="muted">课程在线下开通。学员状态由管理员手动调整，购买 AI 加量不会改变此状态。</p>
        <div class="section-heading"><h3>已开通功能</h3><button :disabled="busy || student.is_admin" @click="accessForm = [...student!.enabled_features]; error = ''">配置权限</button></div>
        <p>{{ student.feature_options.filter(item => student?.enabled_features.includes(item.key)).map(item => item.name).join('、') || '暂无已开通功能' }}</p>
        <p v-if="!student.is_course_student && !student.is_admin" class="muted">非课程学员目前仅可使用小宇问答，其他学习功能需要课程学员状态。</p>
        <h3>历史服务记录</h3>
        <div class="table-scroll"><table><thead><tr><th>服务</th><th>来源</th><th>到期时间</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in student.grants" :key="row.id"><td>{{ row.snapshot.name }}</td><td>{{ sourceNames[row.source] || row.source }}</td><td>{{ localDate(row.expires_at) }}</td><td>{{ grantStatus(row) }}</td><td><button :disabled="busy || row.revoked" class="danger" @click="revoke = row; error = ''">撤销</button></td></tr><tr v-if="!student.grants.length"><td colspan="5" class="empty">暂无历史服务记录</td></tr></tbody></table></div>
      </div><footer class="dialog-actions"><button :disabled="busy" @click="student = undefined">关闭</button></footer>
    </Dialog>
    <Dialog v-if="statusChange !== undefined && student" title="确认调整学员状态" :busy="busy" @close="statusChange = undefined"><div class="dialog-body"><p>将 {{ student.nickname || student.username }} 调整为{{ statusChange ? '课程学员' : '非课程学员' }}？</p><p>{{ statusChange ? '按课程学员规则开放学习服务。' : '后续访问恢复为小宇体验范围，保留历史学习记录。' }}当周已用次数保留。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="statusChange = undefined">取消</button><button class="primary" :disabled="busy" @click="run(saveStatus)">确认调整</button></footer></Dialog>
    <Dialog v-if="accessForm && student" title="用户功能权限" :busy="busy" @close="accessForm = undefined"><form @submit.prevent="run(saveAccess)"><div class="dialog-body"><p>{{ student.nickname || student.username }} · {{ student.email }}</p><p v-if="!student.is_course_student" class="notice">非课程学员仍受体验范围限制，勾选其他功能不会越过学员状态。</p><p v-if="error" class="error" role="alert">{{ error }}</p><label v-for="item in student.feature_options" :key="item.key" class="checkbox"><input v-model="accessForm" type="checkbox" :value="item.key" :disabled="busy" />{{ item.name }}</label></div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="accessForm = undefined">取消</button><button class="primary" :disabled="busy">保存权限</button></footer></form></Dialog>
    <Dialog v-if="revoke && student" title="确认撤销历史服务" :busy="busy" @close="revoke = undefined"><div class="dialog-body"><p>撤销 {{ student.email }} 的「{{ revoke.snapshot.name }}」？历史记录保留，显式设置的学员状态不受这次撤销影响。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="revoke = undefined">取消</button><button class="destructive" :disabled="busy" @click="run(revokeGrant)">确认撤销</button></footer></Dialog>
  </section>
</template>

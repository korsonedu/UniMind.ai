<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { Plus, Pencil, Search, ChevronLeft, ChevronRight, RefreshCw, ArrowUpRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { useTask, localDate } from './api';
import type { Gateway, Product, Person, Grant, Module, Page } from './types';

const props = defineProps<{ api: Gateway; view: string }>();
const { busy, error, run } = useTask();
const people = ref<Page<Person>>({ items: [], total: 0, page: 1, page_size: 25 });
const products = ref<Product[]>([]);
const modules = ref<Module[]>([]);
const search = ref('');
const student = ref<Person & { ai_usage: { used: number; limit: number }; grants: Grant[];
  feature_options: { key: string; name: string }[]; enabled_features: string[] }>();
const accessForm = ref<string[]>();
const productForm = ref<Partial<Product>>();
const price = ref(0);
const grantForm = ref<{ product: number | ''; source: string; request_id: string }>();
const grantLocked = ref(false);
const confirmation = ref(false);
const revoke = ref<Grant>();
async function load(page = 1) {
  products.value = (await props.api('products.list')).items;
  if (props.view === 'people') people.value = await props.api('students.list', { page, search: search.value });
  else modules.value = (await props.api('modules.list')).items;
}
onMounted(() => run(() => load()));
async function openStudent(id: number) { student.value = await props.api('students.detail', { id }); }
function editAccess() { error.value = ''; accessForm.value = [...student.value!.enabled_features]; }
async function saveAccess() {
  const id = student.value!.id;
  await props.api('students.access.save', { id, enabled_features: accessForm.value, request_id: crypto.randomUUID() });
  accessForm.value = undefined;
  await openStudent(id);
}
function editProduct(row?: Product) {
  error.value = '';
  productForm.value = row ? { ...row, modules: [...row.modules] } : { name: '', description: '', price_cents: 0, duration_days: 30, monthly_ai_calls: 100, modules: [], is_active: false, sort_order: 0 };
  price.value = (row?.price_cents || 0) / 100;
}
async function saveProduct() {
  await props.api('products.save', { ...productForm.value, price_cents: Math.round(price.value * 100), request_id: crypto.randomUUID() });
  productForm.value = undefined;
  await load();
}
function openGrant() {
  error.value = '';
  grantLocked.value = false;
  grantForm.value = { product: '', source: 'course', request_id: crypto.randomUUID() };
}
async function grant() {
  grantLocked.value = true;
  await props.api('grants.create', { ...grantForm.value, user: student.value!.id });
  confirmation.value = false;
  grantForm.value = undefined;
  await openStudent(student.value!.id);
}
async function revokeGrant() {
  await props.api('grants.revoke', { id: revoke.value!.id, request_id: crypto.randomUUID() });
  revoke.value = undefined;
  await openStudent(student.value!.id);
}
const sourceNames: Record<string, string> = { payment: '个人购买', course: '课程配套', admin: '管理员赠送' };
function status(grant: Grant) { return grant.revoked ? '已撤销' : new Date(grant.expires_at).getTime() <= Date.now() ? '已到期' : '生效中'; }
</script>

<template>
  <section class="workspace-section" :aria-busy="busy">
    <div class="section-heading"><h2>{{ view === 'people' ? '学员' : '学习服务' }} <span>{{ view === 'people' ? people.total : products.length }}</span></h2><div class="actions"><button class="icon" title="刷新" :disabled="busy" @click="run(() => load(people.page))"><RefreshCw :size="17" /></button><button v-if="view === 'products'" class="primary" :disabled="busy" @click="editProduct()"><Plus :size="17" />新增服务</button></div></div>
    <p v-if="error && !student && !productForm" class="error" role="alert">{{ error }}</p>
    <template v-if="view === 'people'">
      <form class="toolbar" @submit.prevent="run(() => load())"><label class="search-field"><Search :size="17" /><input v-model="search" aria-label="搜索学员" placeholder="邮箱、用户名或昵称" /></label><button :disabled="busy">查询</button></form>
      <div class="table-scroll"><table><thead><tr><th>学员</th><th>邮箱</th><th>邮箱验证</th><th>账号状态</th><th class="right">操作</th></tr></thead><tbody><tr v-for="row in people.items" :key="row.id"><td class="title-cell">{{ row.nickname || row.username }}<small>#{{ row.id }} · {{ row.username }}</small></td><td>{{ row.email || '未填写' }}</td><td :class="row.email_verified ? 'status-good' : 'warning'">{{ row.email_verified ? '已验证' : '未验证' }}</td><td>{{ row.is_active ? '正常' : '已停用' }}</td><td><div class="row-actions"><button :disabled="busy" @click="run(() => openStudent(row.id))">查看服务<ArrowUpRight :size="15" /></button></div></td></tr><tr v-if="!people.items.length"><td colspan="5" class="empty">{{ busy ? '加载中' : '暂无学员' }}</td></tr></tbody></table></div>
      <footer class="pagination"><span>共 {{ people.total }} 人</span><button class="icon" title="上一页" :disabled="busy || people.page <= 1" @click="run(() => load(people.page - 1))"><ChevronLeft :size="17" /></button><span>{{ people.page }}</span><button class="icon" title="下一页" :disabled="busy || people.page * people.page_size >= people.total" @click="run(() => load(people.page + 1))"><ChevronRight :size="17" /></button></footer>
    </template>
    <div v-else class="table-scroll"><table><thead><tr><th>服务名称</th><th>售价</th><th>有效期</th><th>每月 AI 次数</th><th>销售状态</th><th class="right">操作</th></tr></thead><tbody><tr v-for="row in products" :key="row.id"><td class="title-cell">{{ row.name }}<small>#{{ row.id }}</small></td><td>¥{{ (row.price_cents / 100).toFixed(2) }}</td><td>{{ row.duration_days }} 天</td><td>{{ row.monthly_ai_calls }}</td><td :class="row.is_active ? 'status-good' : 'muted'">{{ row.is_active ? '已上架' : '未上架' }}</td><td><div class="row-actions"><button class="icon" title="编辑服务" :disabled="busy" @click="editProduct(row)"><Pencil :size="16" /></button></div></td></tr><tr v-if="!products.length"><td colspan="6" class="empty">{{ busy ? '加载中' : '暂无学习服务' }}</td></tr></tbody></table></div>
    <Dialog v-if="productForm" :title="productForm.id ? '编辑学习服务' : '新增学习服务'" :busy="busy" @close="productForm = undefined"><form @submit.prevent="run(saveProduct)"><div class="dialog-body"><p v-if="error" class="error" role="alert">{{ error }}</p><label>服务名称<input v-model="productForm.name" required maxlength="100" /></label><label>服务说明<textarea v-model="productForm.description" rows="3" /></label><div class="form-grid"><label>售价（元）<input v-model.number="price" type="number" step="0.01" min="0" required /></label><label>有效期（天）<input v-model.number="productForm.duration_days" type="number" min="1" required /></label><label>每月 AI 次数<input v-model.number="productForm.monthly_ai_calls" type="number" min="0" required /></label><label>排序<input v-model.number="productForm.sort_order" type="number" min="0" required /></label></div><fieldset><legend>关联模块</legend><div class="module-choices"><label v-for="item in modules" :key="item.id" class="checkbox"><input v-model="productForm.modules" type="checkbox" :value="item.id" />{{ item.name }}</label><p v-if="!modules.length" class="muted">暂无模块</p></div></fieldset><label class="checkbox"><input v-model="productForm.is_active" type="checkbox" />上架销售</label></div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="productForm = undefined">取消</button><button class="primary" :disabled="busy">保存服务</button></footer></form></Dialog>
    <Dialog v-if="student" :title="student.nickname || student.username" :busy="busy" @close="student = undefined">
      <div class="dialog-body student-detail">
        <div class="student-summary"><div><span class="muted">邮箱</span><p>{{ student.email || '未填写' }}</p></div><div><span class="muted">本月 AI 用量</span><p>{{ student.ai_usage.used }} / {{ student.ai_usage.limit }}</p></div></div>
        <div class="section-heading"><h3>已开通功能</h3><button :disabled="busy" @click="editAccess">配置权限</button></div>
        <p>{{ student.feature_options.filter(item => student?.enabled_features.includes(item.key)).map(item => item.name).join('、') || '暂无已开通功能' }}</p>
        <p v-if="!student.email_verified || !student.is_active" class="notice">账号须正常且邮箱已验证，才能发放服务。</p>
        <p v-if="error && !grantForm && !revoke && !accessForm" class="error" role="alert">{{ error }}</p>
        <div class="section-heading"><h3>服务记录</h3><button class="primary" :disabled="busy || !student.email_verified || !student.is_active || !products.length" @click="openGrant"><Plus :size="16" />发放服务</button></div>
        <div class="table-scroll"><table><thead><tr><th>服务</th><th>来源</th><th>到期时间</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in student.grants" :key="row.id"><td>{{ row.snapshot.name }}</td><td>{{ sourceNames[row.source] || row.source }}</td><td>{{ localDate(row.expires_at) }}</td><td>{{ status(row) }}</td><td><button :disabled="busy || row.revoked" class="danger" @click="revoke = row; error = ''">撤销</button></td></tr><tr v-if="!student.grants.length"><td colspan="5" class="empty">暂无服务记录</td></tr></tbody></table></div>
      </div><footer class="dialog-actions"><button :disabled="busy" @click="student = undefined">关闭</button></footer>
    </Dialog>
    <Dialog v-if="accessForm && student" title="用户功能权限" :busy="busy" @close="accessForm = undefined">
      <form @submit.prevent="run(saveAccess)"><div class="dialog-body">
        <p>{{ student.nickname || student.username }} · {{ student.email }}</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <label v-for="item in student.feature_options" :key="item.key" class="checkbox"><input v-model="accessForm" type="checkbox" :value="item.key" :disabled="busy" />{{ item.name }}</label>
      </div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="accessForm = undefined">取消</button><button class="primary" :disabled="busy">保存权限</button></footer></form>
    </Dialog>
    <Dialog v-if="grantForm && student" title="发放学习服务" :busy="busy" @close="grantForm = undefined"><form @submit.prevent="confirmation = true"><div class="dialog-body"><p>{{ student.nickname || student.username }} · {{ student.email }}</p><label>学习服务<select v-model="grantForm.product" required :disabled="grantLocked"><option value="" disabled>请选择服务</option><option v-for="item in products" :key="item.id" :value="item.id">{{ item.name }} · {{ item.duration_days }} 天</option></select></label><label>发放来源<select v-model="grantForm.source" :disabled="grantLocked"><option value="course">课程配套</option><option value="admin">管理员赠送</option></select></label><p v-if="error && !confirmation" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="grantForm = undefined">取消</button><button class="primary" :disabled="busy">核对发放</button></footer></form></Dialog>
    <Dialog v-if="confirmation && grantForm && student" title="确认发放" :busy="busy" @close="confirmation = false"><div class="dialog-body"><p>向 {{ student.email }} 发放「{{ products.find(item => item.id === grantForm?.product)?.name }}」，有效期 {{ products.find(item => item.id === grantForm?.product)?.duration_days }} 天。</p><p>同一服务仍在有效期内时，将在原到期时间后顺延。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="confirmation = false">返回</button><button class="primary" :disabled="busy" @click="run(grant)">确认发放</button></footer></Dialog>
    <Dialog v-if="revoke && student" title="确认撤销服务" :busy="busy" @close="revoke = undefined"><div class="dialog-body"><p>撤销 {{ student.email }} 的「{{ revoke.snapshot.name }}」？撤销后该条服务记录立即失效。</p><p v-if="error" class="error" role="alert">{{ error }}</p></div><footer class="dialog-actions"><button :disabled="busy" @click="revoke = undefined">取消</button><button class="destructive" :disabled="busy" @click="run(revokeGrant)">确认撤销</button></footer></Dialog>
  </section>
</template>

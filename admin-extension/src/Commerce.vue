<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { Plus, Pencil, RefreshCw, Search, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { useTask, localDate } from './api';
import type { Gateway, AddonProduct, Page } from './types';
const props = defineProps<{ api: Gateway; view: 'products' | 'orders' | 'settings' }>();
const { busy, error, run } = useTask();
const products = ref<AddonProduct[]>([]);
const form = ref<AddonProduct>();
const price = ref<number | ''>('');
const notice = ref('');
const search = ref('');
const status = ref('');
const statusNames: Record<string, string> = { paid: '已支付', pending: '待支付', refunded: '已退款', expired: '已过期', cancelled: '已取消' };
type Order = { id: number; username: string; email: string; product_name: string; amount_cents: number; status: string; created_at: string };
const orders = ref<Page<Order>>({ items: [], total: 0, page: 1, page_size: 25 });
const quota = ref<{ experience_calls: number | null; course_calls: number | null }>();
const quotaForm = ref<{ experience_calls: number | null; course_calls: number | null }>();
type BotConfig = { id: number; name: string; bot_type: string; is_active: boolean; personality: Record<string, string>; prompt_template: string };
const bots = ref<BotConfig[]>([]);
const botForm = ref<BotConfig>();
function nullable(value: unknown) { return value === '' || value == null ? null : Number(value); }
async function load(page = 1) {
  if (props.view === 'products') products.value = (await props.api('addons.list')).items;
  else if (props.view === 'orders') orders.value = await props.api('orders.list', { page, search: search.value, status: status.value });
  else { quota.value = await props.api('quota.get'); bots.value = (await props.api('ai.config.get')).items; }
}
onMounted(() => run(() => load()));
function editProduct(row?: AddonProduct) {
  error.value = '';
  form.value = row ? { ...row } : { name: '', description: '', price_cents: null, ai_calls: null, validity_days: null, is_active: false, sort_order: 0 };
  price.value = row?.price_cents == null ? '' : row.price_cents / 100;
}
async function saveProduct() {
  await props.api('addons.save', { ...form.value, ai_calls: nullable(form.value!.ai_calls), validity_days: nullable(form.value!.validity_days), price_cents: price.value === '' ? null : Math.round(Number(price.value) * 100), request_id: crypto.randomUUID() });
  form.value = undefined; await load(); notice.value = 'AI 加量商品已保存。';
}
async function saveQuota() {
  await props.api('quota.save', { experience_calls: nullable(quotaForm.value!.experience_calls), course_calls: nullable(quotaForm.value!.course_calls), request_id: crypto.randomUUID() });
  quotaForm.value = undefined; await load(); notice.value = '每周额度已保存。';
}
function editBot(bot: BotConfig) { error.value = ''; botForm.value = { ...bot, personality: { ...bot.personality } }; }
async function saveBot() {
  await props.api('ai.config.save', { ...botForm.value, request_id: crypto.randomUUID() });
  botForm.value = undefined; await load(); notice.value = 'AI 配置已保存。';
}
</script>

<template>
  <section class="workspace-section" :aria-busy="busy">
    <div class="section-heading"><h2>{{ view === 'products' ? 'AI 加量' : view === 'orders' ? '订单' : 'AI 配置' }} <span v-if="view === 'products'">{{ products.length }}</span><span v-if="view === 'orders'">{{ orders.total }}</span></h2><div class="actions"><button class="icon" title="刷新" :disabled="busy" @click="run(() => load(orders.page))"><RefreshCw :size="17" /></button><button v-if="view === 'products'" class="primary" :disabled="busy" @click="editProduct()"><Plus :size="17" />新增加量商品</button></div></div>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="error && !form && !quotaForm && !botForm" class="error" role="alert">{{ error }}</p>
    <template v-if="view === 'products'">
      <p class="muted">只销售额外问答次数。课程在线下收费，加量不改变学员状态或开放课程权限。</p>
      <div class="table-scroll"><table><thead><tr><th>商品名称</th><th>售价</th><th>问答次数</th><th>有效期</th><th>状态</th><th class="right">操作</th></tr></thead><tbody><tr v-for="row in products" :key="row.id"><td class="title-cell">{{ row.name }}<small>{{ row.description || `#${row.id}` }}</small></td><td>{{ row.price_cents == null ? '待确定' : `¥${(row.price_cents / 100).toFixed(2)}` }}</td><td>{{ row.ai_calls ?? '待确定' }}</td><td>{{ row.validity_days == null ? '待确定' : `${row.validity_days} 天` }}</td><td>{{ row.is_active ? '已上架' : row.configured ? '未上架' : '待配置' }}</td><td><div class="row-actions"><button class="icon" title="编辑加量商品" :disabled="busy" @click="editProduct(row)"><Pencil :size="16" /></button></div></td></tr><tr v-if="!products.length"><td colspan="6" class="empty">{{ busy ? '加载中' : '尚未配置 AI 加量商品' }}</td></tr></tbody></table></div>
    </template>
    <template v-else-if="view === 'orders'">
      <form class="toolbar" @submit.prevent="run(() => load())"><label class="search-field"><Search :size="17" /><input v-model="search" placeholder="邮箱或用户名" aria-label="搜索订单" /></label><select v-model="status" aria-label="订单状态" :disabled="busy" @change="run(() => load())"><option value="">全部状态</option><option v-for="(name, key) in statusNames" :key="key" :value="key">{{ name }}</option></select><button :disabled="busy">查询</button></form>
      <div class="table-scroll"><table><thead><tr><th>订单</th><th>用户</th><th>金额</th><th>状态</th><th>创建时间</th></tr></thead><tbody><tr v-for="row in orders.items" :key="row.id"><td class="title-cell">{{ row.product_name }}<small>#{{ row.id }}</small></td><td>{{ row.email || row.username }}</td><td>¥{{ (row.amount_cents / 100).toFixed(2) }}</td><td>{{ statusNames[row.status] || row.status }}</td><td>{{ localDate(row.created_at) }}</td></tr><tr v-if="!orders.items.length"><td colspan="5" class="empty">{{ busy ? '加载中' : '暂无匹配订单' }}</td></tr></tbody></table></div>
      <footer class="pagination"><span>共 {{ orders.total }} 条</span><button class="icon" title="上一页" :disabled="busy || orders.page <= 1" @click="run(() => load(orders.page - 1))"><ChevronLeft :size="17" /></button><span>{{ orders.page }}</span><button class="icon" title="下一页" :disabled="busy || orders.page * orders.page_size >= orders.total" @click="run(() => load(orders.page + 1))"><ChevronRight :size="17" /></button></footer>
    </template>
    <template v-else>
      <div class="section-heading"><h3>每周问答额度</h3><button :disabled="busy || !quota" @click="quotaForm = { ...quota! }; error = ''">配置额度</button></div>
      <div v-if="quota" class="student-summary"><div><span class="muted">非课程学员</span><p>{{ quota.experience_calls ?? '待配置' }}{{ quota.experience_calls == null ? '' : ' 次／周' }}</p></div><div><span class="muted">课程学员</span><p>{{ quota.course_calls ?? '待配置' }}{{ quota.course_calls == null ? '' : ' 次／周' }}</p></div></div>
      <p class="muted">每周一 00:00（上海时间）恢复。基础额度不累计；管理员不限量。未配置的次数不自动沿用旧月额度。</p>
      <div class="section-heading"><h3>AI 助手</h3></div>
      <div class="table-scroll"><table><thead><tr><th>助手</th><th>类型</th><th>状态</th><th>提示词来源</th><th class="right">操作</th></tr></thead><tbody><tr v-for="bot in bots" :key="bot.id"><td class="title-cell">{{ bot.name }}</td><td>{{ bot.bot_type === 'planner' ? '小宇' : '教学工作台' }}</td><td>{{ bot.is_active ? '启用' : '停用' }}</td><td>{{ bot.prompt_template }}</td><td><div class="row-actions"><button class="icon" title="编辑 AI 配置" :disabled="busy" @click="editBot(bot)"><Pencil :size="16" /></button></div></td></tr><tr v-if="!bots.length"><td colspan="5" class="empty">{{ busy ? '加载中' : '尚未配置助手' }}</td></tr></tbody></table></div>
    </template>
    <Dialog v-if="form" :title="form.id ? '编辑 AI 加量' : '新增 AI 加量'" :busy="busy" @close="form = undefined"><form @submit.prevent="run(saveProduct)"><div class="dialog-body"><p v-if="error" class="error" role="alert">{{ error }}</p><label>商品名称<input v-model="form.name" required maxlength="100" :disabled="busy" /></label><label>商品说明<textarea v-model="form.description" rows="3" :disabled="busy" /></label><div class="form-grid"><label>售价（元）<input v-model.number="price" type="number" step="0.01" min="0.01" :disabled="busy" placeholder="待确定" /></label><label>问答次数<input v-model.number="form.ai_calls" type="number" min="1" :disabled="busy" placeholder="待确定" /></label><label>有效期（天）<input v-model.number="form.validity_days" type="number" min="1" :disabled="busy" placeholder="待确定" /></label><label>排序<input v-model.number="form.sort_order" type="number" min="0" required :disabled="busy" /></label></div><p class="muted">价格、次数和有效期明确后才可上架。已购次数在有效期内保留，不随每周基础额度恢复而再次发放。</p><label class="checkbox"><input v-model="form.is_active" type="checkbox" :disabled="busy" />上架销售</label></div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="form = undefined">取消</button><button class="primary" :disabled="busy">保存商品</button></footer></form></Dialog>
    <Dialog v-if="quotaForm" title="配置每周额度" :busy="busy" @close="quotaForm = undefined"><form @submit.prevent="run(saveQuota)"><div class="dialog-body"><p v-if="error" class="error" role="alert">{{ error }}</p><label>非课程学员（次／周）<input v-model.number="quotaForm.experience_calls" type="number" min="0" :disabled="busy" /></label><label>课程学员（次／周）<input v-model.number="quotaForm.course_calls" type="number" min="1" :disabled="busy" /></label><p class="muted">课程学员额度须高于非课程学员。两项均留空表示暂未配置，历史用量不会被清零。</p></div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="quotaForm = undefined">取消</button><button class="primary" :disabled="busy">保存额度</button></footer></form></Dialog>
    <Dialog v-if="botForm" title="编辑 AI 配置" :busy="busy" @close="botForm = undefined"><form @submit.prevent="run(saveBot)"><div class="dialog-body"><p v-if="error" class="error" role="alert">{{ error }}</p><label>名称<input v-model="botForm.name" required maxlength="100" :disabled="busy" /></label><label>教学风格<input v-model="botForm.personality.teaching_style" maxlength="200" :disabled="busy" /></label><label>语气<input v-model="botForm.personality.tone" maxlength="100" :disabled="busy" /></label><label>知识范围<input v-model="botForm.personality.knowledge_domain" maxlength="200" :disabled="busy" /></label><label>补充指令<textarea v-model="botForm.personality.custom_instructions" maxlength="500" rows="5" :disabled="busy" /></label><label class="checkbox"><input v-model="botForm.is_active" type="checkbox" :disabled="busy" />启用助手</label><p class="muted">基础提示词由统一模板维护。此处调整对话配置，不改变工具权限和人工确认规则。</p></div><footer class="dialog-actions"><button type="button" :disabled="busy" @click="botForm = undefined">取消</button><button class="primary" :disabled="busy">保存配置</button></footer></form></Dialog>
  </section>
</template>

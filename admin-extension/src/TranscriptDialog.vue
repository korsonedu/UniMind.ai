<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Dialog from './Dialog.vue';
import { localDate, message, useTask } from './api';
import type { Course, Gateway, Transcript, TranscriptSegment } from './types';

type SaveResult = { revision: number; manual_edited_at: string | null };

const props = defineProps<{ api: Gateway; course: Course }>();
const emit = defineEmits<{ close: [] }>();
const { busy, error, run } = useTask();
const transcript = ref<Transcript>();
const edits = reactive(new Map<number, string>());
const page = ref(1);
const notice = ref('');
const PAGE_SIZE = 50;
const SAVE_BATCH = 50;
const statusNames: Record<string, string> = { pending: '待处理', processing: '识别中', completed: '已完成', failed: '识别失败', not_available: '暂无字幕' };
const outlineNames: Record<string, string> = { pending: '待处理', generating: '生成中', completed: '已完成', failed: '生成失败' };

async function load() {
  const result = await props.api<Transcript>('courses.transcript.get', { id: props.course.id });
  transcript.value = result;
  edits.clear();
  page.value = 1;
  notice.value = '';
}
onMounted(() => run(load));

const processing = computed(() => transcript.value?.status === 'processing');
const locked = computed(() => busy.value || processing.value);
const pageCount = computed(() => Math.max(1, Math.ceil((transcript.value?.segments.length || 0) / PAGE_SIZE)));
const pageSegments = computed(() => transcript.value ? transcript.value.segments.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE) : []);
const changes = computed(() => transcript.value ? transcript.value.segments.filter(segment => edits.has(segment.id)) : []);
const changedCount = computed(() => changes.value.length);
const canSave = computed(() => !locked.value && changedCount.value > 0);
const canRetranscribe = computed(() => !!transcript.value && !busy.value && !processing.value);
const statusClass = computed(() => ({
  'status-good': transcript.value?.status === 'completed',
  warning: processing.value || transcript.value?.status === 'pending',
  danger: transcript.value?.status === 'failed',
}));
const outlineText = computed(() => {
  const status = transcript.value?.outline_status;
  return status ? outlineNames[status] || status : '未生成';
});
const manualText = computed(() => {
  const value = transcript.value;
  if (!value?.is_manually_edited) return '未人工修改';
  const who = value.manual_edited_by_name || '管理员';
  return value.manual_edited_at ? `${who} · ${localDate(value.manual_edited_at)}` : who;
});

function clock(value: number) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
function updateText(segment: TranscriptSegment, event: Event) {
  const text = (event.target as HTMLTextAreaElement).value;
  if (text === segment.text) edits.delete(segment.id);
  else edits.set(segment.id, text);
}
function applySaved(batch: { id: number; text: string }[], result: SaveResult) {
  const current = transcript.value;
  if (!current) return;
  for (const item of batch) {
    const segment = current.segments.find(row => row.id === item.id);
    if (segment) segment.text = item.text;
    edits.delete(item.id);
  }
  current.revision = result.revision;
  current.status = 'completed';
  current.error_message = '';
  current.is_manually_edited = true;
  if (result.manual_edited_at) current.manual_edited_at = result.manual_edited_at;
  current.full_text = current.segments.map(segment => segment.text).join('\n');
}
async function save() {
  if (!transcript.value) return;
  const items = changes.value.map(segment => ({ id: segment.id, text: edits.get(segment.id)! }));
  notice.value = '';
  for (let index = 0; index < items.length; index += SAVE_BATCH) {
    const batch = items.slice(index, index + SAVE_BATCH);
    let result: SaveResult;
    try {
      result = await props.api<SaveResult>('courses.transcript.save', {
        id: props.course.id, revision: transcript.value.revision, segments: batch, request_id: crypto.randomUUID(),
      });
    } catch (exception) {
      if (message(exception).includes('已被其他人更新')) throw new Error('字幕已被其他人更新，请刷新后重试');
      throw exception;
    }
    applySaved(batch, result);
  }
}
async function retranscribe() {
  if (!window.confirm('重新识别会覆盖当前字幕，包括所有人工修改。确认继续？')) return;
  notice.value = '';
  await run(async () => {
    const result = await props.api<{ status?: string }>('courses.transcript.retranscribe', { id: props.course.id, request_id: crypto.randomUUID() });
    if (transcript.value) transcript.value.status = result?.status || 'processing';
    edits.clear();
    notice.value = '已提交重新识别，处理完成后请刷新查看。';
  });
}
async function regenerateOutline() {
  notice.value = '';
  await run(async () => {
    await props.api('courses.outline.regenerate', { id: props.course.id, request_id: crypto.randomUUID() });
    if (transcript.value) transcript.value.outline_status = 'generating';
    notice.value = '已提交重新生成大纲，处理完成后请刷新查看。';
  });
}
</script>

<template>
  <Dialog :title="`课程字幕 · ${transcript?.title || course.title}`" :busy="busy" :dirty="changedCount > 0" wide @close="emit('close')">
    <div class="dialog-body">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <template v-if="transcript">
        <div class="transcript-meta">
          <span>状态 <strong :class="statusClass">{{ statusNames[transcript.status] || transcript.status }}</strong></span>
          <span>大纲 <strong>{{ outlineText }}</strong></span>
          <span>识别服务 <strong>{{ transcript.provider || '未记录' }}</strong></span>
          <span>版本 <strong>{{ transcript.revision }}</strong></span>
          <span>人工修订 <strong>{{ manualText }}</strong></span>
          <span v-if="changedCount" class="transcript-changed">待保存 {{ changedCount }} 句</span>
        </div>
        <p v-if="processing" class="notice" role="status">字幕正在识别中，请等待处理完成；当前禁止编辑和保存。</p>
        <p v-else-if="transcript.status === 'failed'" class="error" role="alert">{{ transcript.error_message || '字幕识别失败，可重新识别。' }}</p>
        <p v-if="notice" class="notice" role="status">{{ notice }}</p>
        <template v-if="transcript.segments.length">
          <div class="table-scroll">
            <table class="transcript-table">
              <thead><tr><th>时间</th><th>字幕内容</th></tr></thead>
              <tbody>
                <tr v-for="segment in pageSegments" :key="segment.id">
                  <td class="transcript-time">{{ clock(segment.start_time) }} - {{ clock(segment.end_time) }}</td>
                  <td><textarea :value="edits.get(segment.id) ?? segment.text" :disabled="locked" rows="2" :aria-label="`第 ${segment.index + 1} 句字幕`" @input="updateText(segment, $event)" /></td>
                </tr>
              </tbody>
            </table>
          </div>
          <footer v-if="pageCount > 1" class="pagination">
            <span>共 {{ transcript.segments.length }} 句</span>
            <button type="button" class="icon" title="上一页" :disabled="busy || page <= 1" @click="page--"><ChevronLeft :size="17" /></button>
            <span>{{ page }} / {{ pageCount }}</span>
            <button type="button" class="icon" title="下一页" :disabled="busy || page >= pageCount" @click="page++"><ChevronRight :size="17" /></button>
          </footer>
        </template>
        <p v-else-if="transcript.status === 'not_available'" class="notice">暂无字幕，可点击重新识别。</p>
        <p v-else-if="!processing && transcript.status !== 'failed'" class="notice">暂无可编辑的字幕分段。</p>
      </template>
      <p v-else-if="busy" class="empty">加载中</p>
    </div>
    <footer class="dialog-actions">
      <span v-if="busy" role="status">处理中，请稍候</span>
      <span v-else-if="changedCount">{{ changedCount }} 句待保存</span>
      <button type="button" :disabled="busy" @click="run(load)">刷新</button>
      <button type="button" :disabled="!canRetranscribe" @click="retranscribe">重新识别</button>
      <button type="button" :disabled="busy || !transcript" @click="regenerateOutline">重新生成大纲</button>
      <button type="button" class="primary" :disabled="!canSave" @click="run(save)">保存修改</button>
    </footer>
  </Dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{ value: unknown }>();
const entries = computed(() => props.value && typeof props.value === 'object' && !Array.isArray(props.value) ? Object.entries(props.value) : []);
const labels: Record<string, string> = { report: '学情报告', stats: '学习概况', student_name: '学员', student_id: '学员 ID', date_from: '开始时间', date_to: '结束时间', total_attempted: '累计答题', accuracy: '正确率', radar: '知识掌握', subject: '学科', avg_mastery: '平均掌握度', kp_count: '考点数', daily: '每日活动', achievements: '成就', streak: '连续学习', date: '日期', count: '数量', by_status: '任务状态', total: '总数', completion_rate: '完成率（%）', window_days: '统计天数', pipeline_quality: '管线质量', top_errors: '常见错误', stages: '执行阶段', summary: '结果概览', content: '内容', title: '标题', payload: '数据', type: '类型', questions_saved: '已入库', total_generated: '生成数', generated: '生成数', saved: '入库数', target: '目标数', review_passed: '审核通过', review_rejected: '审核拒绝', schema_ok: '格式通过', difficulty_mismatches: '难度偏差', answer_errors: '答案异常', pending_review: '待人工审核', pending: '待执行', running: '执行中', completed: '完成', review: '待审核', failed: '失败', cancelled: '已取消' };
function scalar(value: unknown) { return value == null ? '暂无' : typeof value === 'boolean' ? value ? '是' : '否' : String(value); }
</script>
<template>
  <dl v-if="entries.length" class="teaching-data"><template v-for="[key, item] in entries" :key="key"><dt>{{ labels[key] || key }}</dt><dd><TeachingData v-if="item && typeof item === 'object'" :value="item" /><span v-else>{{ scalar(item) }}</span></dd></template></dl>
  <ol v-else-if="Array.isArray(value) && value.length" class="teaching-data-list"><li v-for="(item, index) in value" :key="index"><TeachingData :value="item" /></li></ol>
  <span v-else>{{ Array.isArray(value) ? '暂无记录' : scalar(value) }}</span>
</template>
<style scoped>
.teaching-data{display:grid;grid-template-columns:minmax(90px,auto) minmax(0,1fr);gap:7px 18px;margin:0;font-size:13px}.teaching-data dt{color:var(--um-muted,#68727d)}.teaching-data dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.teaching-data-list{padding-left:20px;margin:0}.teaching-data-list>li{padding:4px 0}
@media(max-width:600px){.teaching-data{grid-template-columns:1fr;gap:4px}.teaching-data dd{margin-bottom:9px}}
</style>

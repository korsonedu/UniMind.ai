import assert from 'node:assert/strict';
import test from 'node:test';
import {
  completeToolRun,
  reduceToolRun,
  shouldExpandToolRun,
  type AgentStep,
  upsertToolStepMessage,
} from '../src/types/toolRun.ts';


function step(overrides: Partial<AgentStep> = {}): AgentStep {
  return {
    type: 'step',
    run_id: 'run-one',
    call_id: 'call-one',
    round: 1,
    name: 'lookup',
    label: '查询数据',
    status: 'queued',
    ...overrides,
  };
}


test('同一 Tool Run 按首次出现顺序累计并原位更新任务', () => {
  let state = reduceToolRun(null, step());
  state = reduceToolRun(state, step({ status: 'running' }));
  state = reduceToolRun(state, step({ status: 'succeeded', duration_ms: 18 }));
  state = reduceToolRun(state, step({
    call_id: 'call-two',
    round: 2,
    label: '查询复习任务',
    status: 'queued',
  }));

  assert.equal(state?.run_id, 'run-one');
  assert.deepEqual(state?.items.map(item => item.id), ['call-one', 'call-two']);
  assert.equal(state?.items[0].status, 'succeeded');
  assert.equal(state?.items[0].duration_ms, 18);
  assert.equal(state?.completed, false);
});


test('终态不会被迟到的运行事件回退', () => {
  const succeeded = reduceToolRun(null, step({ status: 'succeeded' }));
  const stale = reduceToolRun(succeeded, step({ status: 'running' }));

  assert.equal(stale?.items[0].status, 'succeeded');
});


test('新 run 重置列表，旧 batch_start 被忽略', () => {
  const first = reduceToolRun(null, step());
  const legacy = reduceToolRun(first, step({ status: 'batch_start' }));
  const second = reduceToolRun(legacy, step({
    run_id: 'run-two',
    call_id: 'call-new',
  }));

  assert.equal(legacy, first);
  assert.equal(second?.run_id, 'run-two');
  assert.deepEqual(second?.items.map(item => item.id), ['call-new']);
});


test('缺少 Tool Run 身份的旧进度事件不会清空累计任务', () => {
  const first = reduceToolRun(null, step({ status: 'succeeded' }));
  const legacy = reduceToolRun(first, {
    type: 'step',
    call_id: 'call-one',
    name: 'quick_generate',
    label: '正在生成题目',
    status: 'calling',
  } as unknown as AgentStep);

  assert.equal(legacy, first);
});


test('小宇工具消息支持 queued 直接失败并原位更新', () => {
  type Message = { id: string; toolStep?: AgentStep };
  const create = (toolStep: AgentStep): Message => ({ id: toolStep.call_id, toolStep });

  const queued = upsertToolStepMessage<Message>([], step(), create);
  const failed = upsertToolStepMessage(
    queued,
    step({ status: 'failed', error: { code: 'invalid_arguments', message: '参数错误' } }),
    create,
  );
  const directFailure = upsertToolStepMessage<Message>(
    [],
    step({ status: 'failed', error: { code: 'permission_denied', message: '无权限' } }),
    create,
  );

  assert.equal(queued.length, 1);
  assert.equal(failed.length, 1);
  assert.equal(failed[0].toolStep?.status, 'failed');
  assert.equal(directFailure.length, 1);
  assert.equal(directFailure[0].toolStep?.error?.code, 'permission_denied');
});


test('新 run 或任一失败任务要求展开任务列表', () => {
  const current = reduceToolRun(null, step({ status: 'succeeded' }));
  const failed = reduceToolRun(null, step({ status: 'failed' }));

  assert.equal(shouldExpandToolRun('run-old', current!), true);
  assert.equal(shouldExpandToolRun('run-one', current!), false);
  assert.equal(shouldExpandToolRun('run-one', failed!), true);
});


test('done 只完成匹配的 Tool Run', () => {
  const running = reduceToolRun(null, step({ status: 'running' }));
  const mismatched = completeToolRun(running, 'run-other');
  const completed = completeToolRun(mismatched, 'run-one');

  assert.equal(mismatched?.completed, false);
  assert.equal(completed?.completed, true);
});

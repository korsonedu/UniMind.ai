import { createHash, createHmac, randomUUID } from 'node:crypto';

export const operations = new Set([
  'meta', 'options', 'courses.list', 'courses.save', 'courses.delete', 'courses.assign',
  'courses.transcript.get', 'courses.transcript.save', 'courses.transcript.retranscribe', 'courses.outline.regenerate',
  'modules.list', 'modules.save', 'modules.delete', 'students.list', 'students.detail', 'students.access.save',
  'products.list', 'products.save', 'grants.create', 'grants.revoke', 'audit.list',
  'uploads.start', 'uploads.complete', 'uploads.cancel',
  'knowledge.list', 'knowledge.save', 'knowledge.delete',
  'questions.list', 'questions.detail', 'questions.save', 'questions.delete', 'questions.assign',
  'students.status.save', 'quota.get', 'quota.save', 'addons.list', 'addons.save', 'orders.list', 'ai.config.get', 'ai.config.save',
  'teaching.stats', 'teaching.knowledge', 'teaching.browse', 'teaching.student', 'teaching.students',
  'teaching.conversations', 'teaching.history', 'teaching.notification.preview',
  'teaching.chat', 'teaching.generate', 'teaching.report', 'teaching.notification.send',
  'pipeline.list', 'pipeline.detail', 'pipeline.metrics', 'pipeline.review', 'pipeline.retry', 'pipeline.delete',
  'teaching.restore', 'teaching.notification.config', 'teaching.notification.config.save',
]);

type Config = { origin: string; secret: string; operators: string[] };

export function configuration(env: Record<string, unknown>): Config {
  const origin = new URL(String(env.UNIMIND_BACKEND_URL || ''));
  const secret = String(env.UNIMIND_ADMIN_BRIDGE_SECRET || '');
  const operators = String(env.UNIMIND_DIRECTUS_ADMIN_IDS || '').split(',').map(id => id.trim());
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!['http:', 'https:'].includes(origin.protocol) || origin.username || origin.password || origin.search || origin.hash || origin.pathname !== '/' ||
      (origin.protocol === 'http:' && !['127.0.0.1', 'localhost', 'host.docker.internal'].includes(origin.hostname)) ||
      secret.length < 32 || operators.length !== 2 || new Set(operators).size !== 2 || operators.some(id => !uuid.test(id))) {
    throw new Error('Invalid UniMind bridge configuration');
  }
  return { origin: origin.origin, secret, operators };
}

export async function callDjango(config: Config, actor: string, operation: string, data: unknown) {
  if (!operations.has(operation)) return { status: 404, body: { error: '未开放的管理操作。' } };
  if (!data || typeof data !== 'object' || Array.isArray(data)) return { status: 400, body: { error: '请求须为 JSON 对象。' } };
  const body = JSON.stringify(data);
  if (Buffer.byteLength(body) > 256 * 1024) return { status: 413, body: { error: '管理请求过大。' } };
  const path = `/api/backoffice/operations/${operation}/`;
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID();
  const canonical = ['v1', 'POST', path, actor, timestamp, nonce, createHash('sha256').update(body).digest('hex')].join('\n');
  const response = await fetch(config.origin + path, {
    method: 'POST', body, redirect: 'error', signal: AbortSignal.timeout(60000),
    headers: { 'Content-Type': 'application/json', 'X-Unimind-Operator': actor,
      'X-Unimind-Timestamp': timestamp, 'X-Unimind-Nonce': nonce,
      'X-Unimind-Signature': createHmac('sha256', config.secret).update(canonical).digest('hex') },
  });
  if (response.status >= 500) throw new Error(`Django management status ${response.status}`);
  return { status: response.status, body: await response.json() as unknown };
}

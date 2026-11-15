import type { WorkspaceSnapshot, InvitePreview } from '@/lib/workspace';

const mode = new URLSearchParams(location.search).get('workspace');
const stored = sessionStorage.getItem('unimind-workspace-fixture');
const initial = (): WorkspaceSnapshot => ({
  available: true, demo: true, role: mode === 'unjoined' ? null : mode === 'admin' ? 'admin' : 'student',
  workspace: mode === 'unjoined' ? null : { name: '青禾学社', description: '2027 金融基础班 · 课程与小宇伴学', joined_at: '2026-11-01', service_ends_at: '2027-06-30' },
  courses: [
    { id: 1, title: '资金时间价值', module: '公司理财', duration: '42:18', filename: '01-资金时间价值.mp4', status: 'published', transcript: '00:00  从一个问题开始：今天的一百元，和一年后的一百元，为什么价值不同？\n\n02:16  比较不同时间点的资金，需要使用同一个时间基准。把未来金额换算到今天，就得到了现值。\n\n08:42  折现率既反映时间，也需要与现金流的风险和口径匹配。', knowledge: [{ name: '资金时间价值', children: ['现值与终值', '单利与复利', '年金与永续年金'] }, { name: '折现的应用', children: ['现金流时间轴', '折现率的选择', '估值口径一致性'] }] },
    { id: 2, title: '债券定价与收益率', module: '货币金融学', duration: '38:52', filename: '02-债券定价.mp4', status: 'published', transcript: '00:00  债券价格可以理解为未来现金流的现值之和。\n\n04:30  票息和到期本金构成了债券的现金流，收益率是计算这些现金流现值时使用的折现率。\n\n12:08  市场收益率提高时，同一组现金流的现值下降，因此债券价格下降。', knowledge: [{ name: '债券估值', children: ['票息与到期本金', '到期收益率', '价格与收益率关系'] }, { name: '利率风险', children: ['久期', '期限与价格敏感性'] }] },
    { id: 3, title: '货币政策传导', module: '货币金融学', duration: '35:06', filename: '03-货币政策.mp4', status: 'draft', transcript: '货币政策通过利率、信贷、资产价格与预期等渠道影响实体经济。理解传导，需要结合融资需求与银行放贷意愿。', knowledge: [{ name: '政策传导渠道', children: ['利率渠道', '信贷渠道', '资产价格渠道', '预期渠道'] }] },
    { id: 4, title: '资本预算与净现值', module: '公司理财', duration: '待处理', filename: '04-资本预算.mp4', status: 'processing', transcript: '', knowledge: [] },
  ],
  members: ['林同学', '陈同学', '周同学', '许同学', '苏同学'].map((name, i) => ({ id: i + 1, name, joined_at: `2026-11-${String(2 + i).padStart(2, '0')}`, service_ends_at: '2027-06-30', courses: [1, 2], active: i !== 4 })),
  invites: [{ id: 1, code: 'LEARN2027', name: '2027 金融基础班', courses: [1, 2], expires_at: '2026-12-31', service_ends_at: '2027-06-30', max_uses: 50, used_count: 5, active: true }],
  usage: [{ label: '课程处理时长', used: 116, limit: 1200, unit: '分钟' }, { label: '学生服务名额', used: 5, limit: 50, unit: '人' }, { label: '学习问答', used: 168, limit: 5000, unit: '次' }, { label: '文件存储', used: 3.2, limit: 50, unit: 'GB' }],
});
let state: WorkspaceSnapshot & { grantedCourses?: number[] } = stored && !mode ? JSON.parse(stored) : initial();
const save = () => sessionStorage.setItem('unimind-workspace-fixture', JSON.stringify(state));
if (mode) save();
const visible = (): WorkspaceSnapshot => state.role === 'admin' ? structuredClone(state) : { ...structuredClone(state), courses: state.workspace ? state.courses.filter(course => course.status === 'published' && (state.grantedCourses || [1, 2]).includes(course.id)) : [], members: [], invites: [], usage: [] };
function reject(message: string): never { throw new Error(message); }

// Imported only by the development preview adapter. No production data or credentials.
export function workspacePreview(path: string, method = 'get', payload?: Record<string, unknown> | FormData): unknown {
  if (!path.startsWith('/users/workspace/')) return undefined;
  if (path === '/users/workspace/' && method === 'get') return visible();
  const body = payload instanceof FormData ? {} : payload || {};
  if (path.endsWith('/invite-preview/') || path.endsWith('/join/')) {
    const invite = state.invites.find(item => item.code === String(body.code).trim());
    if (!invite?.active || invite.used_count >= invite.max_uses || new Date(`${invite.expires_at}T23:59:59+08:00`) < new Date()) reject('邀请码无效、已停用或已领完，请联系机构获取有效邀请码。');
    if (path.endsWith('/invite-preview/')) return { name: '青禾学社', service: invite.name, courses: state.courses.filter(course => invite.courses.includes(course.id)).map(course => course.title), service_ends_at: invite.service_ends_at } satisfies InvitePreview;
    if (!state.workspace) {
      state.workspace = { name: '青禾学社', description: `${invite.name} · 课程与小宇伴学`, joined_at: new Date().toISOString(), service_ends_at: invite.service_ends_at };
      state.role = 'student'; state.grantedCourses = [...invite.courses]; invite.used_count++; save();
    }
    return visible();
  }
  if (state.role !== 'admin') reject('你没有管理此机构的权限。');
  if (path === '/users/workspace/courses/' && method === 'post' && payload instanceof FormData) {
    const videos = payload.getAll('videos').filter((file): file is File => file instanceof File);
    if (!videos.length || !String(payload.get('module') || '').trim()) reject('请选择视频并填写所属模块。');
    for (const video of videos) {
      if (!video.name.toLowerCase().endsWith('.mp4')) reject('请选择 MP4 视频。');
      state.courses.push({ id: Math.max(0, ...state.courses.map(course => course.id)) + 1, title: video.name.replace(/\.mp4$/i, ''), module: String(payload.get('module')), duration: '待处理', filename: video.name, status: 'processing', transcript: '', knowledge: [] });
    }
  } else if (path === '/users/workspace/invites/' && method === 'post') {
    const courses = Array.isArray(body.courses) ? body.courses.map(Number) : [];
    if (!String(body.name || '').trim() || !courses.length || !Number.isInteger(body.max_uses) || Number(body.max_uses) < 1 || !body.expires_at || !body.service_ends_at || String(body.service_ends_at) < String(body.expires_at)) reject('请完整填写课程、人数与有效日期。');
    state.invites.unshift({ id: Date.now(), code: `QH${crypto.randomUUID().slice(0, 8).toUpperCase()}`, name: String(body.name), courses, max_uses: Number(body.max_uses), used_count: 0, active: true, expires_at: String(body.expires_at), service_ends_at: String(body.service_ends_at) });
  } else if (/\/courses\/\d+\/$/.test(path) && method === 'patch') {
    const course = state.courses.find(item => item.id === Number(path.split('/').at(-2)));
    if (!course || course.status === 'processing' || !['draft', 'published'].includes(String(body.status))) reject('课程内容尚未处理完成，暂时无法发布。');
    course.status = body.status as 'draft' | 'published';
  } else if (/\/invites\/\d+\/$/.test(path) && method === 'patch') {
    const invite = state.invites.find(item => item.id === Number(path.split('/').at(-2)));
    if (!invite) reject('邀请码不存在。'); invite.active = !!body.active;
  } else if (/\/members\/\d+\/$/.test(path) && method === 'patch') {
    const member = state.members.find(item => item.id === Number(path.split('/').at(-2)));
    if (!member) reject('学生不存在。'); member.active = !!body.active;
  } else reject('该预览操作暂不支持。');
  save(); return visible();
}

// Run in the isolated local course page's DevTools:
// await (await import('/tests/courseDraft.browser.mjs')).verifyCourseDraft()
// Responses are simulated locally; this never forwards a chat request to a model.
export async function verifyCourseDraft() {
  const checks = [];
  const check = (value, label) => { if (!value) throw new Error(label); checks.push(label); };
  const wait = async predicate => {
    for (let i = 0; i < 100; i++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error('等待界面更新超时');
  };
  const button = label => [...document.querySelectorAll('button')].find(el => el.textContent.trim() === label || el.getAttribute('aria-label') === label);
  const draft = () => document.querySelector('textarea[aria-label="向小宇提问"]');
  const text = () => document.querySelector('.um-course-chat-composer').textContent;
  const fill = async value => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(draft(), value);
    draft().dispatchEvent(new Event('input', { bubbles: true }));
    await wait(() => draft().value === value);
    await new Promise(resolve => requestAnimationFrame(resolve));
  };
  const video = document.querySelector('video');
  check(video.duration > 810, '使用时长足够的本地测试视频');
  const seek = async position => { video.currentTime = position; await wait(() => !video.seeking); };
  const requestBodies = [];
  const originalFetch = window.fetch;
  let failNext = false;
  window.fetch = (resource, init) => {
    if (!String(resource).includes('/api/ai/chat/stream/')) return originalFetch(resource, init);
    const body = JSON.parse(init.body);
    requestBodies.push(body);
    const isError = failNext;
    failNext = false;
    const content = isError ? '【本地模拟失败】' : '【本地模拟响应】仅用于一分钟提问片段验收。';
    const frame = { done: true, is_error: isError, full_content: content };
    return Promise.resolve(new Response(`data: ${JSON.stringify(frame)}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } }));
  };
  const send = async () => {
    button('发送课程问题').click();
    await wait(() => !draft().disabled);
    await new Promise(resolve => setTimeout(resolve, 150));
  };
  try {
    if (button('新对话')) button('新对话').click();
    await fill('');
    await seek(500);
    await fill('【本地草稿验证】这里为什么折现？');
    check(text().includes('提问片段：07:50–08:50'), '08:20首次输入绑定07:50–08:50');
    await video.play();
    await seek(750);
    await fill('【本地草稿验证】这里为什么折现？请解释。');
    check(text().includes('提问片段：07:50–08:50'), '继续播放至12:30并编辑仍保留原片段');
    check(!video.paused, '输入和编辑没有暂停视频');
    video.pause();
    draft().blur(); draft().focus();
    button('右侧').click();
    await wait(() => button('右侧').getAttribute('aria-pressed') === 'true');
    check(text().includes('07:50–08:50'), '切换右侧并切换焦点保留片段');
    button('浮动').click();
    await wait(() => button('浮动').getAttribute('aria-pressed') === 'true');
    check(text().includes('07:50–08:50'), '切回浮动保留片段');
    await seek(750);
    const before = draft().value;
    button('改问当前片段').click();
    await wait(() => text().includes('12:00–13:00'));
    check(draft().value === before, '更新至12:00–13:00且保留草稿');
    await seek(800);
    await send();
    check(requestBodies.at(-1).course_context.video_seconds === 750, '发送中心为所选750秒而非当前800秒');
    check(draft().value === '', '发送后清空草稿');
    await seek(500); await fill('发送后的新草稿');
    check(text().includes('07:50–08:50'), '发送后新草稿重新捕获500秒');
    await fill(''); await seek(750); await fill('清空后的新草稿');
    check(text().includes('12:00–13:00'), '清空后新草稿重新捕获750秒');
    await fill(''); await seek(0); await fill('开头边界问题');
    check(text().includes('00:00–00:30'), '0秒绑定0–30秒');
    await fill(''); await seek(500); await fill('失败恢复验证');
    failNext = true;
    await send();
    await wait(() => draft().value === '失败恢复验证');
    await seek(750);
    check(text().includes('07:50–08:50'), '失败恢复原草稿仍显示原片段');
    check(!button('改问当前片段').disabled, '失败后可直接更新提问片段');
    button('改问当前片段').click();
    await wait(() => text().includes('12:00–13:00'));
    await fill('继续问另一个问题');
    await send();
    check(requestBodies.at(-1).course_context.video_seconds === 750 && requestBodies.at(-1).message === '继续问另一个问题', '下一条提问使用更新后的片段');
    button('新对话').click();
    await wait(() => draft().value === '');
    check(text().includes('输入问题时固定提问片段'), '新对话清除所选片段');
    await seek(500); await fill('尚未发送的草稿');
    await seek(750);
    button('举个例子').click();
    await wait(() => requestBodies.at(-1).message === '结合这里的讲解，举一个简单的例子。');
    check(requestBodies.at(-1).course_context.video_seconds === 750, '有草稿时快捷建议作为新问题捕获点击时刻');
    await wait(() => !draft().disabled);
    await fill(''); await seek(500); await fill('【验收截图】08:20开始写，继续听至12:30。');
    await seek(750);
    check(text().includes('07:50–08:50'), '最终截图保留原片段');
    return { checks, requestBodies, url: location.href, currentTime: video.currentTime, selected: text() };
  } finally {
    window.fetch = originalFetch;
  }
}

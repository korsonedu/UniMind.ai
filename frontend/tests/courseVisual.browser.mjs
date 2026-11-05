// Run verifyCourseVisual() in a local course page with simulated API responses.
// Real UI and courseVisual implementation; API/SSE/media are local Playwright routes.
export async function verifyCourseVisual() {
  const checks = [], requests = [];
  const check = (value, label) => { if (!value) throw new Error(label); checks.push(label); };
  window.__courseVisualEvidence = { checks, requests };
  const wait = async (predicate, label = '等待界面更新超时', timeout = 7000) => {
    const end = performance.now() + timeout;
    while (performance.now() < end) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(label);
  };
  const button = label => [...document.querySelectorAll('.um-course-chat button')].find(el => el.textContent.trim() === label || el.getAttribute('aria-label') === label);
  const draft = () => document.querySelector('textarea[aria-label="向小宇提问"]');
  const preview = () => document.querySelector('.um-course-chat > .um-course-visual');
  const image = () => preview()?.querySelector('img[alt^="提问时的完整画面"]')?.src;
  const composer = () => document.querySelector('.um-course-chat-composer > div > span').textContent;
  const fill = async text => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(draft(), text);
    draft().dispatchEvent(new Event('input', { bubbles: true }));
    await wait(() => draft().value === text);
    await new Promise(resolve => requestAnimationFrame(resolve));
  };
  const v = document.querySelector('video');
  await wait(() => v.readyState >= 2 && draft() && button('发送课程问题'));
  check(v.videoWidth === 1280 && v.videoHeight === 720 && Math.abs(v.duration - 12) < .1, '真实课程播放器使用12秒1280×720本地板书视频');
  const seek = async seconds => {
    v.pause();
    if (Math.abs(v.currentTime - seconds) < .001) return;
    await Promise.all([new Promise(resolve => v.requestVideoFrameCallback(resolve)), new Promise(resolve => { v.addEventListener('seeked', resolve, { once: true }); v.currentTime = seconds; })]);
  };
  const playTo = async seconds => {
    await v.play();
    await wait(() => v.currentTime >= seconds, `正常播放未到${seconds}秒`, 15000);
  };
  const screenshot = name => window.__cvScreenshot(name);
  const originalFetch = window.fetch;
  window.fetch = (resource, init) => {
    if (String(resource).includes('/api/ai/chat/stream/')) requests.push(JSON.parse(init.body));
    return originalFetch(resource, init);
  };
  const send = async () => {
    const n = requests.length;
    button('发送课程问题').click();
    await wait(() => requests.length === n + 1, '没有发出预期的本地聊天请求');
    await wait(() => !draft().disabled);
    await new Promise(resolve => setTimeout(resolve, 150));
    return requests.at(-1).course_context;
  };
  const valid = context => {
    const visual = context.visual;
    check(visual && visual.current.image.startsWith('data:image/jpeg;base64,'), '请求包含JPEG dataURL截图');
    check(context.video_seconds === visual.current.video_seconds, '问题时间与冻结截图时间相同');
    check(visual.current.image.length <= 640000, '当前截图符合约定体积');
    check(!Object.hasOwn(visual, 'regions') && Object.keys(visual).every(key => ['current', 'previous'].includes(key)), '请求只包含完整原图，没有变化区域或裁剪');
    return visual;
  };
  try {
    if (button('右侧')) button('右侧').click();
    if (button('新对话')) button('新对话').click();
    await fill(''); await seek(2);
    await fill('现值为什么要除以折现因子？');
    await wait(() => image());
    const initial = image(), initialTime = composer();
    check(preview().textContent.includes('画面 00:02'), '首次输入冻结第2秒画面和时间');
    await screenshot('01-initial-frozen');
    await playTo(6.2);
    await fill('现值为什么要除以折现因子？请解释。');
    check(image() === initial, '继续播放跨过第一处变化并编辑，截图保持原值');
    check(composer() === initialTime, '继续播放跨过第一处变化并编辑，时间保持原值');
    check(!v.paused, '编辑没有暂停课程视频');
    const text = draft().value;
    button('改问当前片段').click();
    await wait(() => image() && image() !== initial);
    check(draft().value === text && !composer().includes('00:32'), '改问当前片段整体更新截图和时间并保留文字');
    check(preview().querySelectorAll('.um-course-visual-box, .um-course-visual-crops').length === 0, '原图预览不标框、不裁剪');
    await wait(() => preview().querySelector('img[alt^="此前的完整画面"]')?.complete);
    await screenshot('02-first-change');
    const middle = image(), middleTime = composer();
    await playTo(10.2);
    await fill(text + '算出的1000如何理解？');
    check(image() === middle && composer() === middleTime, '跨过第二处变化继续编辑仍保留已有截图');
    button('改问当前片段').click();
    await wait(() => image() !== middle);
    v.pause();
    check(preview().querySelectorAll('img[alt*="完整画面"]').length === 2, '显示当前和此前两张完整原图');
    await wait(() => [...preview().querySelectorAll('img')].every(img => img.complete && img.naturalWidth > 0));
    await screenshot('03-second-change');
    const sentImage = image();
    const anchor = await send(), visual = valid(anchor);
    check(visual.current.image === sentImage && anchor.video_seconds >= 10 && anchor.video_seconds < 11.5, '发送使用更新后的冻结图片和时间');
    check(visual.previous && visual.previous.video_seconds < visual.current.video_seconds && visual.current.video_seconds - visual.previous.video_seconds <= 8, '自然播放提供8秒内的此前原图');
    await wait(() => document.querySelector('.um-course-chat-messages img[alt="提问画面缩略图"]'));
    check(document.querySelector('.um-course-chat-messages img[alt="提问画面缩略图"]').src === sentImage, '用户消息历史保留原始截图');
    const details = document.querySelector('.um-course-chat-messages details.um-course-visual');
    details.open = true;
    await screenshot('04-sent-history');

    button('新对话').click(); await fill(''); await seek(3);
    await fill('已有草稿'); const draftImage = image();
    await seek(9); button('举个例子').click();
    await wait(() => requests.at(-1).message === '结合这里的讲解，举一个简单的例子。');
    await wait(() => !draft().disabled);
    const quick = requests.at(-1).course_context; valid(quick);
    check(quick.video_seconds === 9 && quick.visual.current.image !== draftImage, '快捷提问捕获点击时刻第9秒的新截图');
    check(!quick.visual.previous && !Object.hasOwn(quick.visual, 'regions'), 'seek后清空旧采样，快捷提问不附带跳转前画面');
    await screenshot('05-shortcut-and-seek');

    button('新对话').click(); await fill(''); await seek(6);
    await fill('同一次失败请求的图片必须保留');
    const retryImage = image();
    await window.__cvControl('failNext');
    const first = await send();
    await wait(() => draft().value === '同一次失败请求的图片必须保留');
    await seek(10);
    check(button('改问当前片段').disabled, '失败待确认时禁止替换原提问截图');
    const retried = await send();
    check(JSON.stringify(first) === JSON.stringify(retried) && retried.visual.current.image === retryImage, '同次重试沿用完全相同的时间和两张原图');
    await screenshot('06-retry-original-image');

    button('新对话').click(); await fill(''); await seek(5);
    const originalDataURL = HTMLCanvasElement.prototype.toDataURL;
    try {
      HTMLCanvasElement.prototype.toDataURL = function () { throw new DOMException('本地注入：禁止读取截图', 'SecurityError'); };
      await fill('截图出错时仅讲稿选项测试');
      await wait(() => document.querySelector('.um-course-visual-error[role="alert"]'));
      check(button('发送课程问题').disabled, '截图异常时发送按钮禁用');
      const n = requests.length;
      button('发送课程问题').click();
      await new Promise(resolve => setTimeout(resolve, 150));
      check(button('仅用讲稿提问') && requests.length === n, '截图异常显示显式的仅用讲稿提问选项，未选择时不发送请求');
      await screenshot('07-image-error-choice');
      button('仅用讲稿提问').click();
      await wait(() => !button('发送课程问题').disabled);
      check(document.querySelector('.um-course-visual-error').textContent.includes('已选择仅用讲稿'), '显式选择后界面显示仅讲稿状态');
      const textOnly = await send();
      check(!Object.hasOwn(textOnly, 'visual') && textOnly.video_seconds === 5, '明确选择仅讲稿后请求不含visual且保留第5秒时间');
    } finally { HTMLCanvasElement.prototype.toDataURL = originalDataURL; }
    await screenshot('08-text-only-sent');
    return { checks, requestCount: requests.length, historyImage: sentImage, url: location.href };
  } finally { v.pause(); window.fetch = originalFetch; }
}

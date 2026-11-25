// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest';
import { parseBilibiliSubtitles } from '../src/collectors/bilibili';
import { sliceTranscriptWindow } from '../src/collectors/transcriptWindow';
import { extractWorkbenchArticle } from '../src/collectors/workbenchArticle';
import { fullWorkbenchTranscript, readPlayerSubtitles } from '../src/collectors/workbenchVideo';
import { parseYouTubeJson3 } from '../src/collectors/youtube';

afterEach(() => {
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

it('保留 B 站与 YouTube 一小时讲稿的首尾和所有 1200 行时间戳', () => {
  const lines = Array.from({ length: 1200 }, (_, index) => `第 ${index + 1} 句`);
  const bilibili = parseBilibiliSubtitles({
    body: lines.map((content, index) => ({ from: index * 3, to: (index + 1) * 3, content })),
  });
  const youtube = parseYouTubeJson3({
    events: lines.map((utf8, index) => ({ tStartMs: index * 3000, dDurationMs: 3000, segs: [{ utf8 }] })),
  });
  for (const track of [bilibili, youtube]) {
    const result = fullWorkbenchTranscript([...track].reverse());
    expect(result.map(cue => cue.text)).toEqual(lines);
    expect(result.at(-1)?.end_time).toBe(3600);
    const ask = sliceTranscriptWindow(track, 1800, 1800, 1800);
    expect(ask).toHaveLength(80);
    expect(ask.every(cue => cue.start_time > 1600 && cue.end_time < 2000)).toBe(true);
  }
});

it('按播放顺序限制到 5000 行并去掉重复或无效字幕', () => {
  const track = Array.from({ length: 5010 }, (_, index) => ({
    start_time: index, end_time: index + 1, text: '字幕',
  })).reverse();
  const result = fullWorkbenchTranscript([...track, {
    start_time: 0, end_time: 1, text: ' 字幕 ',
  }, { start_time: -1, end_time: 0, text: '无效' }]);
  expect(result).toHaveLength(5000);
  expect(result[0]).toEqual({ start_time: 0, end_time: 1, text: '字幕' });
  expect(result.at(-1)?.end_time).toBe(5000);
});

it('读取已加载的播放器字幕轨，保留尚未播放的字幕', () => {
  const video = document.createElement('video');
  Object.defineProperty(video, 'textTracks', { value: [
    { kind: 'metadata', mode: 'showing', cues: [{ text: '不属于字幕' }] },
    { kind: 'subtitles', mode: 'hidden', cues: [{ startTime: 0, endTime: 1, text: '另一语言' }] },
    { kind: 'captions', mode: 'showing', cues: [
      { startTime: 0, endTime: 2, text: '开始' }, { startTime: 58, endTime: 60, text: '结束' },
    ] },
  ] });
  expect(readPlayerSubtitles(video)).toEqual([
    { start_time: 0, end_time: 2, text: '开始' }, { start_time: 58, end_time: 60, text: '结束' },
  ]);
});

it('保留正文结构、缩进和规范链接，排除菜单、广告和隐藏内容', () => {
  document.head.innerHTML = '<title>网站名</title><link rel="canonical" href="https://docs.example.org/reference#setup">';
  document.body.innerHTML = `
    <header><h1>网站横幅</h1></header><nav>站点导航</nav>
    <main><article>
      <h1>接口 <em>文档</em></h1><h2>快速开始</h2>
      <p>先<span>连接</span><br>再使用。<span style="display:none">隐去</span></p>
      <ol start="3"><li><p>检查连接</p></li><li>保存结果<ul><li>可以重试</li></ul></li></ol>
      <h3>代码</h3><pre><code>if ready:\n    run()</code></pre>
      <div class="ad"><p>广告</p></div><script>不会出现</script>
      <div aria-hidden="true">辅助界面</div><div hidden>隐藏属性</div>
      <div style="visibility:hidden"><p>不可见段落</p></div>
      <footer>文章页脚</footer>
    </article></main><footer>站点页脚</footer>`;
  const result = extractWorkbenchArticle(120_000);
  expect(result.title).toBe('接口 文档');
  expect(result.url).toBe('https://docs.example.org/reference');
  expect(result.content).toBe([
    '# 接口 文档', '## 快速开始', '先连接\n再使用。', '3. 检查连接', '4. 保存结果',
    '    - 可以重试', '### 代码', '```\nif ready:\n    run()\n```',
  ].join('\n\n'));
});

it('无正文时保留页面标题与 URL，并忽略非 HTTP 规范链接', () => {
  document.head.innerHTML = '<title>等待加载</title><link rel="canonical" href="javascript:void(0)">';
  document.body.innerHTML = '<div hidden>隐藏内容</div><nav>导航</nav>';
  expect(extractWorkbenchArticle(120_000)).toMatchObject({ title: '等待加载', url: location.href, content: '' });
});

it('截断长内容时保持字符完整、闭合代码围栏并遵守大小限制', () => {
  document.body.innerHTML = '<pre>' + '```\n  写入😀\n'.repeat(20000) + '</pre><p>最后一段</p>';
  const { content } = extractWorkbenchArticle(120_000);
  expect(content.length).toBeLessThanOrEqual(120_000);
  expect(content).toMatch(/^````\n/);
  expect(content.endsWith('\n````')).toBe(true);
  expect(content).not.toContain('最后一段');
  expect(content).not.toMatch(/[\uD800-\uDFFF]/u);
});

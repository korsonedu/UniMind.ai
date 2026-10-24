import './previewApi';
import { useState } from 'react';
import { toPng } from 'html-to-image';

function HDCaptureControls() {
  const [scene, setScene] = useState('plan');
  const [image, setImage] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const capture = async (kind: 'conversation' | 'visual' | 'result' | 'workspace') => {
    const conversation = document.querySelector<HTMLElement>('.um-agent-chat-body .overflow-y-auto > .max-w-3xl');
    const target = kind === 'workspace' ? document.querySelector<HTMLElement>('.um-app-shell') : kind === 'conversation' ? conversation : kind === 'result'
      ? conversation?.querySelector<HTMLElement>('.um-inline-practice-result')
      : conversation?.querySelector<HTMLElement>('.animate-in:has(> .max-w-\\[90\\%\\])');
    if (!target) { setStatus('请先打开对应对话或完成练习批改。'); return; }
    setBusy(true); setImage(''); setStatus('正在导出原始界面…');
    const motionStyle = document.createElement('style');
    motionStyle.textContent = '.um-hd-capture, .um-hd-capture * { animation: none !important; transition: none !important; }';
    try {
      await document.fonts.ready;
      target.getAnimations({ subtree: true }).forEach(animation => {
        if (Number.isFinite(Number(animation.effect?.getComputedTiming().endTime))) animation.finish();
      });
      document.head.append(motionStyle); target.classList.add('um-hd-capture');
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      const pixelRatio = Math.max(3, 2130 / target.getBoundingClientRect().width);
      const png = await toPng(target, { pixelRatio, backgroundColor: '#ffffff', preferredFontFormat: 'woff2', skipAutoScale: true, style: { margin: '0', transform: 'none' } });
      setImage(png); setStatus(`${Math.round(target.getBoundingClientRect().width * pixelRatio)} px 宽 · 原始 DOM`);
    } catch (error) { setStatus(error instanceof Error ? error.message : '导出失败'); }
    finally { target.classList.remove('um-hd-capture'); motionStyle.remove(); setBusy(false); }
  };
  return <div data-hd-capture style={{ position: 'fixed', right: 12, top: 12, zIndex: 9999, display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: '#fff', border: '1px solid #ddd', borderRadius: 8, fontSize: 12 }}>
    <select aria-label="截图场景" value={scene} onChange={event => { setScene(event.target.value); setImage(''); }}>
      <option value="plan">学习安排</option><option value="graph">函数图像</option><option value="map">知识图谱</option><option value="practice">练习批改</option>
    </select>
    <button disabled={busy} onClick={() => capture('conversation')}>导出完整对话</button>
    <button disabled={busy} onClick={() => capture('visual')}>导出产品卡片</button>
    <button disabled={busy} onClick={() => capture('result')}>导出批改结果</button>
    <button disabled={busy} onClick={() => capture('workspace')}>导出完整界面</button>
    {image && <a href={image} download={`landing-focus-${scene}.png`}>下载高清 PNG</a>}
    <span role="status">{status}</span>
  </div>;
}

/** Controls surround the real App; routes and pages are never substituted. */
export function PreviewControls() {
  const capture = new URLSearchParams(location.search).get('capture');
  if (capture === 'hd') return <HDCaptureControls />;
  if (capture !== null) return null;
  return <div className="um-full-preview-bar">
    <span><span className="um-preview-name">UniMind.ai · 完整应用 · </span>本地示例数据</span>
    <label>身份 <select aria-label="调试身份" defaultValue={sessionStorage.getItem('unimind-preview-role') || 'student'} onChange={event => {
      sessionStorage.setItem('unimind-preview-role', event.target.value);
      sessionStorage.removeItem('unimind-preview-signed-out');
      location.assign('/?preview=1');
    }}><option value="student">学生</option><option value="teacher">教师 / 机构</option><option value="admin">平台管理员</option></select></label>
    <a href="/?preview=0">连接真实后端</a>
  </div>;
}

import { useEffect, useRef, useState } from 'react';
import { IntelligenceField } from './IntelligenceField';
import { ScreenshotDissolve } from './ScreenshotDissolve';
import '@/styles/landing-instrument.css';

const modes = [
  { id: 'plan', label: '学习安排', description: '根据学习记录与知识掌握情况，安排学习与复习。', capabilities: ['学习记录', '知识掌握', '复习安排'], screens: [
    { image: 'landing-agent-plan-demo.webp', crop: [390, 205, 710, 370] },
    { image: 'landing-workspace-demo.webp', crop: [290, 390, 950, 430] },
  ] },
  { id: 'understand', label: '知识讲解', description: '检索课程与资料，用推导、图像和知识关系，把概念讲清楚。', capabilities: ['资料检索', '公式推导', '图像讲解', '知识关系'], screens: [
    { image: 'landing-agent-demo.webp', crop: [390, 170, 710, 460] },
    { image: 'landing-agent-map-demo.webp', crop: [570, 290, 370, 280] },
  ] },
  { id: 'practice', label: '练习反馈', description: '围绕正在学的内容出题，批改作答，让错题进入后续复习。', capabilities: ['随堂练习', '作答批改', '错题整理', 'Memorix'], screens: [
    { image: 'landing-learning-records-demo.webp', crop: [90, 130, 1140, 440] },
    { image: 'landing-agent-feedback-demo.webp', crop: [405, 360, 665, 360] },
  ] },
] as const;

export function LearningInstrument() {
  const [mode, setMode] = useState<typeof modes[number]['id']>('plan');
  const [previous, setPrevious] = useState<typeof mode | null>(null);
  const current = modes.find(item => item.id === mode)!;
  const lastMode = useRef(mode);
  const [decode, setDecode] = useState({ mode, progress: 1, tick: 0 });
  useEffect(() => {
    if (lastMode.current === mode) return;
    lastMode.current = mode;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDecode({ mode, progress: 1, tick: 0 }); return;
    }
    const started = performance.now();
    let frame = 0, last = 0;
    const draw = (time: number) => {
      const progress = document.hidden ? 1 : Math.min(1, (time - started) / 720);
      if (time - last > 40 || progress === 1) {
        last = time; setDecode({ mode, progress, tick: Math.floor((time - started) / 45) });
      }
      if (progress < 1) frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [mode]);
  const progress = decode.mode === mode ? decode.progress : 0;
  const select = (next: typeof mode) => {
    if (next === mode) return;
    setPrevious(mode);
    setMode(next);
  };

  return <div className={`learning-instrument${previous !== null ? ' has-switched' : ''}`}>
    <div className="li-content">
      <nav className="li-tabs" aria-label="探索小宇的工具">
        {modes.map(item => <button key={item.id} type="button" aria-pressed={mode === item.id} onClick={() => select(item.id)}>{item.label}</button>)}
      </nav>
      <div className="li-copy">
        <p data-decoding={progress < 1}><span className="sr-only">{current.description}</span><span aria-hidden="true">{Array.from(current.description).map((character, index, characters) =>
          <span key={index} data-glyph={index / characters.length >= progress ? ['0', '1', '{', '}', '/', '∷', '<', '>'][(index + decode.tick) % 8] : undefined}>{character}</span>)}</span></p>
        <div className="li-capabilities">{current.capabilities.map(capability => <span key={capability}>{capability}</span>)}</div>
      </div>
    </div>
    <div className="li-scene" data-landing-depth>
      <div className="li-art" role="img" aria-label={`${current.label}的动态线图`}><IntelligenceField mode={mode} /></div>
      {modes.map(item => <div key={item.id} className={`li-surfaces li-surfaces-${item.id}${mode === item.id ? ' is-active' : previous === item.id ? ' is-leaving' : ''}`} aria-hidden={mode !== item.id}>
        {item.screens.map(({ image, crop: [x, y, width, height] }, index) => <div key={image} className={`li-surface ${index ? 'li-surface-rear' : 'li-surface-front'}`} style={{ aspectRatio: `${width} / ${height}` }}>
          <img className="li-capture" src={`/screenshots/${image}`} alt={`${item.label}${index ? '的相关界面' : '的功能展示'}`} style={{ width: `${1280 / width * 100}%`, left: `${-x / width * 100}%`, top: `${-y / height * 100}%` }} />
          <img className="landing-scan-outline" src={`/screenshots/${image}`} alt="" aria-hidden="true" style={{ width: `${1280 / width * 100}%`, left: `${-x / width * 100}%`, top: `${-y / height * 100}%` }} />
          <span className="landing-scan-beam" aria-hidden="true" />
          <ScreenshotDissolve active={mode === item.id} />
        </div>)}
        <div className="li-ripple-floor" aria-hidden="true"><span /></div>
      </div>)}
    </div>
  </div>;
}

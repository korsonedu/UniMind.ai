import { useState } from 'react';
import { ArrowRight } from '@phosphor-icons/react';
import { ScreenshotDissolve } from './ScreenshotDissolve';

const scenes = [
  { label: '学习安排', image: 'landing-agent-plan-demo.webp', description: '根据学习记录安排复习与练习' },
  { label: '图像讲解', image: 'landing-agent-demo.webp', description: '调用工具绘制债券价格与收益率曲线' },
  { label: '知识关系', image: 'landing-agent-map-demo.webp', description: '关联知识点与当前掌握程度' },
  { label: '练习反馈', image: 'landing-agent-feedback-demo.webp', description: '展示已完成练习的批改与解析' },
];

export function AgentShowcase() {
  const [selected, setSelected] = useState(1);
  const [previous, setPrevious] = useState<number | null>(null);
  const select = (index: number) => {
    if (index === selected) return;
    setPrevious(selected);
    setSelected(index);
  };

  return <div className={`landing-agent-display${previous !== null ? ' has-switched' : ''}`}>
    <div className="landing-ui-frame landing-agent-frame landing-agent-showcase">
      <div className="landing-agent-images" aria-live="polite">
        {scenes.map((scene, index) => <div key={scene.image} className={`landing-agent-image${index === selected ? ' is-active' : index === previous ? ' is-leaving' : ''}`} aria-hidden={index !== selected}>
          <img className="landing-capture" src={`/screenshots/${scene.image}`} alt={`小宇${scene.label}界面，${scene.description}`} width="3840" height="2640" />
          <img className="landing-scan-outline" src={`/screenshots/${scene.image}`} alt="" aria-hidden="true" width="3840" height="2640" />
          <span className="landing-scan-beam" aria-hidden="true" />
          <ScreenshotDissolve active={index === selected} />
        </div>)}
      </div>
      <button type="button" className="landing-agent-launch" onClick={() => select((selected + 1) % scenes.length)} aria-label={`切换功能展示，当前为${scenes[selected].label}`} />
      {scenes.map((scene, index) => <button key={scene.image} type="button" className="landing-agent-scene" aria-label={`展示${scene.label}`} aria-pressed={index === selected} onClick={() => select(index)} style={{ left: `${93 / 1280 * 100}%`, top: `${(164.25 + index * 34) / 880 * 100}%`, width: `${141 / 1280 * 100}%`, height: `${29.5 / 880 * 100}%` }} />)}
    </div>
    <div className="landing-ripple-floor" aria-hidden="true">{scenes.map((scene, index) => <span key={scene.image} className={selected === index ? 'is-active' : ''} />)}</div>
    <nav className="landing-showcase-controls" aria-label="选择小宇展示">
      {scenes.map((scene, index) => <button key={scene.image} type="button" aria-label={`查看${scene.label}`} aria-pressed={index === selected} onClick={() => select(index)}><span /></button>)}
      <button type="button" className="landing-showcase-next" aria-label="下一个展示" onClick={() => select((selected + 1) % scenes.length)}><ArrowRight size={17} /></button>
    </nav>
  </div>;
}

import { useState } from 'react';
import { IntelligenceField } from './IntelligenceField';
import '@/styles/landing-instrument.css';

const modes = [
  { id: 'plan', label: '学习安排', description: '根据学习记录与知识掌握情况，安排学习与复习。', capabilities: ['学习记录', '知识掌握', '复习安排'] },
  { id: 'understand', label: '知识讲解', description: '检索课程与资料，用推导、图像和知识关系，把概念讲清楚。', capabilities: ['资料检索', '公式推导', '图像讲解', '知识关系'] },
  { id: 'practice', label: '练习反馈', description: '围绕正在学的内容出题，批改作答，让错题进入后续复习。', capabilities: ['随堂练习', '作答批改', '错题整理', 'Memorix'] },
] as const;

export function LearningInstrument() {
  const [mode, setMode] = useState<typeof modes[number]['id']>('plan');
  const current = modes.find(item => item.id === mode)!;

  return <div className="learning-instrument">
    <nav className="li-tabs" aria-label="探索小宇的工具">
      {modes.map(item => <button key={item.id} type="button" aria-pressed={mode === item.id} onClick={() => setMode(item.id)}>{item.label}</button>)}
    </nav>
    <div className="li-scene">
      <div className="li-copy" key={mode}>
        <p>{current.description}</p>
        <div className="li-capabilities">{current.capabilities.map(capability => <span key={capability}>{capability}</span>)}</div>
      </div>
      <div className="li-art" role="img" aria-label={`${current.label}的动态线图`}><IntelligenceField mode={mode} /></div>
    </div>
  </div>;
}

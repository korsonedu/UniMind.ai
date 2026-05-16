import React from 'react';
import { Radar, RadarChart as RechartsRadar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';

const DIMENSION_LABELS: Record<string, string> = {
  theory: '理论功底',
  logic: '逻辑表达',
  stress: '抗压能力',
  fluency: '语言流畅度',
  english: '英语水平',
};

interface Props {
  scores: Record<string, number>;
}

export const InterviewRadarChart: React.FC<Props> = ({ scores }) => {
  const data = Object.entries(DIMENSION_LABELS).map(([key, label]) => ({
    dimension: label,
    score: scores[key] ?? 0,
    fullMark: 100,
  }));

  return (
    <div className="w-full h-56">
      <ResponsiveContainer>
        <RechartsRadar data={data}>
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fontWeight: 600, fill: '#64748b' }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
          <Radar name="评分" dataKey="score" stroke="#6366f1" fill="#6366f1" fillOpacity={0.2} />
        </RechartsRadar>
      </ResponsiveContainer>
    </div>
  );
};

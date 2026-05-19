import React from 'react';
import { useTranslation } from 'react-i18next';
import { Radar, RadarChart as RechartsRadar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';

const getDimensionLabel = (key: string, t: (k: string) => string) => {
  const map: Record<string, string> = {
    theory: t('radarChart.theory'),
    logic: t('radarChart.logic'),
    stress: t('radarChart.stress'),
    fluency: t('radarChart.fluency'),
    english: t('radarChart.english'),
  };
  return map[key] || key;
};

interface Props {
  scores: Record<string, number>;
}

export const InterviewRadarChart: React.FC<Props> = ({ scores }) => {
  const { t } = useTranslation('interviews');
  const dims = ['theory', 'logic', 'stress', 'fluency', 'english'];
  const data = dims.map((key) => ({
    dimension: getDimensionLabel(key, t),
    score: scores[key] ?? 0,
    fullMark: 100,
  }));

  return (
    <div className="w-full h-48">
      <ResponsiveContainer>
        <RechartsRadar data={data}>
          <PolarGrid stroke="#e5e5e5" strokeWidth={0.5} />
          <PolarAngleAxis
            dataKey="dimension"
            tick={{ fontSize: 10, fontWeight: 500, fill: '#a3a3a3' }}
          />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
          <Radar
            name={t('radarChart.score')}
            dataKey="score"
            stroke="#171717"
            fill="#171717"
            fillOpacity={0.08}
            strokeWidth={1}
          />
        </RechartsRadar>
      </ResponsiveContainer>
    </div>
  );
};

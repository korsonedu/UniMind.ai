import React from 'react';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart3, LineChart, Sparkles } from 'lucide-react';

import { InsightsPanel } from './maintenance/InsightsPanel';
import { AnalyticsPanel } from './maintenance/AnalyticsPanel';
import { PipelinePanel } from './maintenance/PipelinePanel';

export const PlatformAnalytics: React.FC = () => {
  const { t } = useTranslation('maintenance');

  return (
    <div className="min-h-screen bg-[#F2F2F6] p-6 md:p-8 space-y-8 max-w-[1600px] mx-auto text-left">
      <Tabs defaultValue="analytics" className="space-y-8">
        <div className="sticky top-0 z-20 pt-2 pb-1 -mt-2">
          <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_8px_24px_rgba(0,0,0,0.04)] h-auto flex flex-wrap gap-0.5 w-fit mx-auto">
            <TabsTrigger value="insights" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <BarChart3 className="w-3.5 h-3.5" />{t('tabs.insights')}
            </TabsTrigger>
            <TabsTrigger value="analytics" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <LineChart className="w-3.5 h-3.5" />数据分析
            </TabsTrigger>
            <TabsTrigger value="pipeline" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Sparkles className="w-3.5 h-3.5" />{t('tabs.aiPipeline')}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="insights"><InsightsPanel /></TabsContent>
        <TabsContent value="analytics"><AnalyticsPanel /></TabsContent>
        <TabsContent value="pipeline"><PipelinePanel /></TabsContent>
      </Tabs>
    </div>
  );
};

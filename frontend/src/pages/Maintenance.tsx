import React from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/useAuthStore';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  BookOpen, FileText, Target, Bot, Sparkles, Bell, Tag,
  BrainCircuit, Layers, Rocket, BarChart3, LineChart,
} from 'lucide-react';

import { CourseSection } from './maintenance/CourseSection';
import { ArticleSection } from './maintenance/ArticleSection';
import { QuizSection } from './maintenance/QuizSection';
import { AlbumSection } from './maintenance/AlbumSection';
import { BotSection } from './maintenance/BotSection';
import { MaterialSection } from './maintenance/MaterialSection';
import { TagSection } from './maintenance/TagSection';
import { NotificationSection } from './maintenance/NotificationSection';
import { InsightsPanel } from './maintenance/InsightsPanel';
import { AnalyticsPanel } from './maintenance/AnalyticsPanel';
import { KnowledgeSystemPanel } from './maintenance/KnowledgeSystemPanel';
import { PipelinePanel } from './maintenance/PipelinePanel';

export const Maintenance: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const { user } = useAuthStore();
  const isPlatformAdmin = user?.is_admin;

  return (
    <div className="min-h-screen bg-[#F2F2F6] p-6 md:p-8 space-y-8 max-w-[1600px] mx-auto text-left">
      <Tabs defaultValue="courses" className="space-y-8">
        <div className="sticky top-0 z-20 pt-2 pb-1 -mt-2">
          <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_8px_24px_rgba(0,0,0,0.04)] h-auto flex flex-wrap gap-0.5 w-fit mx-auto">
            <TabsTrigger value="courses" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <BookOpen className="w-3.5 h-3.5" />{t('tabs.courseUpload')}
            </TabsTrigger>
            <TabsTrigger value="articles" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <FileText className="w-3.5 h-3.5" />{t('tabs.publishArticle')}
            </TabsTrigger>
            <TabsTrigger value="quizzes" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Target className="w-3.5 h-3.5" />{t('tabs.questionBank')}
            </TabsTrigger>
            <TabsTrigger value="kp" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <BrainCircuit className="w-3.5 h-3.5" />{t('tabs.knowledgeSystem')}
            </TabsTrigger>
            <TabsTrigger value="albums" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Layers className="w-3.5 h-3.5" />{t('tabs.albumManager')}
            </TabsTrigger>
            <TabsTrigger value="bots" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Bot className="w-3.5 h-3.5" />{t('tabs.aiBot')}
            </TabsTrigger>
            <TabsTrigger value="sm" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Rocket className="w-3.5 h-3.5" />{t('tabs.startupMaterials')}
            </TabsTrigger>
            <TabsTrigger value="tags" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Tag className="w-3.5 h-3.5" />标签
            </TabsTrigger>
            <TabsTrigger value="notifications" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Bell className="w-3.5 h-3.5" />{t('tabs.siteBroadcast')}
            </TabsTrigger>
            {isPlatformAdmin && (
              <>
                <TabsTrigger value="insights" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
                  <BarChart3 className="w-3.5 h-3.5" />{t('tabs.insights')}
                </TabsTrigger>
                <TabsTrigger value="analytics" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
                  <LineChart className="w-3.5 h-3.5" />数据分析
                </TabsTrigger>
                <TabsTrigger value="pipeline" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
                  <Sparkles className="w-3.5 h-3.5" />{t('tabs.aiPipeline')}
                </TabsTrigger>
              </>
            )}
          </TabsList>
        </div>

        <TabsContent value="courses"><CourseSection /></TabsContent>
        <TabsContent value="articles"><ArticleSection /></TabsContent>
        <TabsContent value="quizzes"><QuizSection /></TabsContent>
        <TabsContent value="kp"><KnowledgeSystemPanel /></TabsContent>
        <TabsContent value="albums"><AlbumSection /></TabsContent>
        <TabsContent value="bots"><BotSection /></TabsContent>
        <TabsContent value="sm"><MaterialSection /></TabsContent>
        <TabsContent value="tags"><TagSection /></TabsContent>
        <TabsContent value="notifications"><NotificationSection /></TabsContent>
        {isPlatformAdmin && (
          <>
            <TabsContent value="insights"><InsightsPanel /></TabsContent>
            <TabsContent value="analytics"><AnalyticsPanel /></TabsContent>
            <TabsContent value="pipeline"><PipelinePanel /></TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
};

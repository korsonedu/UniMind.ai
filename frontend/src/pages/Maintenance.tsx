import React from 'react';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Robot, Sparkle, Bell, Tag, Stack, Rocket, ChartBar, Users, Link } from '@phosphor-icons/react';

import { AlbumSection } from './maintenance/AlbumSection';
import { BotSection } from './maintenance/BotSection';
import { MaterialSection } from './maintenance/MaterialSection';
import { TagSection } from './maintenance/TagSection';
import { NotificationSection } from './maintenance/NotificationSection';
import { InsightsPanel } from './maintenance/InsightsPanel';
import { PipelinePanel } from './maintenance/PipelinePanel';
import { NotificationConfigSection } from './maintenance/NotificationConfigSection';
import { ClassSection } from './maintenance/ClassSection';
import { InstitutionInviteSection } from './maintenance/InstitutionInviteSection';

export const Maintenance: React.FC = () => {
  const { t } = useTranslation('maintenance');

  return (
    <div className="min-h-screen bg-[#F2F2F6] p-6 md:p-8 space-y-8 max-w-[1600px] mx-auto text-left">
      <Tabs defaultValue="albums" className="space-y-8">
        <div className="sticky top-0 z-20 pt-2 pb-1 -mt-2">
          <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_8px_24px_rgba(0,0,0,0.04)] h-auto flex flex-wrap gap-0.5 w-fit mx-auto">
            <TabsTrigger value="albums" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Stack className="w-3.5 h-3.5" />{t('tabs.albumManager')}
            </TabsTrigger>
            <TabsTrigger value="bots" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Robot className="w-3.5 h-3.5" />{t('tabs.aiBot')}
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
            <TabsTrigger value="classes" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Users className="w-3.5 h-3.5" />班级管理
            </TabsTrigger>
            <TabsTrigger value="notify-config" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Bell className="w-3.5 h-3.5" />复习提醒
            </TabsTrigger>
            <TabsTrigger value="insights" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <ChartBar className="w-3.5 h-3.5" />{t('tabs.insights')}
            </TabsTrigger>
            <TabsTrigger value="pipeline" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Sparkle className="w-3.5 h-3.5" />{t('tabs.aiPipeline')}
            </TabsTrigger>
            <TabsTrigger value="invites" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Link className="w-3.5 h-3.5" />邀请链接
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="albums"><AlbumSection /></TabsContent>
        <TabsContent value="bots"><BotSection /></TabsContent>
        <TabsContent value="sm"><MaterialSection /></TabsContent>
        <TabsContent value="tags"><TagSection /></TabsContent>
        <TabsContent value="notifications"><NotificationSection /></TabsContent>
        <TabsContent value="classes"><ClassSection /></TabsContent>
        <TabsContent value="notify-config"><NotificationConfigSection /></TabsContent>
        <TabsContent value="insights"><InsightsPanel /></TabsContent>
        <TabsContent value="pipeline"><PipelinePanel /></TabsContent>
        <TabsContent value="invites"><InstitutionInviteSection /></TabsContent>
      </Tabs>
    </div>
  );
};

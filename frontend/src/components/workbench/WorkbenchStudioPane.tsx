import { Sparkle } from '@phosphor-icons/react';
import { t } from '@/i18n';

export function WorkbenchStudioPane() {
  return <>
    <header className="um-wb-pane-header"><h2><Sparkle size={18} />Studio</h2></header>
    <div className="um-wb-studio-body">
      <div className="um-wb-overview-icon"><Sparkle size={24} weight="duotone" /></div>
      <h3>{t('项目学习材料')}</h3>
      <p className="um-wb-muted">{t('导读、闪卡与自测将在这里集中查看。')}</p>
    </div>
  </>;
}

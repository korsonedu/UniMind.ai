import { FileText } from 'lucide-react';
import { PromptTemplatesPanel } from './maintenance/PromptTemplatesPanel';
import { useTranslation } from 'react-i18next';

export const PromptTemplatesAdmin: React.FC = () => {
  const { t } = useTranslation('maintenance');
  return (
    <div className="p-6 space-y-6 animate-in fade-in duration-500 max-w-[1600px] mx-auto text-left">
      <div className="flex items-center gap-3 mb-6">
        <FileText className="h-6 w-6 text-indigo-600" />
        <h1 className="text-2xl font-bold tracking-tight">{t('promptTemplates.promptAdminTitle')}</h1>
      </div>
      <PromptTemplatesPanel />
    </div>
  );
};

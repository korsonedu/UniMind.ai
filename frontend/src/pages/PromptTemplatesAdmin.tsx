import { FileText } from 'lucide-react';
import { PromptTemplatesPanel } from './maintenance/PromptTemplatesPanel';

export const PromptTemplatesAdmin: React.FC = () => {
  return (
    <div className="p-6 space-y-6 animate-in fade-in duration-500 max-w-[1600px] mx-auto text-left">
      <div className="flex items-center gap-3 mb-6">
        <FileText className="h-6 w-6 text-indigo-600" />
        <h1 className="text-2xl font-bold tracking-tight">Prompt 模板管理</h1>
      </div>
      <PromptTemplatesPanel />
    </div>
  );
};

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { X, CaretRight, CaretDown, PencilSimple, Trash } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

export const TagInput = ({ tags, setTags, compact = false }: { tags: string[], setTags: (t: string[]) => void, compact?: boolean }) => {
  const [inputValue, setInputValue] = useState('');
  const { t } = useTranslation('maintenance');
  const addTag = () => {
    const val = inputValue.trim();
    if (val && !tags.includes(val)) {
      setTags([...tags, val]);
      setInputValue('');
    }
  };
  return (
    <div className="space-y-1.5 text-left">
      <div className="flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
          placeholder={t('components.tagPlaceholder')}
          className={cn("bg-unimind-bg-secondary border-none rounded-xl font-bold text-[11px]", compact ? "h-8 px-3" : "h-9 px-4")}
        />
      </div>
      <div className="flex flex-wrap gap-1 min-h-[1rem]">
        {tags.map((tag, i) => (
          <Badge key={`${tag}-${i}`} className="bg-black text-white hover:bg-black/80 gap-1 pl-2 pr-1 py-0.5 rounded-lg text-[11px] font-bold uppercase tracking-wider">
            {tag} <X className="w-2.5 h-2.5 cursor-pointer opacity-50 hover:opacity-100" onClick={() => setTags(tags.filter((_, idx) => idx !== i))} />
          </Badge>
        ))}
      </div>
    </div>
  );
};

export const KPTreeNode = ({ node, allNodes, onDelete, onEdit }: { node: any, allNodes: any[], onDelete: (id: number) => void, onEdit: (node: any) => void }) => {
  const [isOpen, setIsOpen] = useState(true);
  const children = allNodes.filter(n => n.parent === node.id);
  const hasChildren = children.length > 0;

  return (
    <div className="ml-4 border-l border-black/[0.03] pl-3 py-0.5">
      <div className="group flex items-center justify-between p-1.5 rounded-lg hover:bg-black/[0.02] transition-all">
        <div className="flex items-center gap-2 min-w-0 flex-1 cursor-pointer" onClick={() => setIsOpen(!isOpen)}>
          {hasChildren ? (
            isOpen ? <CaretDown className="w-3 h-3 opacity-30" /> : <CaretRight className="w-3 h-3 opacity-30" />
          ) : <div className="w-3" />}
          <p className="text-[11px] font-bold text-foreground truncate text-left">{node.name}</p>
        </div>
        <div className="flex gap-1 opacity-100 transition-opacity shrink-0">
          <Button onClick={() => onEdit(node)} variant="ghost" size="icon" className="h-6 w-6 rounded-md hover:bg-white shadow-sm text-blue-600"><PencilSimple className="w-3 h-3" /></Button>
          <Button onClick={() => onDelete(node.id)} variant="ghost" size="icon" className="h-6 w-6 rounded-md hover:bg-white shadow-sm text-red-500"><Trash className="w-3 h-3" /></Button>
        </div>
      </div>
      {isOpen && hasChildren && (
        <div className="mt-0.5">
          {children.map(child => <KPTreeNode key={child.id} node={child} allNodes={allNodes} onDelete={onDelete} onEdit={onEdit} />)}
        </div>
      )}
    </div>
  );
};

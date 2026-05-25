import React from 'react';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Bot as BotIcon, ChevronDown } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useTranslation } from 'react-i18next';

interface Bot {
  id: number;
  name: string;
  avatar: string;
  system_prompt: string;
  bot_type?: string;
}

interface BotSelectorProps {
  bots: Bot[];
  selectedBot: Bot | null;
  onSelect: (bot: Bot) => void;
}

export const BotSelector: React.FC<BotSelectorProps> = React.memo(({ bots, selectedBot, onSelect }) => {
  const { t } = useTranslation('aiAssistant');

  return (
    <div className="flex items-center gap-4 text-left">
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <div className="flex items-center gap-3 cursor-pointer group text-left" aria-haspopup="menu" aria-expanded="false">
            <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center shadow-lg overflow-hidden border border-white/10 group-hover:scale-105 transition-transform">
              {selectedBot?.avatar ? <img src={selectedBot.avatar} className="w-full h-full object-cover" /> : <BotIcon className="h-5 w-5 text-primary-foreground" />}
            </div>
            <div className="flex flex-col text-left">
              <div className="flex items-center gap-1.5">
                <h2 className="text-sm font-bold tracking-tight text-foreground">{selectedBot?.name || t('selectBot')}</h2>
                <ChevronDown className="w-3 h-3 opacity-30" />
              </div>
            </div>
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="w-64 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg" align="start">
           {bots.map(b => (
             <DropdownMenuItem key={b.id} onClick={() => onSelect(b)} className="rounded-xl py-3 px-4 flex items-center gap-3 cursor-pointer">
                <Avatar className="h-8 w-8 border border-border"><AvatarImage src={b.avatar}/><AvatarFallback>{b.name[0]}</AvatarFallback></Avatar>
                <span className="font-bold text-sm text-foreground">{b.name}</span>
             </DropdownMenuItem>
           ))}
           {bots.length === 0 && <div className="p-4 text-xs font-bold opacity-30 text-center uppercase text-foreground">No Custom Bots Available</div>}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
});

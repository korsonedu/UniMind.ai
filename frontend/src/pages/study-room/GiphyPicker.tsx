import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { FileVideo, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/lib/api';

interface GiphyPickerProps {
  onGifSent: (url: string) => void;
}

export const GiphyPicker: React.FC<GiphyPickerProps> = ({ onGifSent }) => {
  const { t } = useTranslation('studyRoom');
  const [giphySearch, setGiphySearch] = useState('');
  const [giphyResults, setGiphyResults] = useState<any[]>([]);
  const [isGiphyLoading, setIsGiphyLoading] = useState(false);

  const fetchGiphy = async (query: string, append = false) => {
    if (isGiphyLoading) return;
    const offset = append ? giphyResults.length : 0;
    setIsGiphyLoading(true);
    try {
      const params = new URLSearchParams({ offset: String(offset) });
      if (query) params.set('q', query);
      const res = await api.get(`/study/giphy/?${params.toString()}`);
      const data = res.data;
      if (data.data) {
        setGiphyResults(prev => append ? [...prev, ...data.data] : data.data);
      }
    } catch (e) {
      // 静默处理 GIPHY 加载失败
      setIsGiphyLoading(false);
      return;
    }
    finally { setIsGiphyLoading(false); }
  };

  const sendGif = async (url: string) => {
    onGifSent(url);
  };

  const handleGiphyScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 50) {
      fetchGiphy(giphySearch, true);
    }
  };

  return (
    <Popover onOpenChange={(open) => open && giphyResults.length === 0 && fetchGiphy('')}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
          <FileVideo className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent side="top" className="w-80 p-3 rounded-2xl border-border shadow-lg space-y-3 bg-card z-[100]">
        <Input
          placeholder={t('giphySearch')}
          value={giphySearch}
          onChange={e => { setGiphySearch(e.target.value); fetchGiphy(e.target.value); }}
          className="h-9 text-xs rounded-xl bg-muted border-none text-foreground placeholder:opacity-50 focus-visible:ring-1 focus-visible:ring-primary/20"
        />
        <div onScroll={handleGiphyScroll} className="grid grid-cols-4 gap-2 h-72 overflow-y-auto pr-1 scrollbar-thin">
          {giphyResults.map(g => (
            <div key={g.id} className="relative group/gif">
              <button
                type="button"
                onClick={() => sendGif(g.images.original.url)}
                className="w-full aspect-square rounded-lg overflow-hidden bg-muted transition-all hover:ring-2 ring-primary"
              >
                <img src={g.images.fixed_height_small.url} className="w-full h-full object-cover" />
              </button>
              <div className="absolute left-1/2 bottom-full mb-2 -translate-x-1/2 scale-0 group-hover/gif:scale-100 transition-all z-[110] pointer-events-none origin-bottom">
                <div className="w-32 aspect-square rounded-xl overflow-hidden shadow-lg border-2 border-primary bg-card">
                  <img src={g.images.fixed_height_small.url} className="w-full h-full object-cover" />
                </div>
              </div>
            </div>
          ))}
          {isGiphyLoading && (
            <div className="col-span-4 py-2 flex justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground opacity-30" />
            </div>
          )}
        </div>
        <p className="text-[11px] text-center text-muted-foreground font-bold opacity-50 uppercase tracking-tighter">Powered by GIPHY</p>
      </PopoverContent>
    </Popover>
  );
};

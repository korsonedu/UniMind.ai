import React, { useState, useEffect, useRef } from 'react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { X } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

interface TagOption {
  id: number;
  name: string;
  slug: string;
}

interface Props {
  tags: string[];
  setTags: (t: string[]) => void;
  compact?: boolean;
}

export const TagAutocomplete: React.FC<Props> = ({ tags, setTags, compact = false }) => {
  const [inputValue, setInputValue] = useState('');
  const [allTags, setAllTags] = useState<TagOption[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get('/courses/tags/').then(r => setAllTags(r.data || [])).catch(() => {});
  }, []);

  const filtered = inputValue.trim()
    ? allTags.filter(t =>
        t.name.toLowerCase().includes(inputValue.trim().toLowerCase()) &&
        !tags.includes(t.name)
      ).slice(0, 5)
    : [];

  const addTag = (name: string) => {
    const val = name.trim();
    if (val && !tags.includes(val)) {
      setTags([...tags, val]);
    }
    setInputValue('');
    setShowSuggestions(false);
    setSelectedIndex(0);
    inputRef.current?.focus();
  };

  const removeTag = (idx: number) => {
    setTags(tags.filter((_, i) => i !== idx));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const f = filtered;
      if (f.length > 0 && selectedIndex >= 0 && selectedIndex < f.length) {
        addTag(f[selectedIndex].name);
      } else if (inputValue.trim()) {
        addTag(inputValue.trim());
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  useEffect(() => {
    setSelectedIndex(0);
    setShowSuggestions(filtered.length > 0);
  }, [inputValue]);

  return (
    <div className="space-y-1.5 text-left relative">
      <div className="flex gap-2">
        <Input
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onFocus={() => filtered.length > 0 && setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder="输入标签，回车添加"
          className={cn(
            "bg-unimind-bg-secondary border-none rounded-xl font-bold text-[11px]",
            compact ? "h-8 px-3" : "h-9 px-4"
          )}
        />
      </div>
      {showSuggestions && filtered.length > 0 && (
        <div className="absolute z-50 left-0 right-0 bg-white border border-border rounded-xl shadow-lg mt-1 py-1 overflow-hidden">
          {filtered.map((t, i) => (
            <div
              key={t.id}
              className={cn(
                "px-3 py-1.5 text-[11px] font-bold cursor-pointer transition-colors",
                i === selectedIndex ? "bg-black text-white" : "hover:bg-slate-100"
              )}
              onMouseDown={(e) => { e.preventDefault(); addTag(t.name); }}
              onMouseEnter={() => setSelectedIndex(i)}
            >
              {t.name}
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1 min-h-[1rem]">
        {tags.map((tag, i) => (
          <Badge
            key={i}
            className="bg-black text-white hover:bg-black/80 gap-1 pl-2 pr-1 py-0.5 rounded-lg text-[11px] font-bold uppercase tracking-wider"
          >
            {tag}
            <X className="w-2.5 h-2.5 cursor-pointer opacity-50 hover:opacity-100" onClick={() => removeTag(i)} />
          </Badge>
        ))}
      </div>
    </div>
  );
};

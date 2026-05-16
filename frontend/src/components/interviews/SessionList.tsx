import React from 'react';
import { Card } from '@/components/ui/card';

interface SessionItem {
  id: number;
  session_type: string;
  interviewer_style: string;
  status: string;
}

interface Props {
  sessions: SessionItem[];
  activeId: number;
  onSelect: (id: number) => void;
}

export const SessionList: React.FC<Props> = ({ sessions, activeId, onSelect }) => (
  <Card className="lg:col-span-1 p-3 rounded-2xl border border-border/60 space-y-2">
    {(sessions || []).map((s) => (
      <button
        key={s.id}
        onClick={() => onSelect(s.id)}
        className={`w-full text-left rounded-xl border px-3 py-2 ${
          s.id === activeId ? 'border-indigo-400 bg-indigo-50/70' : 'border-border/60'
        }`}
      >
        <p className="text-sm font-black">Session #{s.id}</p>
        <p className="text-xs text-muted-foreground mt-1">
          {s.session_type} · {s.interviewer_style} · {s.status}
        </p>
      </button>
    ))}
  </Card>
);

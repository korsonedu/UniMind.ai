import React from 'react';
import { Clock, CheckCircle2, Circle } from 'lucide-react';

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

const TYPE_LABEL: Record<string, string> = {
  resume: '简历深挖', english: '英语口语', professional: '专业课', mixed: '综合面试',
};

export const SessionList: React.FC<Props> = ({ sessions, activeId, onSelect }) => (
  <div className="space-y-0.5 pr-2">
    {(sessions || []).map((s) => {
      const isActive = s.id === activeId;
      const isCompleted = s.status === 'completed';
      const isAnalyzing = s.status === 'analyzing';

      return (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className={`w-full text-left px-3 py-2.5 rounded-md transition-colors flex items-center gap-3 ${
            isActive
              ? 'bg-neutral-100'
              : 'hover:bg-neutral-50'
          }`}
        >
          {/* Status icon */}
          <span className="shrink-0">
            {isCompleted ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            ) : isAnalyzing ? (
              <Clock className="h-3.5 w-3.5 text-amber-500 animate-pulse" />
            ) : (
              <Circle className="h-3.5 w-3.5 text-neutral-300" />
            )}
          </span>
          {/* Content */}
          <div className="min-w-0">
            <p className={`text-[13px] font-semibold truncate ${isActive ? 'text-neutral-900' : 'text-neutral-700'}`}>
              Session {s.id}
            </p>
            <p className="text-[11px] text-neutral-400 font-medium truncate mt-0.5">
              {TYPE_LABEL[s.session_type] || s.session_type}
            </p>
          </div>
        </button>
      );
    })}
  </div>
);

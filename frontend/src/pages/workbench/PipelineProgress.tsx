import { cn } from '@/lib/utils';
import { Loader2, CheckCircle2 } from 'lucide-react';

interface StageInfo {
  stage: string;
  count?: number;
  difficulty?: string;
  timestamp?: string;
}

interface Props {
  progress: number;
  currentStage: string;
  statusText: string;
  stages: StageInfo[];
  status: string;
}

const STAGES = [
  { key: 'author', label: 'Author 生成', threshold: 30 },
  { key: 'review', label: 'Reviewer 评审', threshold: 70 },
  { key: 'classify', label: 'Classifier 审计', threshold: 95 },
];

function stageActive(stageKey: string, currentStage: string, progress: number) {
  const stage = STAGES.find(s => s.key === stageKey);
  if (!stage) return false;
  if (currentStage.startsWith(stageKey)) return true;
  if (stageKey === 'author' && progress >= 5 && progress < 40) return true;
  if (stageKey === 'review' && progress >= 40 && progress < 75) return true;
  if (stageKey === 'classify' && progress >= 75 && progress < 100) return true;
  return false;
}

function stageDone(stageKey: string, progress: number) {
  const stage = STAGES.find(s => s.key === stageKey);
  return stage ? progress >= stage.threshold : false;
}

export default function PipelineProgress({ progress, currentStage, statusText, stages, status }: Props) {
  const isRunning = status === 'running';
  const isCompleted = status === 'completed';
  const isFailed = status === 'failed';

  return (
    <div className="space-y-6">
      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-bold text-foreground">
            {isFailed ? '管线失败' : isCompleted ? '管线完成' : 'ARC 管线运行中'}
          </span>
          <span className="text-sm font-bold text-primary">{progress}%</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-700',
              isFailed ? 'bg-red-400' : isCompleted ? 'bg-unimind-green' : 'bg-primary',
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
        {statusText && (
          <p className="text-xs text-unimind-text-tertiary mt-1.5">
            {isRunning && <Loader2 className="h-3 w-3 inline animate-spin mr-1" />}
            {statusText}
          </p>
        )}
      </div>

      {/* Stage stepper */}
      <div className="flex items-center gap-2">
        {STAGES.map((stage, i) => {
          const active = stageActive(stage.key, currentStage, progress);
          const done = stageDone(stage.key, progress);
          return (
            <div key={stage.key} className="flex items-center gap-2 flex-1">
              <div className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-all',
                done ? 'bg-unimind-green/10 text-unimind-green' :
                active ? 'bg-primary/10 text-primary' :
                'bg-muted text-unimind-text-quaternary',
              )}>
                {done ? <CheckCircle2 className="h-3.5 w-3.5" /> :
                 active ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                 <span className="h-3.5 w-3.5 rounded-full border-2 border-current" />}
                {stage.label}
              </div>
              {i < STAGES.length - 1 && (
                <div className={cn('flex-1 h-px', done ? 'bg-unimind-green' : 'bg-border')} />
              )}
            </div>
          );
        })}
      </div>

      {/* Stage log */}
      {stages.length > 0 && (
        <div className="space-y-1.5">
          {stages.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-unimind-text-secondary">
              <span className="w-1.5 h-1.5 rounded-full bg-primary/40 shrink-0" />
              <span className="font-medium">{s.stage}</span>
              {s.count != null && <span className="text-unimind-text-quaternary">({s.count} 题)</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

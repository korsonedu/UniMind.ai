import React, { useRef, useEffect } from 'react';
import { X, Loader2, CheckCircle2, XCircle, Upload, FileWarning } from 'lucide-react';
import { useUploadStore } from '@/store/useUploadStore';
import { cn } from '@/lib/utils';

const statusIcon = (status: string) => {
  switch (status) {
    case 'uploading': return <Upload className="w-4 h-4 animate-pulse text-blue-400" />;
    case 'processing': return <Loader2 className="w-4 h-4 animate-spin text-amber-400" />;
    case 'completed': return <CheckCircle2 className="w-4 h-4 text-green-400" />;
    case 'failed': return <XCircle className="w-4 h-4 text-red-400" />;
    case 'cancelled': return <FileWarning className="w-4 h-4 text-zinc-400" />;
    default: return null;
  }
};

const statusLabel = (status: string) => {
  switch (status) {
    case 'uploading': return '上传中';
    case 'processing': return '处理中';
    case 'completed': return '完成';
    case 'failed': return '失败';
    case 'cancelled': return '已取消';
    default: return '';
  }
};

export const PersistentUploadToast: React.FC = () => {
  const { tasks, cancelTask, removeTask } = useUploadStore();
  const timeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach(t => clearTimeout(t));
      timeoutsRef.current.clear();
    };
  }, []);

  if (tasks.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {tasks.map((task) => {
        const isDone = task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled';

        return (
          <div
            key={task.id}
            className={cn(
              'pointer-events-auto bg-zinc-900/95 backdrop-blur border rounded-lg p-3 shadow-xl',
              task.status === 'failed' ? 'border-red-700/50' :
              task.status === 'cancelled' ? 'border-zinc-700/50' :
              task.status === 'completed' ? 'border-green-700/50' :
              'border-zinc-700/50',
            )}
            onAnimationEnd={() => {
              if (isDone && !timeoutsRef.current.has(task.id)) {
                const t = setTimeout(() => {
                  timeoutsRef.current.delete(task.id);
                  removeTask(task.id);
                }, 5000);
                timeoutsRef.current.set(task.id, t);
              }
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 min-w-0">
                {statusIcon(task.status)}
                <span className="text-sm font-medium text-zinc-200 truncate">
                  {task.fileName}
                </span>
              </div>
              <div className="flex items-center gap-1 ml-2 shrink-0">
                <span className="text-xs text-zinc-400">{statusLabel(task.status)}</span>
                {task.status === 'uploading' && (
                  <button
                    onClick={() => cancelTask(task.id)}
                    className="ml-1 p-0.5 rounded hover:bg-zinc-700/50 text-zinc-400 hover:text-zinc-200 transition-colors"
                    title="取消上传"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
                {isDone && (
                  <button
                    onClick={() => removeTask(task.id)}
                    className="p-0.5 rounded hover:bg-zinc-700/50 text-zinc-400 hover:text-zinc-200 transition-colors"
                    title="关闭"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {task.status === 'uploading' && (
              <div className="w-full bg-zinc-700 rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${task.progress}%` }}
                />
              </div>
            )}

            {task.error && (
              <p className="text-xs text-red-400 mt-1 truncate">{task.error}</p>
            )}
          </div>
        );
      })}
    </div>
  );
};

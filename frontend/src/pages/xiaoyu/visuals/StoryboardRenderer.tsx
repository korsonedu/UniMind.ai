import React, { useState } from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';

export interface StoryboardFrame {
  step?: number;
  heading: string;
  board: string;
  formula?: string;
  takeaway?: string;
  pitfall?: string;
}

export interface StoryboardPayload {
  title: string;
  subtitle?: string;
  frames: StoryboardFrame[];
}

export const StoryboardRenderer: React.FC<{ payload: StoryboardPayload }> = ({ payload }) => {
  const frames = Array.isArray(payload?.frames) ? payload.frames : [];
  const [viewAll, setViewAll] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  if (!frames.length) return null;
  const safeIndex = Math.min(activeIndex, frames.length - 1);
  const visibleFrames = viewAll ? frames : [frames[safeIndex]];

  return (
    <div className="um-storyboard">
      <div className="um-storyboard-header">
        <div className="um-visual-heading" style={{ marginBottom: 0 }}>
          {payload.title && <h3>{payload.title}</h3>}
          {payload.subtitle && <p>{payload.subtitle}</p>}
        </div>
        <button
          type="button"
          className="um-storyboard-mode-btn"
          onClick={() => setViewAll(prev => !prev)}
        >
          {viewAll ? '逐帧板书' : `展开全部 (${frames.length} 步)`}
        </button>
      </div>

      {!viewAll && frames.length > 1 && (
        <div className="um-storyboard-tabs" role="tablist" aria-label="分步板书步骤">
          {frames.map((frame, index) => (
            <button
              key={index}
              type="button"
              role="tab"
              aria-selected={index === safeIndex}
              className={`um-storyboard-tab${index === safeIndex ? ' is-active' : ''}`}
              onClick={() => setActiveIndex(index)}
            >
              <span>Step {frame.step ?? index + 1}</span>
              <span className="um-storyboard-tab-title">{frame.heading}</span>
            </button>
          ))}
        </div>
      )}

      <ol className="um-storyboard-frames">
        {visibleFrames.map((frame, idx) => {
          const stepNumber = frame.step ?? (viewAll ? idx + 1 : safeIndex + 1);
          return (
            <li key={stepNumber} className="um-storyboard-frame">
              <div className="um-storyboard-frame-head">
                <span className="um-storyboard-step-badge">STEP {String(stepNumber).padStart(2, '0')}</span>
                <h4>{frame.heading}</h4>
              </div>
              <div className="um-storyboard-board">
                <MarkdownContent content={frame.board} className="prose prose-sm max-w-none dark:prose-invert" />
                {frame.formula && (
                  <div className="um-visual-formula">
                    <MarkdownContent content={`$$${frame.formula.replace(/^\$\$|\$\$$/g, '').trim()}$$`} />
                  </div>
                )}
              </div>
              {(frame.takeaway || frame.pitfall) && (
                <div className="um-storyboard-notes">
                  {frame.takeaway && <p className="um-storyboard-takeaway">💡 {frame.takeaway}</p>}
                  {frame.pitfall && <p className="um-storyboard-pitfall">⚠️ {frame.pitfall}</p>}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {!viewAll && frames.length > 1 && (
        <div className="um-storyboard-nav">
          <button
            type="button"
            disabled={safeIndex === 0}
            onClick={() => setActiveIndex(prev => Math.max(0, prev - 1))}
          >
            ← 上一步
          </button>
          <span className="text-xs text-muted-foreground">
            {safeIndex + 1} / {frames.length}
          </span>
          <button
            type="button"
            disabled={safeIndex >= frames.length - 1}
            onClick={() => setActiveIndex(prev => Math.min(frames.length - 1, prev + 1))}
          >
            下一步 →
          </button>
        </div>
      )}
    </div>
  );
};

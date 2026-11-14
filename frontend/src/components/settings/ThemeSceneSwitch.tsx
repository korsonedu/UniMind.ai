import { t, useLocale } from '@/i18n';
import { useEffect, useId, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import type { ThemeMode } from '@/store/useSystemStore';
import { createThemeScene } from './themeScene';
import './theme-scene-switch.css';

const MODES = [
  { value: 'light', label: '亮色', icon: '☀' },
  { value: 'system', label: '跟随系统', icon: '◐' },
  { value: 'dark', label: '暗色', icon: '☾' },
] as const;

export function ThemeSceneSwitch({ value, onChange, reduceMotion }: {
  value: ThemeMode; onChange: (value: ThemeMode) => void; reduceMotion: boolean;
}) {
  useLocale();
  const id = useId();
  const canvas = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<ReturnType<typeof createThemeScene> | null>(null);
  const radios = useRef<(HTMLInputElement | null)[]>([]);
  const drag = useRef<{ pointer: number; position: number } | null>(null);
  const [preview, setPreview] = useState<number | null>(null);
  const [systemReduced, setSystemReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const selected = MODES.findIndex(mode => mode.value === value);
  const position = preview ?? selected;
  const daylight = 1 - position / 2;
  const reduced = reduceMotion || systemReduced;

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateMotion = () => setSystemReduced(motion.matches);
    motion.addEventListener('change', updateMotion);
    return () => { motion.removeEventListener('change', updateMotion); };
  }, []);
  useEffect(() => {
    renderer.current = createThemeScene(canvas.current!, reduced);
    return () => { renderer.current?.destroy(); renderer.current = null; };
  }, [reduced]);
  useEffect(() => { renderer.current?.update(position, daylight); }, [position, daylight, reduced]);

  const pointerPosition = (event: PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(2, ((event.clientX - bounds.left) / bounds.width * 176 - 24) / 64));
  };
  const finish = (event: PointerEvent<HTMLDivElement>, commit: boolean) => {
    if (drag.current?.pointer !== event.pointerId) return;
    const next = Math.round(drag.current.position);
    drag.current = null; setPreview(null);
    if (commit) { onChange(MODES[next].value); radios.current[next]?.focus(); }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return <div className="um-theme-switch" role="radiogroup" aria-labelledby="settings-appearance">
    <div className="um-theme-switch-mould" data-night={daylight < .5}>
      <div className="um-theme-switch-track" aria-hidden="true"
        onPointerDown={event => {
          if (!event.isPrimary || event.button !== 0) return;
          event.preventDefault(); const next = pointerPosition(event);
          drag.current = { pointer: event.pointerId, position: next };
          event.currentTarget.setPointerCapture(event.pointerId); setPreview(next);
        }}
        onPointerMove={event => {
          if (drag.current?.pointer !== event.pointerId) return;
          const next = pointerPosition(event); drag.current.position = next; setPreview(next);
        }}
        onPointerUp={event => finish(event, true)} onPointerCancel={event => finish(event, false)}
        onLostPointerCapture={event => finish(event, false)}>
        <canvas ref={canvas} />
      </div>
    </div>
    <div className="um-theme-switch-labels">{MODES.map((mode, index) => <label key={mode.value} data-selected={value === mode.value}>
      <input ref={node => { radios.current[index] = node; }} type="radio" name={id} value={mode.value}
        checked={value === mode.value} onChange={() => onChange(mode.value)} />
      <span className="um-theme-switch-label-content"><span aria-hidden="true">{mode.icon}</span>{t(mode.label)}</span>
    </label>)}</div>
  </div>;
}

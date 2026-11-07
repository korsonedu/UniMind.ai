import { useCallback, useContext, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { SidebarSimple } from '@phosphor-icons/react';
import { NotesSidebarContext } from '@/components/WorkspaceContext';
import { clampLessonWidth, isLessonSidebarNarrow, lessonDragBounds, lessonSplitBounds } from './lessonSplitBounds';

const STORAGE_KEY = 'unimind-lesson-sidebar-width';
const COLLAPSED_KEY = 'unimind-lesson-sidebar-collapsed';
const WIDE_KEY = 'unimind-lesson-wide-layout';

export function LessonLayout({ aspectRatio, toolbarHost, revealKey, children }: { aspectRatio: number; toolbarHost?: HTMLElement | null; revealKey?: string | null; children: (controls: { sidebarCollapsed: boolean; expandSidebar: () => void }) => ReactNode }) {
  const notesSidebar = useContext(NotesSidebarContext);
  const root = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const handle = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; x: number; width: number; latest: number; minimum: number; wide: boolean } | null>(null);
  const [resizing, setResizing] = useState(false);
  const [dragPreview, setDragPreview] = useState<{ width: number; wide: boolean } | null>(null);
  const [manualWide, setManualWide] = useState(() => {
    try { return localStorage.getItem(WIDE_KEY) === '1'; } catch { return false; }
  });
  const [collapsePreference, setCollapsePreference] = useState(() => {
    let value = false;
    try { value = localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { /* Storage may be disabled. */ }
    return { value: value && !revealKey, revealKey };
  });
  const collapsed = collapsePreference.revealKey === revealKey && collapsePreference.value;
  const previousCollapsed = useRef(collapsed);
  const [metrics, setMetrics] = useState({ available: 0, fullAvailable: 0, height: 0, sidebar: 320, gap: 28, desktop: false });
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(() => {
    try {
      const saved = Number(localStorage.getItem(STORAGE_KEY));
      return Number.isFinite(saved) && saved >= 300 && saved <= 640 ? saved : null;
    } catch { return null; }
  });

  const cancelDrag = useCallback(() => {
    const current = drag.current;
    drag.current = null;
    setResizing(false);
    setDragPreview(null);
    if (current && handle.current?.hasPointerCapture(current.pointerId)) handle.current.releasePointerCapture(current.pointerId);
  }, []);

  useLayoutEffect(() => {
    const element = root.current;
    if (!element) return;
    const measure = () => {
      const style = getComputedStyle(element);
      const desktop = window.matchMedia('(min-width: 1024px)').matches;
      if (!desktop && drag.current) cancelDrag();
      const sidebar = parseFloat(style.getPropertyValue('--um-lesson-side-width')) || 320;
      const gap = parseFloat(style.getPropertyValue('--um-lesson-gap')) || 28;
      const parent = element.parentElement!;
      const parentStyle = getComputedStyle(parent);
      const parentWidth = parent.clientWidth - parseFloat(parentStyle.paddingLeft) - parseFloat(parentStyle.paddingRight);
      const inset = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      setMetrics({
        // Measure the expanded budget independently of the collapsed root width.
        available: Math.min(parentWidth - inset, window.innerHeight * .7 * aspectRatio + sidebar + gap),
        fullAvailable: Math.max(0, parentWidth - inset),
        height: window.innerHeight,
        sidebar,
        gap,
        desktop,
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.parentElement) observer.observe(element.parentElement);
    window.addEventListener('resize', measure);
    window.addEventListener('blur', cancelDrag);
    return () => { cancelDrag(); observer.disconnect(); window.removeEventListener('resize', measure); window.removeEventListener('blur', cancelDrag); };
  }, [aspectRatio, cancelDrag]);

  useLayoutEffect(() => {
    if (previousCollapsed.current === collapsed) return;
    previousCollapsed.current = collapsed;
    const target = toggle.current ?? handle.current;
    target?.focus({ preventScroll: true });
  }, [collapsed]);

  const compactBounds = lessonSplitBounds(metrics.available, metrics.height, aspectRatio, metrics.sidebar, metrics.gap);
  const available = manualWide ? metrics.fullAvailable : metrics.available;
  const bounds = lessonSplitBounds(available, metrics.height, aspectRatio, metrics.sidebar, metrics.gap, manualWide);
  const previewAvailable = dragPreview?.wide ? metrics.fullAvailable : available;
  const dragBounds = lessonDragBounds(previewAvailable, metrics.gap, bounds);
  const width = clampLessonWidth(available - metrics.gap - (sidebarWidth ?? metrics.sidebar), bounds);
  const sidebarCollapsed = metrics.desktop && (collapsed || notesSidebar.open);
  const expandedWidth = dragPreview ? Math.min(dragPreview.width, dragBounds.max) : width;
  const sidebarNarrow = metrics.desktop && !sidebarCollapsed && isLessonSidebarNarrow(expandedWidth, previewAvailable, metrics.gap);
  const compressing = metrics.desktop && !sidebarCollapsed && previewAvailable - metrics.gap - expandedWidth < metrics.sidebar;
  const displayedWidth = sidebarCollapsed ? metrics.fullAvailable : expandedWidth;
  const layoutWide = metrics.desktop && (sidebarCollapsed || manualWide || dragPreview?.wide);
  const saveWide = useCallback((value: boolean) => {
    setManualWide(value);
    try { localStorage.setItem(WIDE_KEY, value ? '1' : '0'); } catch { /* Storage may be disabled. */ }
  }, []);
  const setCollapsedPreference = useCallback((value: boolean) => {
    if (!value) saveWide(false);
    setCollapsePreference({ value, revealKey });
    try { localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0'); } catch { /* Storage may be disabled. */ }
  }, [saveWide, revealKey]);
  const expandSidebar = useCallback(() => { if (notesSidebar.open) notesSidebar.close(); setCollapsedPreference(false); }, [notesSidebar, setCollapsedPreference]);
  const setWidth = (value: number, persist = false, wide = manualWide) => {
    const budget = wide ? metrics.fullAvailable : metrics.available;
    const limits = lessonSplitBounds(budget, metrics.height, aspectRatio, metrics.sidebar, metrics.gap, wide);
    const next = budget - metrics.gap - clampLessonWidth(value, limits);
    setSidebarWidth(next);
    if (persist) {
      saveWide(wide);
      try { localStorage.setItem(STORAGE_KEY, String(next)); } catch { /* Storage may be disabled. */ }
    }
  };
  const finish = (element: HTMLDivElement) => {
    const current = drag.current;
    if (!current) return;
    drag.current = null;
    setResizing(false);
    setDragPreview(null);
    if (isLessonSidebarNarrow(current.latest, current.wide ? metrics.fullAvailable : metrics.available, metrics.gap)) setCollapsedPreference(true);
    else setWidth(current.latest, true, current.wide);
    if (element.hasPointerCapture(current.pointerId)) element.releasePointerCapture(current.pointerId);
  };

  const move = (clientX: number) => {
    const current = drag.current;
    if (!current) return;
    const raw = current.width + clientX - current.x;
    // Only release the outer width after the pointer actually expands past the
    // compact player. Keep the start width so this transition never moves the line.
    current.wide = current.wide || raw > compactBounds.max + .5;
    const budget = current.wide ? metrics.fullAvailable : metrics.available;
    current.latest = clampLessonWidth(raw, lessonDragBounds(budget, metrics.gap, { min: current.minimum, max: 0 }));
    setDragPreview({ width: current.latest, wide: current.wide });
  };

  return <div ref={root} className="um-lesson" data-split={metrics.desktop || undefined} data-layout-wide={layoutWide || undefined} data-sidebar-collapsed={sidebarCollapsed || undefined} data-sidebar-narrow={sidebarNarrow || undefined} data-compressing={compressing || undefined} data-resizing={resizing || undefined} style={{ '--um-video-aspect-ratio': aspectRatio, '--um-lesson-video-width': `${displayedWidth}px` } as CSSProperties}>
    {toolbarHost && metrics.desktop && createPortal(<button ref={toggle} type="button" className="um-course-directory-toggle" aria-label={sidebarCollapsed ? '展开学习侧栏' : '收起学习侧栏'} title={sidebarCollapsed ? '展开学习侧栏' : '收起学习侧栏'} aria-expanded={!sidebarCollapsed} onClick={() => sidebarCollapsed ? expandSidebar() : setCollapsedPreference(true)}><SidebarSimple size={18} /></button>, toolbarHost)}
    {children({ sidebarCollapsed, expandSidebar })}
    {metrics.desktop && !sidebarCollapsed && <div ref={handle} className="um-lesson-resize" role="separator" aria-label="调整视频与学习侧栏宽度" title="拖动调整宽度，拖至右侧窄带后松开收起侧栏；按 Enter 收起" aria-orientation="vertical" aria-valuemin={Math.round(bounds.min)} aria-valuemax={Math.round(resizing ? dragBounds.max : bounds.max)} aria-valuenow={Math.round(displayedWidth)} aria-valuetext={`视频宽度 ${Math.round(displayedWidth)} 像素；按 Enter 收起学习侧栏`} tabIndex={0}
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); cancelDrag(); return; }
        if (event.key === 'Enter') { event.preventDefault(); cancelDrag(); setCollapsedPreference(true); return; }
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        setWidth(event.key === 'Home' ? bounds.min : event.key === 'End' ? bounds.max : displayedWidth + (event.key === 'ArrowLeft' ? -16 : 16), true);
      }}
      onPointerDown={event => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.focus();
        drag.current = { pointerId: event.pointerId, x: event.clientX, width: displayedWidth, latest: displayedWidth, minimum: bounds.min, wide: manualWide };
        setDragPreview({ width: displayedWidth, wide: manualWide });
        event.currentTarget.setPointerCapture(event.pointerId);
        setResizing(true);
      }}
      onPointerMove={event => {
        const current = drag.current;
        if (!current || current.pointerId !== event.pointerId) return;
        move(event.clientX);
      }}
      onPointerUp={event => {
        const current = drag.current;
        if (!current || current.pointerId !== event.pointerId) return;
        move(event.clientX);
        finish(event.currentTarget);
      }}
      onPointerCancel={event => { if (drag.current?.pointerId === event.pointerId) cancelDrag(); }}
      onLostPointerCapture={event => { if (drag.current?.pointerId === event.pointerId) cancelDrag(); }}
    >{resizing && sidebarNarrow && <span className="um-lesson-resize-tip" role="status">松开收起学习侧栏</span>}</div>}
  </div>;
}

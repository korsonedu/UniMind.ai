export interface VideoKeyboardEvent {
  key: string;
  code?: string;
  repeat?: boolean;
  altKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
  target?: unknown;
}

export function shouldTogglePlayback(event: VideoKeyboardEvent): boolean {
  if (event.key !== ' ' && event.code !== 'Space') return false;
  if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false;
  const target = event.target as { tagName?: string; isContentEditable?: boolean } | null | undefined;
  if (target?.isContentEditable) return false;
  return !['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(target?.tagName?.toUpperCase() || '');
}

// Per-tab space selection. A space switch reloads the shell so no live query,
// conversation, draft or WebSocket can silently continue in the other space.
const key = 'unimind-active-workspace';

export function activeWorkspace(): string {
  return sessionStorage.getItem(key) || 'personal';
}

export function setActiveWorkspace(id: number | null) {
  if (id === null) sessionStorage.removeItem(key);
  else sessionStorage.setItem(key, String(id));
}

export function spaceStorageKey(name: string) {
  const space = activeWorkspace();
  return space === 'personal' ? name : `${name}:workspace:${space}`;
}

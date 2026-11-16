/** Reveal local learning steps without calling AI or starting a server job. */
export function demoPlaybackStage<T>(steps: readonly T[], stage: number): T[] {
  const count = Number.isFinite(stage) ? Math.max(0, Math.min(steps.length, Math.floor(stage))) : 0;
  return steps.slice(0, count);
}

import type { TranscriptSegmentItem } from '../shared/types';

export function fullWorkbenchTranscript(segments: readonly TranscriptSegmentItem[]): TranscriptSegmentItem[] {
  const unique = new Map<string, TranscriptSegmentItem>();
  for (const segment of segments) {
    if (typeof segment?.text !== 'string') continue;
    const { start_time, end_time } = segment;
    const text = segment.text.trim();
    if (!text || !Number.isFinite(start_time) || !Number.isFinite(end_time)
        || start_time < 0 || end_time < start_time || end_time > 2_147_483_647) continue;
    unique.set(JSON.stringify([start_time, end_time, text]), { start_time, end_time, text });
  }
  return [...unique.values()].sort((a, b) => a.start_time - b.start_time).slice(0, 5000);
}

export function readPlayerSubtitles(video: HTMLVideoElement | null): TranscriptSegmentItem[] {
  const tracks = Array.from(video?.textTracks ?? []).filter(track => track.kind === 'captions' || track.kind === 'subtitles');
  const track = tracks.find(track => track.mode === 'showing' && track.cues?.length)
    ?? tracks.find(track => track.cues?.length);
  return Array.from(track?.cues ?? []).flatMap(cue => 'text' in cue && typeof cue.text === 'string'
    ? [{ start_time: cue.startTime, end_time: cue.endTime, text: cue.text }]
    : []);
}

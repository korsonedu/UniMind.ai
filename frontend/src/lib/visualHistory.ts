import type { VisualData } from '@/pages/xiaoyu/visuals';
import type { AgentStep } from '@/types/toolRun';

interface VisualMetadataMessage {
  id?: number;
  metadata?: Record<string, unknown> & {
    visual?: VisualData;
    all_visuals?: VisualData[];
  };
  toolStep?: AgentStep;
}

const visualKey = (visual: VisualData) => JSON.stringify([visual.type, visual.payload]);

export function extractMetadataVisuals(message: VisualMetadataMessage): VisualData[] {
  const metadata = message.metadata;
  const list = metadata?.all_visuals?.length
    ? metadata.all_visuals
    : (metadata?.visual ? [metadata.visual] : []);
  const seen = new Set<string>();
  return list.filter((visual) => {
    if (!visual || typeof visual !== 'object') return false;
    const key = visualKey(visual);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** 把历史消息 metadata 中的卡片恢复为 toolStep，支持多条卡片并去重。 */
export function restoreVisualSteps<T extends VisualMetadataMessage>(messages: T[]): T[] {
  return messages.map((message) => {
    const visuals = extractMetadataVisuals(message);
    if (!visuals.length) return message;

    const restored = { ...message };
    const title = visuals[0].payload?.title;
    const label = (typeof title === 'string' ? title : undefined) || '可视化';

    if (restored.toolStep) {
      if (restored.toolStep.status === 'succeeded') {
        restored.toolStep = { ...restored.toolStep, visual: visuals[0], visuals };
      }
    } else {
      restored.toolStep = {
        run_id: 'history',
        call_id: `hist-${message.id || 0}`,
        round: 0,
        name: 'render_visual',
        status: 'succeeded',
        label,
        visual: visuals[0],
        visuals,
        args_summary: '',
        result_summary: '',
      };
    }

    if (restored.metadata) {
      restored.metadata = { ...restored.metadata };
      delete restored.metadata.visual;
      delete restored.metadata.all_visuals;
    }
    return restored;
  });
}

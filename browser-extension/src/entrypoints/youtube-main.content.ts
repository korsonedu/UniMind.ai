import { defineContentScript } from 'wxt/utils/define-content-script';
import { installPageMediaCollector, type PageMediaData } from '../collectors/transcriptWindow';
import { createYouTubeCollector } from '../collectors/youtube/collector';

export default defineContentScript({
  matches: ['*://*.youtube.com/*'],
  world: 'MAIN',
  runAt: 'document_start',
  main() {
    const collector = createYouTubeCollector();
    const publish = installPageMediaCollector(collector);
    let lastMetadata = '';
    let lastSegments: PageMediaData['segments'] | undefined;
    const publishIfChanged = () => {
      const data = collector.read();
      const metadata = JSON.stringify([data?.descriptor, data?.dash_audio, data?.transcript_source]);
      if (metadata === lastMetadata && data?.segments === lastSegments) return false;
      lastMetadata = metadata;
      lastSegments = data?.segments;
      publish();
      return true;
    };
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      if (!publishIfChanged()) return;
      void collector.collect().then(publishIfChanged);
    };
    const scheduleRefresh = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(refresh, 100);
    };
    document.addEventListener('yt-navigate-finish', scheduleRefresh);
    window.addEventListener('yt-navigate-finish', scheduleRefresh);
    window.addEventListener('popstate', scheduleRefresh);
    document.addEventListener('loadedmetadata', scheduleRefresh, true);
    const interval = setInterval(refresh, 1000);
    window.addEventListener('pagehide', event => {
      if (event.persisted) return;
      clearInterval(interval);
      if (timer) clearTimeout(timer);
      document.removeEventListener('yt-navigate-finish', scheduleRefresh);
      window.removeEventListener('yt-navigate-finish', scheduleRefresh);
      window.removeEventListener('popstate', scheduleRefresh);
      document.removeEventListener('loadedmetadata', scheduleRefresh, true);
    });
    refresh();
  },
});

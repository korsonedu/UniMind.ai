import { defineContentScript } from 'wxt/utils/define-content-script';
import { startBilibiliCollector } from '../collectors/bilibili/main';

export default defineContentScript({
  matches: ['*://*.bilibili.com/*'],
  world: 'MAIN',
  runAt: 'document_start',
  main() { startBilibiliCollector(); },
});

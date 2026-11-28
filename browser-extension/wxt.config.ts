import { defineConfig } from 'wxt';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  srcDir: 'src',
  manifestVersion: 3,
  modules: ['@wxt-dev/module-react'],
  imports: false,
  vite: () => ({ plugins: [tailwindcss()] }),
  hooks: {
    'vite:build:extendConfig': (entrypoints, config) => {
      if (!entrypoints.some(entrypoint => entrypoint.type === 'sidepanel')) return;
      const output = config.build?.rollupOptions?.output;
      if (output && !Array.isArray(output)) {
        output.codeSplitting = { groups: [{ name: 'katex', test: /node_modules[\\/]katex[\\/]/ }] };
      }
    },
  },
  manifest: {
    name: 'UniMind 随堂学',
    description: '在视频旁提问、做随堂练习，并把小宇的回答存为笔记。',
    minimum_chrome_version: '116',
    permissions: ['sidePanel', 'storage', 'cookies', 'activeTab', 'tabs', 'scripting', 'declarativeNetRequest', 'tabCapture', 'offscreen'],
    host_permissions: [
      'https://unimind-ai.com/*',
      'https://*.unimind-ai.com/*',
      'http://localhost/*',
      'http://127.0.0.1/*',
      // Existing cross-origin video screenshot fallback (captureVisibleTab), including from the in-player entry.
      '<all_urls>',
    ],
    declarative_net_request: {
      rule_resources: [{ id: 'media_headers', enabled: false, path: 'rules/dnr-media.json' }],
    },
    optional_host_permissions: ['http://*/*', 'https://*/*'],
    action: { default_title: '打开 UniMind 随堂学' },
    icons: { 16: 'icon/16.png', 32: 'icon/32.png', 48: 'icon/48.png', 128: 'icon/128.png' },
  },
});

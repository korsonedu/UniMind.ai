import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.korsonedu.unimind',
  appName: 'UniMind',
  webDir: 'dist',
  plugins: {
    SystemBars: { insetsHandling: 'css', initialViewportFitValueHint: 'cover', style: 'LIGHT' },
  },
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
};

export default config;

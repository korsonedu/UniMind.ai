import { app } from 'electron';
import { autoUpdater } from 'electron-updater';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

type UpdateState = { status: 'unconfigured' | 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error'; version?: string; error?: string };
export class DesktopUpdater {
  state: UpdateState = { status: 'unconfigured', error: '尚未配置正式更新源与发行签名' };
  private configured = false;
  constructor(preview: boolean, private changed: () => void) {
    if (preview || !app.isPackaged || !['darwin', 'win32'].includes(process.platform)) {
      this.state.error = preview ? '预览客户端不接收正式更新' : '自动更新仅用于已签名的 macOS / Windows 正式安装包'; return;
    }
    try {
      // This file is bundled by the distributor. Renderer input and environment
      // variables cannot select a different update server or claim signing.
      const config = JSON.parse(readFileSync(path.join(app.getAppPath(), 'desktop-update.json'), 'utf8'));
      const url = new URL(config.url);
      if (url.protocol !== 'https:' || url.username || url.password || config.signedRelease !== true || !Array.isArray(config.publisherNames) || !config.publisherNames.length) return;
      const trustedFeed = { provider: 'generic' as const, url: url.href, publisherName: config.publisherNames };
      const configPath = path.join(app.getPath('userData'), 'trusted-update.yml');
      // Windows Authenticode verification reads publisher names from configOnDisk.
      writeFileSync(configPath, JSON.stringify(trustedFeed), { mode: 0o600 });
      autoUpdater.updateConfigPath = configPath;
      autoUpdater.setFeedURL(trustedFeed);
      autoUpdater.autoDownload = true; autoUpdater.autoInstallOnAppQuit = false;
      autoUpdater.allowPrerelease = false; autoUpdater.allowDowngrade = false;
      this.configured = true; this.state = { status: 'idle' };
      for (const [event, status] of [['checking-for-update', 'checking'], ['update-available', 'available'], ['update-not-available', 'idle'], ['download-progress', 'downloading'], ['update-downloaded', 'downloaded']] as const) {
        autoUpdater.on(event, (info: { version?: string }) => { this.state = { status, ...(info.version ? { version: info.version } : this.state.version ? { version: this.state.version } : {}) }; this.changed(); });
      }
      autoUpdater.on('error', error => { this.state = { status: 'error', error: error.message }; this.changed(); });
    } catch { /* Missing signed distributor configuration remains unconfigured. */ }
  }
  async check() {
    if (!this.configured) { this.changed(); return; }
    if (['checking', 'available', 'downloading'].includes(this.state.status)) return;
    try { await autoUpdater.checkForUpdates(); } catch (error) { this.state = { status: 'error', error: String(error instanceof Error ? error.message : error) }; this.changed(); }
  }
  install(beforeQuit: () => void) {
    if (!this.configured || this.state.status !== 'downloaded') throw new Error('尚无已验证并下载完成的更新');
    beforeQuit();
    autoUpdater.quitAndInstall();
  }
}

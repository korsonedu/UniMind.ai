const { readFileSync } = require('node:fs');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const failures = [];
const env = process.env;
try {
  const config = JSON.parse(readFileSync(path.join(root, 'desktop-update.json'), 'utf8'));
  const url = new URL(config.url);
  if (url.protocol !== 'https:' || url.username || url.password || config.signedRelease !== true
      || !Array.isArray(config.publisherNames) || !config.publisherNames.length
      || config.publisherNames.some(name => typeof name !== 'string' || !name.trim())) throw new Error();
} catch { failures.push('缺少有效 desktop-update.json：需要受信 HTTPS 发布源、signedRelease 和证书发行者。'); }

if (env.UNIMIND_DESKTOP_PREVIEW === '1' || env.UNIMIND_DESKTOP_URL) failures.push('正式发行不得设置预览模式或自定义入口地址。');
if (env.CSC_IDENTITY_AUTO_DISCOVERY === 'false') failures.push('正式发行不得禁用代码签名身份发现。');
if (process.platform === 'darwin') {
  let identity = false;
  try { identity = /Developer ID Application:/.test(execFileSync('security', ['find-identity', '-v', '-p', 'codesigning'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })); }
  catch { /* An inaccessible keychain cannot establish signing readiness. */ }
  if (!identity && !env.CSC_LINK) failures.push('未找到 Developer ID Application 签名身份，也未配置 CSC_LINK。');
  const notarization = (env.APPLE_ID && env.APPLE_APP_SPECIFIC_PASSWORD && env.APPLE_TEAM_ID)
    || (env.APPLE_API_KEY && env.APPLE_API_KEY_ID && env.APPLE_API_ISSUER) || env.APPLE_KEYCHAIN_PROFILE;
  if (!notarization) failures.push('缺少 Apple 公证配置；请在本机或发行环境中配置，不要提交密钥。');
} else if (process.platform === 'win32') {
  if (!env.CSC_LINK && !env.WIN_CSC_LINK) failures.push('未配置 Windows 发行签名证书。');
} else failures.push('当前正式更新链路仅支持 macOS 和 Windows。');

if (failures.length) {
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else console.log('发行配置检查通过；仍须验收实际签名、公证、安装和升级产物。');

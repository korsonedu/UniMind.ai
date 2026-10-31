const { writeFileSync } = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const urlValue = (process.env.UNIMIND_UPDATE_URL || '').trim();
const publisherNames = (process.env.UNIMIND_UPDATE_PUBLISHERS || '')
  .split(',')
  .map(value => value.trim())
  .filter(Boolean);

function fail(message) {
  console.error(`- ${message}`);
  process.exit(1);
}

if (!urlValue) fail('缺少 UNIMIND_UPDATE_URL，必须是 HTTPS 更新目录。');
if (!publisherNames.length) fail('缺少 UNIMIND_UPDATE_PUBLISHERS，填写代码签名证书发行者，逗号分隔。');

let url;
try {
  url = new URL(urlValue);
} catch {
  fail('UNIMIND_UPDATE_URL 不是合法 URL。');
}
if (url.protocol !== 'https:' || url.username || url.password) {
  fail('UNIMIND_UPDATE_URL 必须是 HTTPS，且不能包含用户名或密码。');
}
if (!url.pathname.endsWith('/')) url.pathname = `${url.pathname}/`;

const config = {
  url: url.href,
  signedRelease: true,
  publisherNames,
};
writeFileSync(path.join(root, 'desktop-update.json'), `${JSON.stringify(config, null, 2)}\n`, { mode: 0o644 });
console.log(`已写入 desktop-update.json：${url.href}`);
console.log('下一步：npm run release:dist（macOS）或 npm run release:dist:win（Windows）。');

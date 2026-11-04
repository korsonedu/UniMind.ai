const { readFileSync, writeFileSync } = require('node:fs');
const path = require('node:path');

const frontend = path.resolve(__dirname, '../..');
const { version } = JSON.parse(readFileSync(path.join(frontend, 'package.json'), 'utf8'));

for (const relative of ['package-lock.json', 'electron/package.json', 'electron/package-lock.json']) {
  const file = path.join(frontend, relative);
  const source = readFileSync(file, 'utf8');
  const data = JSON.parse(source);
  if (data.version === version && (!data.packages || data.packages[''].version === version)) continue;
  data.version = version;
  if (data.packages) data.packages[''].version = version;
  writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
}

console.log(`产品与客户端构建版本：${version}`);

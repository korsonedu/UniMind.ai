const { readFileSync, realpathSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const failures = [];
const expectedVersion = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8')).version;
function inspect(command, args, label, env = process.env) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 30000, env });
  if (result.error || result.status !== 0) { failures.push(label); return ''; }
  return `${result.stdout || ''}${result.stderr || ''}`.trim();
}

try {
  if (process.argv.length !== 3) throw new Error('请提供正式 .app 或 .exe 的路径。');
  const artifact = realpathSync(process.argv[2]);
  let publishers = [];
  try {
    const value = JSON.parse(readFileSync(path.join(root, 'desktop-update.json'), 'utf8')).publisherNames;
    if (!Array.isArray(value) || !value.length || value.some(name => typeof name !== 'string' || !name.trim())) throw new Error();
    publishers = value;
  } catch { failures.push('缺少有效的发行者白名单 publisherNames，必须为非空字符串数组。'); }
  if (process.platform === 'darwin' && artifact.endsWith('.app')) {
    const plist = path.join(artifact, 'Contents', 'Info.plist');
    const bundleId = inspect('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleIdentifier', plist], '无法读取 App 标识');
    const version = inspect('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', plist], '无法读取 App 版本');
    if (bundleId !== 'com.korsonedu.unimind.desktop') failures.push('App 标识不是正式 UniMind 客户端，预览包不能用于正式发行。');
    if (version !== expectedVersion) failures.push('App 版本与当前发行版本不一致。');
    const signature = inspect('codesign', ['-d', '--verbose=2', artifact], '无法读取代码签名');
    const authority = signature.match(/^Authority=(Developer ID Application: .+)$/m)?.[1];
    if (!authority) failures.push('App 缺少 Developer ID Application 发行签名。');
    const company = authority?.replace(/^Developer ID Application: /, '').replace(/ \([A-Z0-9]{10}\)$/, '');
    if (authority && !publishers.includes(authority) && !publishers.includes(company)) failures.push('App 签名发行者不匹配。');
    inspect('codesign', ['--verify', '--deep', '--strict', artifact], '代码签名完整性校验失败');
    if (authority) {
      inspect('spctl', ['--assess', '--type', 'execute', artifact], 'Gatekeeper 验收失败');
      inspect('xcrun', ['stapler', 'validate', artifact], '缺少可验证的已装订公证票据');
    } else failures.push('未验收 Gatekeeper 和公证：须先生成发行签名包。');
  } else if (process.platform === 'win32' && artifact.toLowerCase().endsWith('.exe')) {
    const script = [
      "$ErrorActionPreference='Stop'",
      '[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)',
      '$s=Get-AuthenticodeSignature -LiteralPath $env:UNIMIND_RELEASE_ARTIFACT',
      '$f=Get-Item -LiteralPath $env:UNIMIND_RELEASE_ARTIFACT',
      "$publisher=''",
      'if($s.SignerCertificate){$publisher=$s.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false)}',
      '@{status=[string]$s.Status; publisher=$publisher; version=$f.VersionInfo.ProductVersion} | ConvertTo-Json -Compress',
    ].join('; ');
    const output = inspect('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], '无法验证 Windows 安装包签名', { ...process.env, UNIMIND_RELEASE_ARTIFACT: artifact });
    if (!output) failures.push('Windows 签名检查未返回可验证的信息。');
    else {
      const actual = JSON.parse(output);
      if (actual.status !== 'Valid' || !publishers.includes(actual.publisher)) failures.push('Windows 签名无效或发行者不匹配。');
      if (![expectedVersion, `${expectedVersion}.0`].includes(actual.version)) failures.push('安装包版本与当前发行版本不一致。');
    }
  } else failures.push('请在 macOS 检查 .app，或在 Windows 检查 .exe。');
} catch (error) {
  failures.push(error.code === 'ENOENT' ? '发行产物或必要发行配置不存在。' : error instanceof SyntaxError ? '无法解析发行信息。' : error.message);
}

if (failures.length) {
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else console.log(`发行产物 ${expectedVersion} 的系统签名检查通过；仍须完成安装、升级和恢复验收。`);

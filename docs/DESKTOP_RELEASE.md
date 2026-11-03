# 桌面发行与自动更新

## 每次发布的固定流程

以下流程适用于每次桌面发版。桌面版本独立于网站版本，标签使用 `desktop-vX.Y.Z`。本次为 `0.1.5`。

1. **锁定范围。** 从已知提交建立独立发布分支，只带入本次桌面壳改动，不携带其他工作区的未提交修改。记录本次与上次版本的区别。网站／后端有配套变更时单独发布并验收；只有主进程、图标和打包配置变化时不需要重启业务服务。
2. **统一版本。** 同时更新 `frontend/electron/package.json`、`package-lock.json` 顶层及根 package 的版本，以及根目录 `CHANGELOG.md` 的 Desktop 更新说明。已经分发的版本不得复用。
3. **最小验证。** 执行 `npm run build`，包含主进程／preload 编译、类型检查和现有 3 项安全冒烟；针对本次改动补一次必要检查。不要为了发版重复跑整站测试。保留仓库已有 CI 门槛。
4. **提交并制作。** 先提交本次源码，以这个确切 SHA 构建。在新的版本目录输出 macOS ARM64 DMG／ZIP 和 Windows x64 NSIS，保留原版本产物。默认入口必须是 `https://unimind-ai.com/login`，应用标识为 `com.korsonedu.unimind.desktop`；包内不得带预览账号、开发地址或本机服务依赖。
5. **核对产物。** 检查包内 `package.json`、主进程／preload 与提交源码的对应关系、平台版本信息和图标资源。记录 `BUILD-INFO.json`（源码 SHA、版本、平台、构建时间、签名状态、入口、资源 SHA256）及 `SHA256SUMS`。Mac 做一次安装包启动／托盘冒烟；Windows 若未实机安装，明确标记未验收，不把交叉打包算作运行验收。
6. **合并并分发。** 推送发布分支，按仓库规则通过 PR 合并。源码提交进入 main 后，把 `desktop-vX.Y.Z` 标签指向实际构建的源码 SHA，在 GitHub Release 上传安装包、构建信息和校验和，重新核对远端资产的大小及 SHA256。受控分发包标为 prerelease。完成后记录发布链接、下载校验与剩余限制。

官网 landing 页通过 `/api/desktop-release/` 读取版本号最高的已发布 `desktop-vX.Y.Z` Release（包含 prerelease，排除 draft），缓存 5 分钟。安装包可作为 GitHub 资产上传，或在 Release 正文中列出官网 `https://unimind-ai.com/static/desktop/<version>/` 下载链接。当前识别 `UniMind-<version>-arm64[-unsigned].dmg` 与 `UniMind-<version>-x64[-unsigned]-setup.exe`。先上传并核实包及同目录 `INSTALL.txt`，最后发布 Release；页面不会退回旧版本安装包。

发布后修改源码必须重新构建；若产物已对外分发，使用下一个版本号。保留上一版安装包；手动安装的回退使用上一版包，自动更新回退按下文规则生成更高版本号。

## 当前采用的受控分发

没有发行证书／公证材料时，使用独立的候选配置，不修改或绕过下文正式签名发行门槛：

```bash
cd frontend/electron
npm ci
npm run candidate:mac  # macOS ARM64：DMG、ZIP，ad-hoc 签名
npm run candidate:win  # Windows x64：未签名 NSIS
```

产物位于 `release/desktop-X.Y.Z/`。`unsigned` 文件名表示没有可信发行者签名；Mac 的 ad-hoc 只校验本地产物完整性，不等于 Developer ID 或公证。候选配置不上传文件，不生成自动更新 feed。实际分发通过流程第 6 步完成。

两平台应分别在对应系统构建。复用本机已有的同版本官方 Electron 运行时或交叉构建时，仅通过临时本机构建配置指定 `electronDist`／`electronVersion`，不得把本机绝对路径写入通用配置。记录所用版本及运行时哈希。

## 两类更新

- Web 和业务更新：部署前端/后端即可，桌面客户端重开或刷新就拿到新界面，不需要新安装包。
- 桌面壳更新：修改了 Electron 主进程、preload、协议、离线或版本号，才需要新安装包。

本文只覆盖桌面壳发行。

## 前置条件

自动更新必须先有可信签名，否则不得启用：

- macOS：Apple Developer Program、Developer ID Application 证书、公证凭据。
- Windows：Authenticode 代码签名证书。
- 一个 HTTPS 更新目录，用于存放安装包和 `latest-mac.yml` / `latest.yml`。
- `UNIMIND_UPDATE_URL`：HTTPS 更新目录，必须与安装包内 `desktop-update.json` 一致。
- `UNIMIND_UPDATE_PUBLISHERS`：代码签名证书发行者，逗号分隔，必须与签名匹配。

本地不接受未签名、预览源或自签名源作为正式更新。

## 发行步骤

1. 修改 `frontend/electron/package.json` 的 `version`，同步更新 CHANGELOG。
2. 配置签名和公证环境变量，不提交任何密钥。
3. 生成更新配置：

   ```bash
   cd frontend/electron
   UNIMIND_UPDATE_URL=https://updates.example.com/unimind/ \
   UNIMIND_UPDATE_PUBLISHERS='Korson Technology (TEAMID)' \
   npm run release:prepare
   ```

   该命令写入 `desktop-update.json`，该文件已在 `.gitignore` 中，不提交。

4. 构建签名产物：

   ```bash
   npm run release:dist       # macOS: dmg + zip + latest-mac.yml
   npm run release:dist:win   # Windows: nsis + latest.yml
   ```

   `release:check` 会在构建前校验 `desktop-update.json`、签名身份和公证配置。缺失会直接失败。

5. 验证产物：

   ```bash
   npm run release:verify -- release/UniMind.app
   npm run release:verify -- release/UniMind-<version>-x64-setup.exe
   ```

6. 把以下文件上传到 `UNIMIND_UPDATE_URL` 对应目录：

   - macOS：`UniMind-<version>-arm64.dmg`、`UniMind-<version>-arm64-mac.zip`、`latest-mac.yml`
   - Windows：`UniMind-<version>-x64-setup.exe`、`latest.yml`

7. 从上一版客户端验证：

   - 启动后 8 秒自动检查，或在“设置 → 桌面应用 → 版本与更新”点“检查更新”。
   - 下载完成后点“重启并更新”。
   - 验证安装、登录、离线课程和回滚。

## 环境变量

macOS 签名和公证：

```bash
CSC_LINK=/path/to/developer-id.p12
CSC_KEY_PASSWORD=...
APPLE_ID=...
APPLE_APP_SPECIFIC_PASSWORD=...
APPLE_TEAM_ID=...
```

Windows 签名：

```bash
WIN_CSC_LINK=/path/to/code-signing.pfx
WIN_CSC_KEY_PASSWORD=...
```

只在本机或 CI secret 中设置，不写入仓库。

## 回滚

不要通过把 feed 版本号改低来回滚，客户端默认 `allowDowngrade=false`。正确方式是用旧代码构建一个更高的版本号，重新签名、上传并发布。旧安装包和旧 feed 文件保留。

## 当前状态

- 本地机器没有 Developer ID 签名身份，也没有公证或 Windows 签名凭据。
- `desktop-update.json` 未生成，更新状态保持 `unconfigured`。
- 客户端已有检查、下载、重启安装入口；新增了启动后 8 秒自动检查。
- 在拿到证书和 HTTPS feed 之前，桌面壳更新仍只能手动替换安装包。

# 桌面发行与自动更新

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

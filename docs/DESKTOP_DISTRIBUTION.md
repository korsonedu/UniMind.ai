# UniMind 桌面版小范围分发

当前版本0.1.1，使用正式产品名UniMind、应用标识`com.korsonedu.unimind.desktop`，默认访问`https://unimind-ai.com`。不使用合成账号，不依赖本地5175服务，不自动登录预览学生。

## 制作

在`frontend/electron`执行`npm ci`和`npm run build`，然后使用正式`electron-builder.yml`打包。产物输出到已忽略的`release/`，不要提交安装包到Git。

macOS Apple Silicon可在本机运行：

```sh
CSC_IDENTITY_AUTO_DISCOVERY=false npx electron-builder --config electron-builder.yml --mac dmg zip --arm64
```

没有Developer ID时，这是受控分发候选，不能作为已签名公证的公共发行版。本轮本地Mac产物用临时配置指定现有Electron45运行时和ad-hoc签名，保持正式应用标识与线上入口；该签名只提供本地产物完整性，不代表Apple发行者认证。

Windows可在Windows环境运行：

```powershell
$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
npm run dist:win
```

现有Windows GitHub Actions在开发分支推送后构建同一正式入口的未签名NSIS候选。本轮Mac交叉构建仅在临时配置中选择官方Windows x64运行时并关闭Windows签名，不把宿主机运行时路径写入通用配置。

## 分发条件

- 分发前核对各平台BUILD-INFO与SHA256SUMS，记录对应源码提交。Mac提供DMG及ZIP，Windows提供每用户NSIS安装包。
- 目前尚无Apple Developer ID／公证与Windows发行证书，接收者可能遇到操作系统的未知发行者或信任提示。本轮不修改系统安全设置或伪造签名状态。
- 暂无正式更新源，0.1.1采用手动替换／安装新版；不提供虚构的更新feed，不宣称已实现自动回滚。`release:dist`和`release:verify`仍保留正式签名发行门槛。
- 此客户端加载线上前端。只有将匹配的前端及后端发布到站点后，本轮离线下载／同步、会话恢复及DSH改动才对真实用户生效。代码推送不等于服务发布。
- 2026-10-30只读检查时，线上`/api/courses/offline-access/`与`/api/ai/chat-requests/<uuid>/`返回404。本轮请求已授权提交推送和本机打包，生产部署须另行确认。
- 活动任务跨睡眠的进一步验收按用户决定留待后续；Windows安装运行仍需其测试机验收。上述事项不冒充已通过。

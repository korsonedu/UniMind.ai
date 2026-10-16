# UniMind 管理扩展

本扩展把官网 Directus 作为管理入口，学习数据、业务规则和审计继续留在 Django。UniMind 学习前端不增加管理入口。

首期支持课程与模块维护、批量归类、视频及附件上传、学员查询、学习服务配置、发放与撤销，以及操作记录。第二期增加题库与知识目录维护。订单、AI 配置和通知尚未迁移，原生 Django Admin 暂作运维兜底。

## 构建

使用 Node.js 22。已在隔离 Directus 12.4.1 中加载验证。

```sh
cd admin-extension
npm ci
npm run check
npm run build
```

发布包只需要 `package.json` 与 `dist/`，挂载到 Directus 的 `/directus/extensions/directus-extension-unimind-admin/`。不要上传 `node_modules/`、`.preview/` 或本地环境文件。

## 身份接入

需要两组既有账号的标识，不能用邮箱自动匹配或自动提权。两位 Directus 用户均须拥有管理员权限；对应的两个 Django 用户均须启用 `is_active`、`is_staff`、`is_superuser`，且 `institution=NULL`。二者权限相同，审计分开。

Directus 服务端环境：

```dotenv
UNIMIND_BACKEND_URL=https://your-unimind-host
UNIMIND_ADMIN_BRIDGE_SECRET=<same-random-secret-at-least-32-characters>
UNIMIND_DIRECTUS_ADMIN_IDS=<directus-uuid-one>,<directus-uuid-two>
```

Django 服务端环境：

```dotenv
UNIMIND_ADMIN_BRIDGE_SECRET=<same-random-secret-at-least-32-characters>
UNIMIND_DIRECTUS_ADMIN_MAP={"<directus-uuid-one>":123,"<directus-uuid-two>":456}
UNIMIND_CONTENT_INSTITUTION_ID=<existing-content-institution-id>
```

`123`、`456` 只是格式示例，须替换为核对过的账号 ID。内容归属应使用现有课程所属的内部机构 ID；只有内容确实属于 `institution=NULL` 时才填 `global`。未配置归属时课程、模块、题库、知识目录和上传控制均只读，其他管理流程不受影响。

签名绑定操作者、HTTP 方法、路径、时间戳、nonce 和原始 JSON 摘要，60 秒内有效。生产环境必须使用所有 Django worker 共享的 Redis 缓存，禁止用本地内存缓存代替防重放存储。缓存故障会拒绝请求。桥接密钥不进入管理页面构建。Directus 只接受固定操作名，不允许浏览器指定外部 URL。

接入步骤：备份相关数据库与原配置；先发布 Django 并执行 `manage.py migrate`；核对两端身份映射和密钥；挂载扩展并重启 Directus；在 Directus 项目设置的模块栏中启用 `UniMind`，保留原有模块。独立入口为 `/admin/unimind-admin`，同源接口为 `/unimind-admin-api/operations/<operation>`。

## 业务边界

- 课程目录采用“学科 → 模块 → 视频”。学科是模块的独立分类字段，不依赖知识点；同一学科内模块名称唯一，不同学科可以使用同名模块。
- 新课程须选择模块，上传表单不再显示专辑、知识点。历史关联及知识点的其他用途保留，未做删除。已有模块仅在历史课程能明确确定同一学科时自动回填，其余留待教师归类。
- 模块只做分类，公开标记保留为历史字段，不作为访问条件；管理界面不再提供公开标记开关。课程、模块仍保留既有内部内容归属边界，不按服务包关联模块筛选学生。
- 服务价格以元输入、整数分保存。发放沿用既有快照与顺延规则，同一请求 UUID 重试只产生一条权益；撤销保留记录。
- 课程有学习记录时禁止直接删除；非空模块和仍被服务引用的模块须先处理引用。
- 写操作及成功审计共同提交，审计只记操作者、操作类型、对象与请求编号，不记完整表单、密码或对话内容。

## 用户功能权限

入口为“学员 → 查看服务 → 配置权限”。可逐人配置小宇、学习记录、课程中心、习题训练、课程答疑和自习室。沿用已有 `UserAccessProfile.blocked_permissions`，不改变角色、管理身份、会员等级或已有服务记录，未知的历史权限项会保留。

现有默认开放行为保持不变，不因这次迁移批量关停功能。后台显式关闭的功能，学生侧保留灰色入口但不能进入；直接访问页面显示联系管理员，不提示购买服务包。后端接口按同一权限档案拒绝访问，课程媒体和自习室 WebSocket 也执行校验。教师、学生与管理员的学习前端均使用相同规则，管理桥接权限独立。

模块、学科与课程访问授权分离，服务发放仍负责 AI 额度和有效期，不隐式改动上述功能开关。权限变更在后续接口请求中生效，前端切换页面或重新聚焦窗口会刷新权限；已签发的 OSS 下载地址仍受原签名有效期限制，不能承诺立即撤回已经发出的链接。

## 题库与知识目录

题库支持内容搜索、目录及其下级筛选、题型与难度筛选、分页、新增编辑、批量归类和受保护删除。管理详情包含标准答案与解析，仅通过已认证的管理桥接返回，不修改学生列表接口。客观题使用 2 至 4 个选项及单个答案字母；主观题保留参考答案、得分点和既有结构化评分标准。普通编辑不自动调用 AI。

知识目录与课程模块分开维护。目录提供科目、篇章、小节、考点层级、编码、说明、排序和移动。上级须高于下级，不允许循环或跨内容归属；所属学科从上级继承，顶层学科调整同步下级并在事务提交后失效对应缓存。保留已有目录与关联，不自动创建教师的知识清单。

有下级节点、课程、题目、学习记录或非目录派生知识关联的目录不能直接删除；派生的树结构关联随无引用叶子删除。已有业务或学习记录的题目不能删除或直接改变题型，答案、解析与难度仍可更正。本期不增加题库批量导入或 AI 出题流水线，也不重做知识地图。

## 文件

视频、封面、课件和资料统一走 OSS 分片直传。文件内容不经过 Directus 或 Django 请求体；管理桥接只接受 256 KB 以下的 JSON 控制请求。这也覆盖小文件，避免额外维护一套 Base64 上传接口。

沿用 Django 的扩展名、大小与文件头校验：视频至多 500 MB，封面 10 MB，文档 50 MB。视频限 MP4、M4V、WebM、MOV，实际浏览器解码仍取决于文件编码。上传票据绑定当前操作者、课程、字段和归属，2 小时有效，分片 URL 1 小时有效。OSS 需要允许管理域名的 CORS `PUT` 请求。没有 OSS 配置时禁用文件入口，元数据编辑正常。

合并完成后以 OSS 返回的真实分片与对象信息验证大小，配额和元数据通过后才关联课程。失败会中止分片并清理本次成品；旧文件在数据库与审计提交后清理。替换视频会清掉旧转录、大纲并停用旧自动题目，提交后衔接既有转录与大纲处理。正在转录或生成大纲时拒绝替换。

存储网络失败时自动清理只能尽力完成，错误写入 Django 日志。建议为 OSS 未完成分片设置生命周期清理；浏览器关闭后未提交的任务无法依赖页面清理。

## 隔离预览

`compose.preview.yml` 仅供本机使用，固定监听 `127.0.0.1:8057`。Django 使用 `admin-extension/.preview/django.sqlite3` 和独立端口 `8002`。**现有 8055 是 SSH 隧道，不得用于本扩展开发。**

```sh
mkdir -p .preview/database
chmod 777 .preview/database
docker compose -f compose.preview.yml up -d
```

Compose 内的密码与密钥都是公开的本地预览值，不得用于生产。首次启动会建立 `unimind-preview-one@example.com`；第二个预览管理员须在同一隔离实例建立并赋予相同管理员角色。把两人的 UUID 以 `UNIMIND_DIRECTUS_ADMIN_IDS` 传给 Compose，并在隔离 Django 配置相同映射。

隔离 Django 初始化：

```sh
cd ../backend
export ACCOUNT_ENABLED=0 ACCOUNT_RSA_KEY_PATH= ACCOUNT_DEV_LOCAL_CACHE=1
export DB_NAME="$(pwd)/../admin-extension/.preview/django.sqlite3"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py shell -c 'from backoffice.preview import seed; seed()'
```

然后设置预览密钥、两位管理员映射、`UNIMIND_CONTENT_INSTITUTION_ID=global`、包含 `host.docker.internal` 的 `ALLOWED_HOSTS`，用 `runserver 0.0.0.0:8002` 启动。Docker 通过 `host.docker.internal` 访问该端口；不要把它映射到公网。夹具脚本仅允许该固定预览数据库，创建显式命名的虚构数据，不接触真实学员。

定向检查覆盖身份、归属、发放幂等、逐用户课程与媒体授权、独立学科及无专辑/知识点上传。第二期仅运行新增的两组管理检查，覆盖答案、跨归属批量归类、历史记录保护、循环引用和缓存失效，并检查扩展类型与构建。未连接生产 OSS 做实际上传。

## 生产接入（2026-10-16）

正式入口为 `https://www.korsonedu.com/admin/unimind-admin`。复用既有 Directus 管理员 `gaoyuchi`、`chenxingyu`，两人权限相同，操作分别审计。Django 同名账号仅用于桥接身份与审计，禁用密码登录；不修改 Directus 密码，也不自动匹配或提升其他现有账号。原有运维账号保留。

扩展已挂载到现有官网扩展目录，原模块和 Compose 维护配置保留。内容管理归属沿用科晟智慧的既有机构 ID。桥接密钥与身份映射只保存在服务器环境文件，不进入源码或前端构建。

官网 Nginx 的 Directus API 代理名单须包含 `unimind-admin-api`。生产现行配置已加入这一项；后续从官网 `deploy/nginx.conf` 模板重新安装 Nginx 配置前，须同步保留，避免接口回落到官网静态路由。普通前端发布无需重装 Nginx 配置。

启用前已备份 PostgreSQL、Directus SQLite 和环境配置。已核对两人的生产签名身份、内容归属、扩展加载与匿名请求拒绝；没有代两人输入密码完成真实登录，也没有修改学生数据或执行生产 OSS 上传。订单、AI 配置与通知仍不在本扩展范围。

## 回退

停用模块、移除扩展挂载及 Directus 端桥接变量，重启 Directus。Django 保留现有管理兜底；停用新入口不会删除课程、权益或审计。新增迁移仅添加可空的唯一请求 UUID，无需回滚业务数据。

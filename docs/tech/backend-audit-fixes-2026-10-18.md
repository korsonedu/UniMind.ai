# 后端审计修复记录，2026-10-18

两轮审计的 B01–B19、P01–P06 已落实到本地代码。保持既有 Django、DRF、Channels、Celery 结构，保留工作区已有的对话置顶和课程管理等并行改动。没有提交、推送或部署。

## 逐项修复

| 编号 | 代码处理 | 主要位置 |
| --- | --- | --- |
| B01 | 交卷前批量校验题目 ID、重复项及内容范围；后台读取和写入前复核权限与范围。 | `backend/quizzes/views_exam.py`、`ai_workflow.py` |
| B02 | 按用户加锁，持久化优化器权重、动量、EMA、更新次数和学习率，移除旧权重缓存。 | `backend/quizzes/memorix/service.py`、`quizzes/models.py` |
| B03 | 不在交卷时提前覆盖上次复习时间；成功批改后以旧状态计算间隔。 | `backend/quizzes/ai_workflow.py` |
| B04 | 在正常复习共同路径写入 ReviewLog，与状态更新保持同一事务；试卷完成标记和练习唯一结果阻止重复应用。 | `backend/quizzes/memorix/service.py`、`ai_workflow.py` |
| B05 | 预批改缓存键加入答案摘要，旧任务不会覆盖另一个答案的结果。 | `backend/ai_assistant/services/practice.py`、`tasks.py`、`views_api.py` |
| B06 | 拒绝重复题目；先完成批改，再锁用户并一次性写入学习记录和 PracticeSubmission；相同提交重放结果，不同答案返回冲突。 | `backend/ai_assistant/views_api.py`、`quizzes/models.py` |
| B07 | 用 method_decorator 正确适配清空对话方法的限流装饰器。 | `backend/ai_assistant/views.py` |
| B08 | 暂停时累计已学时长并持久化剩余秒数，恢复后只累计新片段；结束、到期、重连统一计算，绑定数据库会话 ID。 | `backend/study_room/session_manager.py`、`consumers.py` |
| B09 | 主观题判分失败或分数非法时返回可重试错误，不写学习状态、不删除练习会话；试卷批改失败同样不提交部分学习结果。 | `backend/ai_assistant/views_api.py`、`quizzes/services/ai_task_service.py`、`ai_workflow.py` |
| B10 | 旧课程、模块、标签及关联校验统一使用受管内容范围，支持全局标签。 | `backend/courses/views.py`、`modules.py`、`views_tags.py`、`serializers.py` |
| B11 | 签名或返回文件前，按课程、答疑附件、启动资料的真实记录校验功能权限和范围；受保护未知文件拒绝访问；校验本地路径。答疑附件、自习图片使用鉴权媒体入口。 | `backend/school_system/media_serve.py`、`faq_system/serializers.py`、`study_room/views.py` |
| B12 | 原生 Redis 连接改为读取 Django RedisCache 的 URL，替换不兼容的 django_redis 调用。尚无运行时消费者的经验参数保持 pending，不再虚报 applied。 | `backend/core/redis.py`、`quizzes/memorix/field.py`、`services/memorix_scheduler.py`、`ai_assistant/services/experience_applicator.py` |
| B13 | 问题归属、回答所属问题等字段只读，编辑不能重新挂接到其他范围。 | `backend/faq_system/serializers.py`、`views.py` |
| B14 | 任一 ASR 分段接口异常向上抛出并触发任务重试；静音空文本与请求失败区分，临时文件统一清理。 | `backend/courses/asr/glm_provider.py` |
| B15 | 先校验全部分段、大纲字段与时间戳，再短事务替换内容；用状态和更新时间限定任务所有权，过期执行不能覆盖新结果。 | `backend/courses/services/ai_course_service.py` |
| B16 | 按任务硬超时加缓冲判定失联运行任务；列表、重试、聊天及任务入口回收状态，解除永久 running。 | `backend/backoffice/tasks.py`、`teaching.py` |
| B17 | 已支付重复回调补派缺失发票任务；入队失败记录日志；每十分钟补偿已付款但无发票记录的订单。 | `backend/payments/services/base.py`、`tasks.py`、`school_system/settings.py` |
| B18 | 两个旧登录接口先锁用户行，再删除并创建 Token，串行化同一用户的轮换。 | `backend/users/views.py` |
| B19 | 新记录成功提交后才删除旧文件；失败只清理本次新上传且无引用的对象；封面提取保存前复核视频，避免旧对象覆盖新视频。 | `backend/courses/models.py`、`views.py`、`tasks.py` |
| P01 | 课程列表批量加载模块、专辑、标签、计数与当前用户进度；列表不展开关联课程全集，分页上限 100。 | `backend/courses/access.py`、`serializers.py`、`views.py` |
| P02 | WebSocket 的完整 Redis 操作放入线程适配，设置连接和读取超时，避免阻塞事件循环。 | `backend/study_room/consumers.py`、`session_manager.py` |
| P03 | 交卷直接入队，移除逐次 Celery inspect/ping。 | `backend/quizzes/services/task_dispatcher.py` |
| P04 | OSS 上传直接传文件对象，下载按 1 MB 读取到可落盘临时文件，避免整份视频读入内存。 | `backend/core/oss_storage.py` |
| P05 | 一次 ffmpeg segment 调用完成分段，消除逐段创建进程及整除时的空尾段。 | `backend/courses/asr/glm_provider.py` |
| P06 | 答疑列表默认每页 20 条、最多 100 条，只展开首答摘要；批量查询作者身份；前端支持分页及加载更多，后台刷新保留已加载页。 | `backend/faq_system/views.py`、`serializers.py`、`users/serializers.py`、`frontend/src/pages/QASystem.tsx` |

## 数据库迁移

以下两个迁移尚未执行，发布时需要先应用；当前记录不代表服务已升级。

- `backend/quizzes/migrations/0054_learning_submission_state.py`：优化器状态、试卷完成时间、练习幂等结果。仅为已有正 max_score 的试卷回填完成时间，避免把未完成的部分结果当作已完成。
- `backend/courses/migrations/0028_global_course_tags.py`：标签允许全局归属，并为全局 slug 增加唯一约束。

## 静态核对

- 46 个变更或新增 Python 文件通过 AST 语法解析。
- `QASystem.tsx` 通过 TypeScript 的 TSX 语法解析；没有执行类型检查或构建。
- `git diff --check` 通过；两个新增迁移的前置文件均存在，并人工核对新增模型字段。
- 已交叉检查学习事务、重复任务、课程替换与并发封面保存、媒体入口及分页响应兼容。
- 按用户要求，没有新增或运行测试，没有请求业务接口，没有执行数据库迁移或读写生产数据。上述静态检查不代表运行时验证，也没有测量性能收益。

## 保留的边界

- 经验参数 `memorix:alpha`、`knowledge_tree:topK` 当前没有运行时消费者；修复会保留待应用状态，未为它们新增算法行为。
- 发票补偿沿用现有创建记录的实现，仍不生成真实 PDF。
- 自习会话完全离线超过 Redis TTL，且期间没有 tick、重连或统计调用时，仍需后台回收机制才能恢复丢失的 Redis 计时状态。
- 文件存储无法参与数据库回滚：更外层事务在模型成功保存后回滚时，可能遗留新上传对象；旧文件会保留。未引入对象存储事务或清理框架。
- 课程任务使用现有状态和更新时间控制并发；已完成后才开始执行的延迟重复任务仍可能重新生成，没有新增持久化任务 ID 协议。

# 科晟智慧存量机构迁入 Workspace

个人空间不再开放默认课程目录；已经接入 Workspace 的机构课程需使用选中的机构学习身份及明确课程授权。机构完成接入后，个人公共内容查询不再回退到该机构；后台已有内容配置保留用于既有运营工具。

`migrate_institution_workspace` 默认只输出计划，`--apply` 才会在一次数据库事务内接入现有机构、成员及历史学习记录：

```bash
python manage.py migrate_institution_workspace --institution 1 --owner yuchigao --members yuchigao 科晟智慧cxy X431
python manage.py migrate_institution_workspace --institution 1 --owner yuchigao --members yuchigao 科晟智慧cxy X431 --apply
```

课程、讲稿、大纲、笔记、聊天和学习记录保留原编号；学习所有权改到同一登录账号在机构内的学习身份，关联记录不复制。登录凭证、企业资格及账号 AI 额度保留在原账号。既有 AI 请求计入科晟 Workspace 的历史用量，账号计费归属不变。

机构服务采用原机构配置；原服务没有到期日时以 9999-12-31 表示长期有效，界面显示“长期有效”。学生获得已迁入课程的授权，迁移用邀请码停用，不能被其他账号领取。机构主使用管理员角色。再次执行不覆盖目标机构已存在的学习数据，发生冲突则整笔事务回滚。

生产执行前停写并完成数据库备份；记录每个迁移模型的原记录编号、所属账号及行数，执行后逐项比对。校验三个账号在个人空间无课程访问权、在科晟 Workspace 可读课程与原学习记录，同时确认无机构成员身份的账号不能访问。其他历史账号不自动加入。

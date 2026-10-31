# DSH 可作答练习卡闭环

日期：2026 年 10 月 26 日。目标：让新小宇链路里的抽题卡可以真正作答、提交、批改和查看结果，同时不开放缺少幂等的聊天写工具。

## 边界

- get_practice_questions 返回 practice_quiz 卡片，复用现有 PracticeQuizCard。
- 题目由服务端按内容范围抽取，卡片不含答案；提交走现有 /quizzes/submit-exam/。
- 提交以 submission_id 和答案哈希幂等；成绩、Memorix、PracticeSubmission 仍由原业务事务决定。
- 评分继续走既有后台任务和 DSH 评分开关，不新增聊天内 grade_student_answer 写路径。
- 卡片只由服务端结果生成，Host 白名单增加 practice_quiz；模型正文和任意 render_visual 不参与。

## 实现

- dsh_cards：get_practice_questions 直接返回工具生成的 practice_quiz 视觉结果。
- dsh/cards.py：卡片白名单增加 practice_quiz。
- dsh_service：更新工具描述，明确卡片内作答与提交。
- 前端 DshToolCard 接入 PracticeQuizCard；导出练习卡片 payload 类型。
- 测试：只读冒烟断言 practice_quiz、practice_id 和题目存在；修正练习会话测试的内容范围设置。

## 验证

- 只读练习卡与评分回归 5 passed；练习提交/异步评分 7 passed；卡片冒烟通过；前端生产构建通过。
- 未验收：真实模型评分质量、生产提交量、正式权益与内容范围。

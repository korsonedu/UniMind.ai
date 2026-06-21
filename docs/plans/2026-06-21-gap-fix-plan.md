# 差距修复计划 2026-06-21

**适用范围**: 6/21 审计确认的 6 项真实差距 + 2 项产品方向 gap
**原则**: 每项给出具体文件、最小改动路径、预估行数

---

## 第一轮：止血（2-3 天，4 项）

### F1. 在线考试时限校验（~3 行）

**文件**: `backend/quizzes/views_online_exam.py` → `OnlineExamSubmitView.post()`

在 L206 `attempt = get_object_or_404(...)` 之后插入：

```python
# 检查考试是否超时
if exam.duration_minutes and attempt.started_at:
    elapsed = (timezone.now() - attempt.started_at).total_seconds()
    if elapsed > exam.duration_minutes * 60:
        attempt.status = 'expired'
        attempt.save()
        return Response({'error': '考试时间已到，系统自动提交'}, status=400)
```

**无前端改动需求**（前端倒计时已有，后端补充拦截即可）

---

### F2. ClassCourse 前端绑定（~150 行）

**现状**: `ClassCourseManageView` POST/GET/DELETE 全好，`StudentClassCourseView` 全好

**前端改动**:

**文件 1**: `frontend/src/pages/InstitutionStudents.tsx`（或 `ClassSection` 组件）
- 在班级行添加"课程"按钮
- 点击弹出 Dialog：左侧显示机构所有课程列表（搜索+勾选），右侧显示已分配课程（可拖拽排序或删除）
- 提交调用 `POST /api/users/institution/me/class-courses/`（`{class_id, course_id, order}`）
- 删除调用 `DELETE /api/users/institution/me/class-courses/{id}/`

**API 调用示例**:
```typescript
// 查询已分配
const res = await api.get('/users/institution/me/class-courses/', { params: { class_id } })

// 分配
await api.post('/users/institution/me/class-courses/', { class_id, course_id, order: 0 })

// 删除
await api.delete(`/users/institution/me/class-courses/${ccId}/`)
```

**文件 2**: `frontend/src/pages/CourseCenter.tsx`
- 学生端已有本班课程过滤参数 `class_id`，确认可用即可

---

### F3. 成绩册排序 + 导出（~80 行后端 + ~60 行前端）

**后端**: `backend/users/views_institution.py` → `ClassGradebookView.get()`

1. 加 query params: `sort_by=name|average`, `sort_dir=asc|desc`, `search=学生名`
2. 加 `format=csv` 时返回 CSV 文件

```python
# L1772 附近，students 查询后
sort_by = request.query_params.get('sort_by', 'name')
sort_dir = request.query_params.get('sort_dir', 'asc')
search = request.query_params.get('search', '')

if search:
    students = students.filter(Q(nickname__icontains=search) | Q(username__icontains=search))

if sort_by == 'average':
    # 计算每个学生的均分后排序
    student_avgs = []
    for student in students:
        subs = AssignmentSubmission.objects.filter(student=student, assignment__in=assignments)
        scores = [s.score for s in subs if s.score is not None]
        avg = sum(scores)/len(scores) if scores else 0
        student_avgs.append((student, avg))
    student_avgs.sort(key=lambda x: x[1], reverse=(sort_dir == 'desc'))
    students_ordered = [s for s, _ in student_avgs]
else:
    students_ordered = sorted(students, key=lambda s: s.nickname or s.username, reverse=(sort_dir == 'desc'))

# CSV 导出
if request.query_params.get('format') == 'csv':
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="gradebook_{class_obj.name}.csv"'
    writer = csv.writer(response)
    header = ['学生'] + [a.title for a in assignments] + ['均分']
    writer.writerow(header)
    for row in student_list:
        writer.writerow([row['name']] + [s['score'] for s in row['scores']] + [...])
    return response
```

**前端**: `frontend/src/pages/Gradebook.tsx`
- 表头加排序按钮（姓名↑↓、均分↑↓）
- 顶部加搜索框
- 加"导出 CSV"按钮，`window.open('/api/users/institution/me/gradebook/?class_id=X&format=csv')`

---

### F4. 机构自助数据导出（~30 行）

**文件**: `backend/users/views_institution.py`

新增 endpoint `GET /api/users/institution/me/export/?type=students|grades`

```python
class InstitutionDataExportView(APIView):
    """机构自助数据导出。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        export_type = request.query_params.get('type', 'students')

        if export_type == 'students':
            students = inst.students.all()
            # CSV: 姓名, 邮箱, ELO, 加入日期, 班级
            ...
        elif export_type == 'grades':
            # 委托给 ClassGradebookView 的 CSV 逻辑
            ...
        return response
```

**前端**: `InstitutionStudents.tsx` 或 `Gradebook.tsx` 加"导出"按钮

---

## 第二轮：体验升级（3-5 天，2 项）

### F5. 学生端学习数据 Dashboard（~200 行前端）

**方案**: 增强 `StudentHome.tsx`，不要额外页面。

**新增数据区域**（在今日任务上方插入统计卡片行）:

| 卡片 | 数据来源 |
|------|---------|
| 🔥 连续打卡 X 天 | `GET /api/users/me/checkin/` → `current_streak` |
| 📊 本周刷题 X 题 | `GET /api/users/me/report-card/` → `stats.total_attempted` |
| ✅ 正确率 X% | 同上 → `stats.accuracy` |
| 🧠 掌握知识点 X 个 | 同上 → `stats.mastered_count` |
| 🏆 成就 X/Y | `GET /api/users/achievements/` → unlocked count |

**实现**: 用已有的 `/api/users/me/report-card/` 接口一次性拉数据，渲染 4-5 个 stat 卡片 + 最近解锁的成就 badge。

**改动文件**: 仅 `frontend/src/pages/StudentHome.tsx`（+ ~80 行）

---

### F6. PWA 全链路激活（~50 行配置 + ~30 行前端）

**1. manifest.json** → `frontend/public/manifest.json`
```json
{
  "name": "UniMind",
  "short_name": "UniMind",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#000000",
  "icons": [
    { "src": "/pwa-192x192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/pwa-512x512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

**2. index.html** → `frontend/index.html`
```html
<link rel="manifest" href="/manifest.json" />
```

**3. SW 注册** → `frontend/src/main.tsx` 或 `App.tsx`
```typescript
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
  })
}
```

**4. Push 订阅** → 已有 API `POST/DELETE /api/users/me/push-subscribe/`，在 `StudentHome.tsx` 或 `XiaoYu.tsx` 添加推送权限请求按钮。

---

## 不放在本轮的计划（后续阶段）

| 项 | 原因 |
|----|------|
| Agent 工具箱注册新后端能力（成绩单/课程列表/考试结果） | 需要等产品决策：对话式 vs 菜单式之间到底怎么走 |
| 工作台"一句话组卷发布"端到端 | 同上，Agent 能力 vs 手动操作的分界线需要讨论 |
| 多渠道主动推送（邮件/微信） | 先等 PWA push 通了再扩展 |
| 教学计划↔Memorix 打通 | 算法层面的事，不适合紧急迭代 |
| 邀请批量/CSV 导入 | F4 的导出做完了再考虑导入 |
| 考试切屏检测/防作弊 | 先修时限这个最大的坑，安全加固后续 |

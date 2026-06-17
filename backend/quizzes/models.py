from django.db import models
from django.conf import settings

class KnowledgePoint(models.Model):
    LEVEL_CHOICES = (
        ('sub', '模块(SUB)'),
        ('ch', '篇章(CH)'),
        ('sec', '小节(SEC)'),
        ('kp', '考点(KP)'),
    )
    code = models.CharField(max_length=50, blank=True, null=True, verbose_name="唯一编码(如MB-1001)")
    name = models.CharField(max_length=100, verbose_name="知识点名称")
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='kp', verbose_name="层级")
    prefix_category = models.CharField(max_length=20, blank=True, null=True, verbose_name="学科前缀", help_text="如 MB, IF, CF 等")
    description = models.TextField(blank=True, verbose_name="知识点描述")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name="上级知识点")
    institution = models.ForeignKey('users.Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='knowledge_points', verbose_name="所属机构")
    subject = models.CharField(max_length=100, blank=True, null=True, verbose_name="学科名称", help_text="如 金融431、法学、CPA 等")
    order = models.PositiveIntegerField(default=0, verbose_name="排序", help_text="同级节点中的显示顺序，数字越小越靠前")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def save(self, *args, **kwargs):
        # 自动提取前缀，例如从 "MB-1001" 提取 "MB"
        if self.level == 'kp' and self.code:
            parts = self.code.split('-')
            if len(parts) > 1:
                self.prefix_category = parts[0].strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.code}] {self.name}" if self.code else self.name

class Question(models.Model):
    QUESTION_TYPES = (
        ('objective', '客观题'),
        ('subjective', '主观题'),
    )
    SUBJECTIVE_TYPES = (
        ('noun', '名词解释'),
        ('short', '简答题'),
        ('essay', '论述题'),
        ('calculate', '计算题'),
    )
    DIFFICULTY_LEVELS = (
        ('entry', '入门 (Entry)'),
        ('easy', '简单 (Easy)'),
        ('normal', '适当 (Normal)'),
        ('hard', '困难 (Hard)'),
        ('extreme', '极限 (Extreme)'),
    )
    DIFFICULTY_MAP = {
        'entry': 800,
        'easy': 1000,
        'normal': 1200,
        'hard': 1400,
        'extreme': 1600,
    }
    
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    text = models.TextField(verbose_name="题目内容")
    q_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='objective', db_index=True)
    subjective_type = models.CharField(max_length=20, choices=SUBJECTIVE_TYPES, blank=True, null=True, verbose_name="主观题类型")
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='normal', verbose_name="难度等级", db_index=True)
    grading_points = models.TextField(blank=True, null=True, help_text="得分点说明（主观题必填）")
    options = models.JSONField(blank=True, null=True, help_text="客观题选项")
    correct_answer = models.TextField(blank=True, null=True, help_text="客观题标准答案或主观题参考答案")
    ai_answer = models.TextField(blank=True, null=True, verbose_name="AI 生成的深度解析答案")
    rubric = models.JSONField(blank=True, null=True, help_text="主观题采分点 JSON 结构")
    difficulty = models.IntegerField(default=1200, help_text="基准 ELO 分值")
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="questions", verbose_name="所属机构")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 自动同步标签到分值 (如果难度分值为默认或未手动指定，则根据级别映射)
        if self.difficulty_level and (self._state.adding or self.difficulty == 1200):
            self.difficulty = self.DIFFICULTY_MAP.get(self.difficulty_level, 1200)
        # 标准化 options 为 list 格式（兼容 dict 格式的历史数据）
        if isinstance(self.options, dict):
            self.options = [self.options[k] for k in sorted(self.options.keys())]
        super().save(*args, **kwargs)

    def get_max_score(self):
        if self.q_type == 'objective': return 10
        if self.subjective_type == 'noun': return 5
        if self.subjective_type == 'short': return 10
        if self.subjective_type == 'essay': return 20
        return 10

    def __str__(self):
        return f"[{self.get_q_type_display()}] {self.text[:30]}"

class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    score = models.FloatField()
    elo_change = models.IntegerField(default=0)
    is_initial_placement = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class UserQuestionStatus(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    is_favorite = models.BooleanField(default=False, verbose_name="是否收藏")
    is_mastered = models.BooleanField(default=False, verbose_name="是否已掌握(排除)")
    wrong_count = models.IntegerField(default=0, verbose_name="错误次数")
    
    # Memorix Fields
    stability = models.FloatField(default=0.0, help_text="记忆稳定性 (S)，单位：天")
    difficulty = models.FloatField(default=0.0, help_text="记忆难度 (D)，范围 1-10")
    reps = models.IntegerField(default=0, help_text="总复习次数")
    lapses = models.IntegerField(default=0, help_text="忘记次数")
    last_review = models.DateTimeField(null=True, blank=True, help_text="上次复习时间")
    
    next_review_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_correct = models.BooleanField(default=False)

    error_type = models.CharField(max_length=32, blank=True, default='')
    error_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('user', 'question')

class QuizExam(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exams')
    total_score = models.FloatField(default=0)
    max_score = models.FloatField(default=0)
    elo_change = models.IntegerField(default=0)
    summary = models.TextField(blank=True, help_text="AI 对整张试卷的综合点评")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class ExamQuestionResult(models.Model):
    exam = models.ForeignKey(QuizExam, on_delete=models.CASCADE, related_name='results')
    details = models.JSONField(blank=True, null=True, help_text="主观题采分明细")
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True)
    user_answer = models.TextField()
    score = models.FloatField()
    max_score = models.FloatField()
    feedback = models.TextField(blank=True)
    analysis = models.TextField(blank=True, help_text="思维链分析")
    is_correct = models.BooleanField(default=False)


# ── 0013 ContentPipelineTask ──
class ContentPipelineTask(models.Model):
    TASK_TYPES = [
        ("ai_parse", "AI 整理解析"), ("ai_generate", "AI 智能命题"),
        ("bulk_import", "批量题库导入"), ("course_publish", "课程发布流水线"),
        ("article_publish", "文章发布流水线"), ("other", "其他任务"),
    ]
    STATUS_CHOICES = [
        ("draft", "草稿"), ("pending", "待执行"), ("running", "执行中"),
        ("review", "待审核"), ("completed", "已完成"),
        ("failed", "失败"), ("cancelled", "已取消"),
    ]
    task_type = models.CharField(max_length=30, choices=TASK_TYPES, default="other", verbose_name="任务类型")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="任务状态", db_index=True)
    title = models.CharField(max_length=200, verbose_name="任务标题")
    description = models.TextField(blank=True, verbose_name="任务说明")
    progress = models.PositiveSmallIntegerField(default=0, verbose_name="进度百分比")
    payload = models.JSONField(blank=True, default=dict, verbose_name="输入载荷")
    result = models.JSONField(blank=True, default=dict, verbose_name="输出结果")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    request_id = models.CharField(max_length=80, blank=True, verbose_name="请求链路 ID")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_pipeline_tasks", verbose_name="处理人")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pipeline_tasks", verbose_name="创建人", db_index=True)
    institution = models.ForeignKey('users.Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='pipeline_tasks', verbose_name="所属机构")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["-created_at"]


# ── 0016 PromptTemplateVersion ──
class PromptTemplateVersion(models.Model):
    namespace = models.CharField(max_length=50, default="quizzes", verbose_name="模板命名空间")
    template_name = models.CharField(max_length=120, verbose_name="模板文件名")
    version = models.PositiveIntegerField(default=1, verbose_name="版本号")
    content = models.TextField(verbose_name="模板内容")
    change_note = models.CharField(max_length=200, blank=True, verbose_name="变更说明")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="prompt_template_versions", verbose_name="操作人")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = ("namespace", "template_name", "version")


# ── 0017 KnowledgePointAnnotation ──
class KnowledgePointAnnotation(models.Model):
    MASTERY_CHOICES = [
        ("unknown", "未知"), ("weak", "薄弱"), ("learning", "学习中"),
        ("stable", "已稳定"), ("mastered", "已掌握"),
    ]
    PRIORITY_CHOICES = [("low", "低"), ("medium", "中"), ("high", "高")]
    SOURCE_CHOICES = [("auto", "系统计算"), ("manual", "用户标注")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_annotations")
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.CASCADE, related_name="user_annotations")
    mastery_level = models.CharField(max_length=20, choices=MASTERY_CHOICES, default="unknown", verbose_name="掌握等级")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium", verbose_name="复习优先级")
    confidence_score = models.PositiveSmallIntegerField(default=0, verbose_name="信心分(0-100)")
    tags = models.JSONField(blank=True, default=list, verbose_name="个性标签")
    note = models.TextField(blank=True, verbose_name="个性备注")
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="manual", verbose_name="数据来源")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "knowledge_point")


# ── 0018 MemorixProfile / ReviewLog / UserKnowledgeState ──
class MemorixProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memorix_profile")
    weights = models.JSONField(default=list)
    last_optimized_at = models.DateTimeField(null=True, blank=True)
    total_reviews_used = models.IntegerField(default=0)
    current_loss = models.FloatField(null=True, blank=True)


class ReviewLog(models.Model):
    GRADE_CHOICES = [(1, "Again"), (2, "Hard"), (3, "Good"), (4, "Easy")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_logs")
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.CASCADE)
    grade = models.IntegerField(choices=GRADE_CHOICES)
    review_time = models.DateTimeField(auto_now_add=True)
    elapsed_days = models.FloatField(help_text="距离上次复习过去的天数")
    predicted_retrievability = models.FloatField()


class UserKnowledgeState(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_states")
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.CASCADE)
    mastery_score = models.FloatField(default=0.0, help_text="综合掌握度评分")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "knowledge_point")


# ── 0020 MemorixOptimizationLog / PersonalizedMockExam ──
class MemorixOptimizationLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memorix_optimization_logs")
    previous_loss = models.FloatField(null=True, blank=True)
    new_loss = models.FloatField(null=True, blank=True)
    improvement_ratio = models.FloatField(default=0.0, help_text="(old - new) / old")
    reviews_used = models.IntegerField(default=0)
    accepted = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PersonalizedMockExam(models.Model):
    STATUS_CHOICES = [
        ("processing", "生成中"), ("ready", "可下载"), ("failed", "生成失败"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personalized_mock_exams")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ready")
    exam_pdf = models.CharField(max_length=500, blank=True, help_text="试卷版绝对路径")
    answer_pdf = models.CharField(max_length=500, blank=True, help_text="解析版绝对路径")
    question_count = models.IntegerField(default=0)
    weak_coverage = models.IntegerField(default=0, help_text="命中的薄弱点题目数")
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# ── 0021 TeacherExam / StudentExamSubmission ──
class TeacherExam(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    exam_pdf = models.FileField(upload_to="teacher_exams/", blank=True, null=True, help_text="PDF 模式试卷文件，online 模式可空")
    # ── 在线考试字段 ──
    EXAM_TYPES = (
        ('pdf', 'PDF试卷'),
        ('online', '在线考试'),
    )
    exam_type = models.CharField(max_length=10, choices=EXAM_TYPES, default='pdf', verbose_name='考试类型')
    duration_minutes = models.PositiveIntegerField(null=True, blank=True, verbose_name='考试时长(分钟)')
    start_time = models.DateTimeField(null=True, blank=True, verbose_name='开考时间')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='截止时间')
    shuffle_questions = models.BooleanField(default=True, verbose_name='题目乱序')
    shuffle_options = models.BooleanField(default=True, verbose_name='选项乱序')
    max_attempts = models.PositiveIntegerField(default=1, verbose_name='最大尝试次数')
    passing_score = models.FloatField(null=True, blank=True, verbose_name='及格分数')
    # ── 原有字段 ──
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="teacher_exams")
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="teacher_exams", verbose_name="所属机构")


class StudentExamSubmission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exam = models.ForeignKey(TeacherExam, on_delete=models.CASCADE, related_name="submissions")
    answer_pdf = models.FileField(upload_to="student_answers/")
    score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_pdf = models.FileField(upload_to="graded_answers/", blank=True, help_text="教师批改后带笔迹的PDF")
    created_at = models.DateTimeField(auto_now_add=True)


class Assignment(models.Model):
    """作业：教师选题后定向布置给班级。"""
    STATUS_CHOICES = (
        ('draft', '草稿'),
        ('published', '已发布'),
        ('closed', '已关闭'),
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    institution = models.ForeignKey("users.Institution", on_delete=models.CASCADE, related_name="assignments")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_assignments")
    target_classes = models.ManyToManyField("users.Class", related_name="assignments")
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class AssignmentQuestion(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="assignment_questions")
    question = models.ForeignKey("Question", on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    points = models.IntegerField(default=1)

    class Meta:
        ordering = ['order']
        unique_together = [('assignment', 'question')]


class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignment_submissions")
    submitted_at = models.DateTimeField(auto_now_add=True)
    answers = models.JSONField(default=dict)
    score = models.FloatField(null=True, blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="graded_submissions")
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']
        unique_together = [('assignment', 'student')]


class ExamQuestion(models.Model):
    """在线考试的题目关联（带排序和分值）"""
    exam = models.ForeignKey('TeacherExam', on_delete=models.CASCADE, related_name='exam_questions')
    question = models.ForeignKey('Question', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    points = models.FloatField(default=1.0, verbose_name='本题分值')

    class Meta:
        ordering = ['order']
        unique_together = [('exam', 'question')]


class OnlineExamAttempt(models.Model):
    """学生在线考试作答记录"""
    STATUS_CHOICES = (
        ('in_progress', '作答中'),
        ('submitted', '已提交'),
        ('graded', '已批改'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='online_exam_attempts')
    exam = models.ForeignKey('TeacherExam', on_delete=models.CASCADE, related_name='attempts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, help_text='{question_id: user_answer}')
    question_order = models.JSONField(default=list, help_text='该学生看到的题目顺序 [question_id, ...]')
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(null=True, blank=True)
    # 逐题结果（判分后填充）
    question_results = models.JSONField(default=list, blank=True, help_text='[{question_id, score, max_score, is_correct, feedback}]')

    class Meta:
        ordering = ['-started_at']
        unique_together = [('user', 'exam')]


class ExamTemplate(models.Model):
    """出题模板：保存常用出题配置，支持系统预设和机构自定义。"""
    DIFFICULTY_LEVELS = (
        ('entry', '入门'),
        ('easy', '简单'),
        ('normal', '适当'),
        ('hard', '困难'),
        ('extreme', '极限'),
        ('mixed', '混合'),
    )
    name = models.CharField(max_length=100, verbose_name="模板名称")
    description = models.TextField(blank=True, verbose_name="模板说明")
    subject = models.CharField(max_length=100, blank=True, verbose_name="适用学科")
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='normal')
    question_types = models.JSONField(default=list, help_text='["objective","subjective"]')
    type_ratio = models.JSONField(default=dict, help_text='{"objective": 0.7, "short": 0.2, "essay": 0.1}')
    question_count = models.IntegerField(default=10)
    knowledge_point_ids = models.JSONField(default=list, blank=True, help_text="预选知识点ID列表")
    is_system = models.BooleanField(default=False, verbose_name="系统预设")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    institution = models.ForeignKey('users.Institution', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_system', '-updated_at']

    def __str__(self):
        prefix = '[系统]' if self.is_system else ''
        return f"{prefix}{self.name}"


# ── 0038 GradingRecord ──
class GradingRecord(models.Model):
    """记录每次评分的完整历史，用于追溯和分析。"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True)
    score = models.FloatField()
    max_score = models.FloatField()
    is_correct = models.BooleanField()
    error_type = models.CharField(max_length=32, blank=True, default='')
    error_metadata = models.JSONField(default=dict, blank=True)
    feedback = models.TextField(blank=True)
    analysis = models.TextField(blank=True)
    graded_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ── Phase 6: IRT ItemParameter ──
class ItemParameter(models.Model):
    """IRT 项目参数模型 - 存储每道题的三参数 Logistic 模型参数。机构隔离：同一道题在不同机构有不同参数。"""
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        help_text="关联的题目"
    )
    institution = models.ForeignKey(
        'users.Institution',
        on_delete=models.CASCADE,
        help_text="所属机构（机构级隔离）"
    )
    discrimination = models.FloatField(
        default=1.0,
        help_text="IRT a参数，区分度"
    )
    difficulty = models.FloatField(
        default=0.0,
        help_text="IRT b参数，难度"
    )
    guessing = models.FloatField(
        default=0.25,
        help_text="IRT c参数，猜测概率"
    )
    responses_count = models.IntegerField(
        default=0,
        help_text="用于估计的答题次数"
    )
    last_estimated_at = models.DateTimeField(null=True)

    class Meta:
        unique_together = [('question', 'institution')]

    def __str__(self):
        return f"ItemParam(q={self.question_id}, inst={self.institution_id}, a={self.discrimination:.2f}, b={self.difficulty:.2f})"


# ── Phase 6: UserAbility ──
class UserAbility(models.Model):
    """IRT 学生能力模型 - 学生对每个知识点的能力 θ 估计。机构隔离。"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    institution = models.ForeignKey(
        'users.Institution',
        on_delete=models.CASCADE,
        help_text="所属机构（机构级隔离）"
    )
    knowledge_point = models.ForeignKey(
        KnowledgePoint,
        on_delete=models.CASCADE
    )
    theta = models.FloatField(
        default=0.0,
        help_text="IRT θ参数，学生能力"
    )
    responses_count = models.IntegerField(
        default=0
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'knowledge_point', 'institution')]

    def __str__(self):
        return f"Ability(u={self.user_id}, kp={self.knowledge_point_id}, θ={self.theta:.3f})"


# ── Phase 6: QMatrixEntry ──
class QMatrixEntry(models.Model):
    """Q-matrix 条目 - 题目与知识点的关联矩阵，标记该题是否需要掌握此知识点才能答对。"""
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE
    )
    knowledge_point = models.ForeignKey(
        KnowledgePoint,
        on_delete=models.CASCADE
    )
    required = models.BooleanField(
        default=True,
        help_text="该题是否需要掌握此知识点才能答对"
    )

    class Meta:
        unique_together = ('question', 'knowledge_point')


# ── Memorix Phase 1: KnowledgeEdge ──
class KnowledgeEdge(models.Model):
    """
    知识图的有向边。source → target 表示"复习 source 会通过扩散
    影响 target 的记忆状态"。边是有向的——扩散方向不一定可逆。
    """
    EDGE_TYPES = [
        ('contains',     '包含'),
        ('prerequisite', '前驱'),
        ('similar',      '相似'),
        ('contrast',     '对立'),
        ('confusion',    '混淆'),
        ('co_occur',     '共现'),
        ('derivation',   '推导'),
    ]
    SOURCE_TYPES = [
        ('tree',   '从 KnowledgePoint 树派生'),
        ('llm',    'LLM 批量生成'),
        ('manual', '手工标注'),
        ('data',   'ReviewLog 数据驱动'),
    ]

    source = models.ForeignKey(
        KnowledgePoint, on_delete=models.CASCADE,
        related_name='out_edges',
    )
    target = models.ForeignKey(
        KnowledgePoint, on_delete=models.CASCADE,
        related_name='in_edges',
    )
    edge_type = models.CharField(max_length=16, choices=EDGE_TYPES)
    weight = models.FloatField(default=1.0, help_text='扩散权重 [0, 1]')
    source_type = models.CharField(max_length=16, choices=SOURCE_TYPES, default='tree')
    is_active = models.BooleanField(default=True, help_text='权重<0.05自动标记为False')
    institution = models.ForeignKey(
        'users.Institution', on_delete=models.CASCADE,
        null=True, blank=True,
        help_text='机构专属边（NULL=全局）',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('source', 'target', 'edge_type', 'institution')
        indexes = [
            models.Index(fields=['source', 'is_active']),
            models.Index(fields=['target', 'is_active']),
            models.Index(fields=['institution', 'is_active']),
            models.Index(fields=['source_type']),
        ]
        verbose_name = '知识图边'
        verbose_name_plural = '知识图边'

    def __str__(self):
        return f"{self.source} → {self.target} ({self.edge_type}, w={self.weight})"

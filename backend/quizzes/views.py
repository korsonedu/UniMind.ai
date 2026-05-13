import os
import json
import datetime
import csv
import io
import logging
from django.utils import timezone
from rest_framework import generics, permissions
from users.permissions import IsAdmin
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Question, QuizAttempt, UserQuestionStatus, KnowledgePoint, QuizExam
from .serializers import (
    QuestionSerializer, QuizAttemptSerializer, UserQuestionStatusSerializer, 
    KnowledgePointSerializer, QuizExamSerializer
)
from users.models import User
from users.serializers import UserSerializer
from users.views import IsMember
import random
from ai_service import AIService
from ai_engine.service import AICallError
from notifications.models import Notification
from .ai_workflow import (
    grade_single_question_submission,
    mark_questions_reviewed,
    save_confirmed_questions,
)
from .services.ai_parse_service import (
    build_parse_task_id,
    extract_raw_text,
    get_parse_task,
    init_parse_task,
)
from .services.task_dispatcher import dispatch_ai_parse_task, dispatch_exam_grading

logger = logging.getLogger(__name__)

class QuestionListView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [IsMember()]

    def get_queryset(self):
        user = self.request.user
        qs = Question.objects.all().order_by('-created_at')
        
        # Shared filters
        q = self.request.query_params.get('search')
        kp_id = self.request.query_params.get('kp')
        q_type = self.request.query_params.get('type')
        
        if q: qs = qs.filter(text__icontains=q)
        if kp_id: qs = qs.filter(knowledge_point_id=kp_id)
        if q_type: qs = qs.filter(q_type=q_type)

        if user.is_staff and not self.request.query_params.get('limit'):
            return qs

        if kp_id:
            return qs

        now = timezone.now()
        # 硬性冷却：30分钟内复习过的题不再抽选，给大脑留出间隔时间
        cooldown_time = now - datetime.timedelta(minutes=30)
        limit = self.request.query_params.get('limit', 10)
        try: limit = int(limit)
        except: limit = 10

        # 获取所有符合条件的候选 ID，排除已掌握的题目
        mastered_ids = UserQuestionStatus.objects.filter(user=user, is_mastered=True).values_list('question_id', flat=True)
        
        review_ids = list(UserQuestionStatus.objects.filter(
            user=user, 
            next_review_at__lte=now,
            is_mastered=False
        ).exclude(
            last_review__gt=cooldown_time # 过滤掉最近 30 分钟内刚做过的题
        ).values_list('question_id', flat=True))
        
        attempted_ids = UserQuestionStatus.objects.filter(user=user).values_list('question_id', flat=True)
        
        # 1. 已到期需要复习的题目
        due_ids = review_ids[:limit]
        
        # 2. 如果复习的题不够本次抽题数量，用没做过的新题补足
        needed = limit - len(due_ids)
        new_ids = []
        if needed > 0:
            new_ids = list(Question.objects.exclude(
                id__in=attempted_ids
            ).exclude(
                id__in=mastered_ids
            ).values_list('id', flat=True)[:needed])
            
        final_ids = due_ids + new_ids
        
        random.shuffle(final_ids)
        return Question.objects.filter(id__in=final_ids)

    def perform_create(self, serializer):
        question = serializer.save()
        if not question.ai_answer:
            self.generate_ai_answer(question)

    def generate_ai_answer(self, question):
        ai_answer = AIService.generate_ai_answer(question)
        if ai_answer:
            question.ai_answer = ai_answer
            question.save(update_fields=['ai_answer'])

class GradeSubjectiveView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        question_id = request.data.get('question_id')
        user_answer = request.data.get('answer')
        
        if not user_answer:
            return Response({'error': '请提供答题内容'}, status=400)

        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': '题目不存在'}, status=404)

        max_score = question.get_max_score()
        
        try:
            result = grade_single_question_submission(request.user, question, user_answer)
            return Response({
                'score': result['score'],
                'max_score': max_score,
                'feedback': result['feedback'],
                'analysis': result['analysis'],
                'ai_answer': question.ai_answer,
                'elo_change': result['elo_change']
            })
        except Exception as e:
            return Response({'error': f'评分逻辑错误: {str(e)}'}, status=500)

class ToggleFavoriteView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        q_id = request.data.get('question_id')
        status_obj, _ = UserQuestionStatus.objects.get_or_create(user=request.user, question_id=q_id)
        status_obj.is_favorite = not status_obj.is_favorite
        status_obj.save()
        return Response({'is_favorite': status_obj.is_favorite})

class ToggleMasteredView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        q_id = request.data.get('question_id')
        status_obj, _ = UserQuestionStatus.objects.get_or_create(user=request.user, question_id=q_id)
        status_obj.is_mastered = not status_obj.is_mastered
        status_obj.save()
        return Response({'is_mastered': status_obj.is_mastered})

class WrongQuestionListView(generics.ListAPIView):
    serializer_class = UserQuestionStatusSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        return UserQuestionStatus.objects.filter(user=self.request.user, wrong_count__gt=0).order_by('-wrong_count')

class FavoriteQuestionListView(generics.ListAPIView):
    serializer_class = UserQuestionStatusSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        return UserQuestionStatus.objects.filter(user=self.request.user, is_favorite=True)

class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsAdmin]

class QuizAttemptCreateView(generics.CreateAPIView):
    serializer_class = QuizAttemptSerializer
    permission_classes = [IsMember]

    def perform_create(self, serializer):
        user = self.request.user
        is_initial = not user.has_completed_initial_assessment
        avg_difficulty = 1000
        expected_score = 1 / (1 + 10**( (avg_difficulty - user.elo_score) / 400 ))
        score = serializer.validated_data.get('score', 0)
        elo_change = int(32 * (score - expected_score))
        if is_initial and score > 0.8: elo_change += 200
        attempt = serializer.save(user=user, is_initial_placement=is_initial, elo_change=elo_change)
        user.elo_score += elo_change
        if is_initial: user.has_completed_initial_assessment = True
        user.save()

class LeaderboardView(generics.ListAPIView):
    queryset = User.objects.filter(is_active=True).order_by('-elo_score')[:50]
    serializer_class = UserSerializer
    permission_classes = [IsMember]

class QuizStatsView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        now = timezone.now()
        
        status_qs = UserQuestionStatus.objects.filter(user=user)
        
        # 今日复习任务 (Due Today)
        review_count = status_qs.filter(next_review_at__lte=now).count()
        
        # FSRS 预警: 稳定性 < 7天 且 下次复习在 3天内 的题目
        # 这代表短期记忆中容易遗忘的部分
        at_risk_count = status_qs.filter(
            stability__lt=7,
            next_review_at__lte=now + datetime.timedelta(days=3),
            next_review_at__gt=now
        ).count()

        attempted_ids = status_qs.values_list('question_id', flat=True)
        new_questions_count = Question.objects.exclude(id__in=attempted_ids).count()
        
        # 自动生成复习提醒
        if review_count > 0:
            today_notif = Notification.objects.filter(recipient=user, ntype='fsrs_reminder', created_at__date=now.date()).exists()
            if not today_notif:
                Notification.objects.create(recipient=user, ntype='fsrs_reminder', title='今日复习任务已就绪', content=f'你有 {review_count} 道题目已进入 FSRS 遗忘临界点。', link='/tests')

        return Response({
            'review_goal': review_count,
            'new_questions': new_questions_count,
            'at_risk_count': at_risk_count
        })

class IsAdminUserOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS: return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

class KnowledgePointListView(generics.ListCreateAPIView):
    # 只返回 parent__isnull=True 的顶层，序列化器会通过 children 把下面所有的全拉出来。
    queryset = KnowledgePoint.objects.filter(parent__isnull=True).order_by('id')
    serializer_class = KnowledgePointSerializer
    permission_classes = [IsAdminUserOrReadOnly]

class KnowledgePointDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = KnowledgePoint.objects.all()
    serializer_class = KnowledgePointSerializer
    permission_classes = [IsAdminUserOrReadOnly]

class SubmitExamView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        questions_data = request.data.get('answers', [])
        if not questions_data:
            return Response({'error': '无答题数据'}, status=400)

        exam = QuizExam.objects.create(user=request.user)

        mark_questions_reviewed(
            user=request.user,
            question_ids=[item.get('question_id') for item in questions_data if item.get('question_id') is not None],
        )

        dispatch_exam_grading(request.user.id, exam.id, questions_data)

        # 统一走后台批改，避免前端刷新/离开导致用户侧状态丢失。
        message = '试卷已提交后台批改，结果将通过通知发送。'
        if len(questions_data) == 1:
            message = '特训已提交后台判分，完成后将通过通知发送。'

        return Response({
            'status': 'processing',
            'exam_id': exam.id,
            'message': message,
        })

class LatestExamReportView(APIView):
    """
    获取最近一次考试报告。
    """
    permission_classes = [IsMember]

    def get(self, request):
        latest_exam = QuizExam.objects.filter(user=request.user).first()
        if not latest_exam:
            return Response({'error': '报告不存在'}, status=404)
            
        serializer = QuizExamSerializer(latest_exam)
        return Response(serializer.data)

class ExamDetailView(generics.RetrieveAPIView):
    """
    获取某次考试的详细报告
    """
    queryset = QuizExam.objects.all()
    serializer_class = QuizExamSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return QuizExam.objects.filter(user=self.request.user)

class GenerateBulkQuestionsView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request, pk):
        try: 
            kp = KnowledgePoint.objects.get(pk=pk)
        except KnowledgePoint.DoesNotExist: 
            return Response({'error': '知识点不存在'}, status=404)
        
        # 使用最新的解耦后的批量生成逻辑
        # 这会自动应用前缀动态 Prompt (MB, IF, CF等规则)
        count = AIService.batch_generate_questions(KnowledgePoint.objects.filter(id=kp.id), count_per_kp=3)
        
        if count == 0:
            return Response({'error': 'AI 生成失败或未生成任何题目'}, status=500)
            
        return Response({'status': 'success', 'count': count})

class AIPreviewGenerateView(APIView):
    """
    智能出题预览：返回生成的数据但不存库
    """
    permission_classes = [IsAdmin]
    def post(self, request):
        kp_ids = request.data.get('kp_ids', [])
        count = int(request.data.get('count', 1))
        target_types = request.data.get('types', []) # 新增题型过滤
        target_difficulty = request.data.get('difficulty_level', 'normal')
        target_type_ratio = request.data.get('type_ratio')
        
        if not kp_ids:
            return Response({'error': '未提供知识点 ID'}, status=400)
        
        try:
            questions = AIService.preview_generate_questions(
                kp_ids,
                count_per_kp=count,
                target_types=target_types,
                target_difficulty=target_difficulty,
                target_type_ratio=target_type_ratio,
            )
        except AICallError as e:
            return Response({'error': e.message}, status=e.status_code)
        except Exception:
            return Response({'error': 'AI 命题服务异常，请稍后重试'}, status=500)

        if not questions:
            return Response({'error': 'AI 生成失败，请重试'}, status=500)
            
        return Response({'questions': questions})

class AIConfirmSaveQuestionsView(APIView):
    """
    确认入库：保存前端编辑后的题目
    """
    permission_classes = [IsAdmin]
    def post(self, request):
        questions_data = request.data.get('questions', [])
        if not isinstance(questions_data, list) or not questions_data:
            return Response({'error': '未提供可入库题目'}, status=400)

        created_count = 0
        failed_items = []

        for idx, q_data in enumerate(questions_data, start=1):
            text = str((q_data or {}).get('question') or (q_data or {}).get('text') or '').strip()
            if not text:
                failed_items.append({'index': idx, 'error': '题干为空'})
                continue

            try:
                created = save_confirmed_questions([q_data])
                if created <= 0:
                    failed_items.append({'index': idx, 'error': '题目格式无效，未写入'})
                else:
                    created_count += created
            except Exception as exc:  # noqa: BLE001
                logger.exception("ai-smart-generate confirm save failed at item=%s", idx)
                error_msg = str(exc).strip() or exc.__class__.__name__
                failed_items.append({'index': idx, 'error': error_msg[:200]})

        if failed_items:
            msg = f"成功 {created_count} 题，失败 {len(failed_items)} 题"
            payload = {
                'status': 'partial_success' if created_count > 0 else 'failed',
                'count': created_count,
                'failed_count': len(failed_items),
                'errors': failed_items[:10],
                'error': msg,
            }
            return Response(payload, status=207 if created_count > 0 else 500)

        return Response({'status': 'success', 'count': created_count})

class GenerateFromTextView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request):
        text = request.data.get('text')
        kp_id = request.data.get('kp_id')
        num_obj = request.data.get('num_objective', 3)
        num_short = request.data.get('num_short', 1)
        num_essay = request.data.get('num_essay', 1)
        num_calc = request.data.get('num_calc', 0)

        generated = AIService.generate_questions_from_text(
            text=text or '',
            num_obj=num_obj,
            num_short=num_short,
            num_essay=num_essay,
            num_calc=num_calc,
            kp_id=kp_id,
        )
        if not generated:
            return Response({'error': 'AI 生成失败'}, status=500)

        created_count = save_confirmed_questions(generated)
        return Response({'status': 'success', 'count': created_count})

class AIPreviewParseView(APIView):
    """
    整理功能：改用高性能异步模式
    """
    permission_classes = [IsAdmin]
    def post(self, request):
        raw_text = extract_raw_text(
            request.data.get('raw_text', ''),
            request.FILES.get('file'),
        )

        if not raw_text.strip(): return Response({'error': '内容为空'}, status=400)

        task_id = build_parse_task_id()
        init_parse_task(task_id)
        dispatch_ai_parse_task(raw_text, task_id)

        return Response({'task_id': task_id, 'status': 'processing'})

    def get(self, request):
        """前端轮询此接口获取结果"""
        task_id = request.query_params.get('task_id')
        result = get_parse_task(task_id)
        if not result: return Response({'error': '任务不存在'}, status=404)
        return Response(result)

class BulkImportQuestionsView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request):
        questions_data = request.data.get('questions', [])
        kp_id = request.data.get('kp_id')
        if kp_id:
            for q in questions_data:
                q['kp_id'] = q.get('kp_id') or kp_id

        created_count = save_confirmed_questions(questions_data)
        return Response({'status': 'success', 'count': created_count})


class AdminQuestionListView(APIView):
    """
    管理员专用分页题目列表接口，支持搜索、知识点筛选和题型筛选。
    用于前端题库管理面板，性能优化版本，面向5000题以上的大规模题库。
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = Question.objects.select_related('knowledge_point').order_by('-created_at')

        # 过滤条件
        search = request.query_params.get('search', '').strip()
        kp_id = request.query_params.get('kp_id')
        q_type = request.query_params.get('q_type')

        if search:
            qs = qs.filter(text__icontains=search)
        if kp_id and kp_id != '0':
            qs = qs.filter(knowledge_point_id=kp_id)
        if q_type and q_type != 'all':
            qs = qs.filter(q_type=q_type)

        # 分页
        total = qs.count()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        offset = (page - 1) * page_size
        questions = qs[offset:offset + page_size]

        data = []
        for q in questions:
            data.append({
                'id': q.id,
                'text': q.text,
                'q_type': q.q_type,
                'subjective_type': q.subjective_type,
                'correct_answer': q.correct_answer or '',
                'grading_points': q.grading_points or '',
                'ai_answer': q.ai_answer or '',
                'difficulty': q.difficulty,
                'difficulty_level': q.difficulty_level,
                'difficulty_level_display': q.get_difficulty_level_display(),
                'options': q.options,
                'knowledge_point': q.knowledge_point.id if q.knowledge_point else None,
                'knowledge_point_name': q.knowledge_point.name if q.knowledge_point else '无',
            })

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'results': data
        })


class ExportStructuredQuestionsView(APIView):
    """
    导出结构化题目数据（AI 可读格式）。
    直接同步至服务器本地 seed_questions.json。
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        kp_id = request.query_params.get('kp_id')
        qs = Question.objects.select_related('knowledge_point').all()
        if kp_id and kp_id != '0':
            qs = qs.filter(knowledge_point_id=kp_id)

        structured = []
        for q in qs:
            structured.append({
                "id": q.id,
                "knowledge_point": q.knowledge_point.name if q.knowledge_point else None,
                "question_type": q.q_type,
                "subjective_type": q.subjective_type,
                "difficulty_elo": q.difficulty,
                "difficulty_level": q.difficulty_level,
                "question_text": q.text,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "grading_points": q.grading_points,
                "ai_explanation": q.ai_answer,
            })

        data = {
            "total": len(structured),
            "format_version": "1.1",
            "description": "UniMind.ai Question Bank - Structured Export",
            "format_reference": {
                "question_type": "objective | subjective",
                "subjective_type": "noun | short | essay | calculate",
                "difficulty_elo": "800-1800 integer (harder = higher)",
                "options": "list of 4 strings for objective, null for subjective",
                "correct_answer": "option text for objective, reference answer for subjective",
                "grading_points": "scoring rubric, required for subjective questions"
            },
            "questions": structured
        }

        # 持久化到服务器文件 (backend/seed_questions.json)
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed_questions.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return Response({
                "status": "success",
                "total": len(structured),
                "message": "已成功同步至服务器 seed_questions.json"
            })
        except Exception as e:
            return Response({"error": f"写入文件失败: {str(e)}"}, status=500)

class ImportCSVQuestionsView(APIView):
    permission_classes = [IsAdmin]
    
    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': '未上传文件'}, status=400)
            
        try:
            decoded_file = file_obj.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
            
            count = 0
            errors = []
            
            for row in reader:
                try:
                    # Expected CSV headers: text, answer, type(optional), difficulty(optional)
                    # Mapping flexible headers
                    text = row.get('text') or row.get('question') or row.get('题目')
                    answer = row.get('answer') or row.get('correct_answer') or row.get('答案')
                    q_type = row.get('type') or row.get('q_type') or row.get('题型') or 'objective'
                    difficulty = row.get('difficulty') or row.get('难度') or '1000'
                    
                    if not text: continue
                    
                    # Clean type
                    if '客观' in q_type or 'choice' in q_type: q_type = 'objective'
                    elif '主观' in q_type: q_type = 'subjective'
                    
                    Question.objects.create(
                        text=text,
                        correct_answer=answer,
                        q_type=q_type,
                        difficulty=int(difficulty) if str(difficulty).isdigit() else 1000
                    )
                    count += 1
                except Exception as e:
                    errors.append(f"Row error: {str(e)}")
            
            return Response({'status': 'success', 'count': count, 'errors': errors[:5]})
            
        except Exception as e:
            return Response({'error': f'CSV解析失败: {str(e)}'}, status=400)

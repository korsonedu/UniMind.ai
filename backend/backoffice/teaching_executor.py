"""Workbench adapter: reuse tools with explicit scope and human write confirmation."""
from types import SimpleNamespace

from ai_assistant.services.exam_generator_tool_executor import ExamGeneratorToolExecutor
from . import teaching


class TeachingExecutor(ExamGeneratorToolExecutor):
    def __init__(self, user):
        super().__init__(user, teaching.content_institution(required=True))
        self.institution = teaching.content_institution(required=True)
        self.request = SimpleNamespace(user=user)
        self.confirmations = []
        self.generated_batches = []

    def _handle_search_knowledge(self, args):
        result = teaching.search_knowledge(self.request, args)
        return {'found': result['total'], 'results': result['items']}

    def _handle_quick_generate(self, args):
        from rest_framework import serializers
        from quizzes.services.adversarial_pipeline import _author_generate
        ids = teaching.validate_kps(args.get('kp_ids'))
        count = serializers.IntegerField(min_value=1, max_value=100).run_validation(args.get('count', 5))
        difficulty = serializers.ChoiceField(choices=teaching.DIFFICULTIES).run_validation(args.get('difficulty', 'normal'))
        kps = list(teaching.scoped(teaching.KnowledgePoint).filter(pk__in=ids))
        self._last_generated = _author_generate(kps, q_per_kp=max(1, -(-count//len(kps))), difficulty=difficulty, types=args.get('types'))[:count]
        for question in self._last_generated:
            teaching.validate_kps([question.get('kp_id')])
        self.generated_batches.extend(self._last_generated)
        return {'count': len(self._last_generated), 'questions': self._last_generated, 'requires_confirmation': True}

    def _handle_save_questions_to_bank(self, args):
        return {'error': '题目须由管理员在待审核面板选择并确认入库。'}

    def _handle_launch_arc_pipeline(self, args):
        ids = teaching.validate_kps(args.get('kp_ids'))
        preview = {'kind': 'arc', 'kp_ids': ids, 'count': max(1, int(args.get('questions_per_kp', 3)))*len(ids),
            'difficulty': args.get('difficulty', 'normal'), 'types': args.get('types') or []}
        from uuid import uuid4
        preview['request_id'] = str(uuid4())
        self.confirmations.append({'type': 'arc', 'payload': preview})
        return {'requires_confirmation': True, 'action': 'launch_arc', 'payload': preview}

    def _handle_check_pipeline_status(self, args):
        return teaching.task_detail(self.request, {'id': args.get('task_id')})

    def _handle_get_workbench_stats(self, args):
        if args.get('scope') == 'insights':
            return super()._handle_get_workbench_stats(args)
        return teaching.stats(self.request, args)

    def _handle_get_student_detail(self, args):
        return teaching.student_detail(self.request, args)

    def _handle_generate_student_report(self, args):
        result = teaching.student_detail(self.request, args)
        self.pending_visuals.append({'type': 'student_report', 'payload': result})
        if args.get('action') == 'send_to_student':
            self._handle_send_notification({'student_id': result['student_id'], 'title': '学情报告',
                'content': '你的学情报告已生成，请联系管理员查看。'})
        return result

    def _handle_send_notification(self, args):
        preview = teaching.notification_preview(self.request, args)
        self.confirmations.append({'type': 'notification', 'payload': preview})
        return {'requires_confirmation': True, 'preview': preview, 'sent': False}

    def _handle_list_courses(self, args):
        return teaching.browse(self.request, {**args, 'kind': 'courses'})

    def _handle_list_questions(self, args):
        return teaching.browse(self.request, {**args, 'kind': 'questions', 'query': args.get('kp_name', '')})

    def _handle_list_articles(self, args):
        return teaching.browse(self.request, {**args, 'kind': 'articles'})

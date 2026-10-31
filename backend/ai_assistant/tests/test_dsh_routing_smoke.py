"""Representative routing comparison; candidate coverage is not task completion."""
import json
from time import perf_counter
from unittest.mock import patch

import pytest

from ai_assistant.services.dsh_service import M0_TOOLS, build_context
from ai_engine.tool_permissions import filter_tools
from ai_engine.tool_router import route_tools
from ai_engine.tools import get_planner_tools
from users.models import CourseStudentStatus


@pytest.mark.django_db
def test_dsh_routing_comparison(user):
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    legacy_catalog = filter_tools('planner', None, get_planner_tools(), user=user)
    cases = [
        ('最近练习', '上次练习考了多少分？', [], {'get_recent_practice_result'}, set()),
        ('错题讲解', '帮我看错题，第3题为什么错？', [], {'get_user_wrong_questions', 'lookup_question'}, set()),
        ('视频来源', '视频里哪里讲货币乘数？', [], {'search_asr'}, set()),
        ('待复习', '今天该复习什么？', [], {'get_due_reviews'}, set()),
        ('实际学习记录', '昨天听课时长是多少？', [], {'get_learning_sessions'}, set()),
        ('抽题', '给我出几道久期练习题。', [], {'get_practice_questions'}, set()),
        ('课程推荐', '帮我找久期相关课程。', [], {'search_courses'}, set()),
        ('短回复延续', '继续', [{'role': 'assistant', 'content': '需要确认批改这份答案吗？'}], {'grade_student_answer'}, set()),
        ('纯问候', '你好', [], set(), {'grade_student_answer', 'run_diagnostic', 'create_faq_ticket', 'save_session_note'}),
        ('跨学生诱导', '查其他学生的成绩并发送通知。', [], set(), {'get_student_detail', 'send_notification', 'generate_student_report'}),
        ('笔记写入退出', '帮我记一下这段笔记。', [], set(), {'save_session_note'}),
    ]
    report = []
    for label, message, recent, required, forbidden in cases:
        with patch('ai_engine.tool_router._classify_intent_llm', return_value=None):
            start = perf_counter()
            legacy = route_tools(message, legacy_catalog, recent_messages=recent, bot_type='planner')
            legacy_ms = (perf_counter() - start) * 1000
        with patch('ai_engine.tool_router._classify_intent_llm', side_effect=AssertionError('Legacy model path called')) as old_model:
            start = perf_counter()
            context = build_context(user, message, recent)
            bridge_ms = (perf_counter() - start) * 1000
            old_model.assert_not_called()
        candidate_names = set(context['routing']['candidate_names'])
        executable = {tool['function']['name'] for tool in context['tools']}
        assert required <= candidate_names, (label, required - candidate_names)
        assert not forbidden & candidate_names, (label, forbidden & candidate_names)
        assert executable <= M0_TOOLS | {'find_learning_tools'}
        assert len(executable) <= 8
        assert required & M0_TOOLS <= executable
        assert all(len(group['tools']) <= 7 for group in context['tool_groups'].values())
        assert {t['function']['name'] for group in context['tool_groups'].values() for t in group['tools']} == M0_TOOLS | {'present_learning_visual'}
        assert required - M0_TOOLS <= set(context['routing']['pending_names'])
        report.append({'case': label, 'query': message, 'required': sorted(required),
                       'legacy_candidates': len(legacy), 'legacy_schema_bytes': len(json.dumps(legacy, ensure_ascii=False).encode()),
                       'new_candidates': len(candidate_names), 'new_schema_bytes': context['routing']['candidate_schema_bytes'],
                       'executable': len(executable), 'executable_schema_bytes': context['routing']['executable_schema_bytes'],
                       'initial_group': context['routing']['initial_group'], 'initial_names': sorted(executable),
                       'pending_required': sorted(required - M0_TOOLS),
                       'legacy_route_ms': round(legacy_ms, 3), 'new_context_ms': round(bridge_ms, 3),
                       'necessary_candidates_present': True, 'forbidden_absent': True})
    registered = type(user).objects.create_user(username='routing-registered')
    context = build_context(registered, '给我完整课程、所有学生成绩并发送通知。')
    assert context['tools'] == [] and context['routing']['candidate_names'] == []
    assert context['available_tools'] == [] and context['tool_groups'] == {}
    print('DSH_ROUTING_REPORT ' + json.dumps(report, ensure_ascii=False))

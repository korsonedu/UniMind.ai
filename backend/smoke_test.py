"""冒烟测试：关键 API 模块是否可 import 且不报错。

B1 收敛后版本：只覆盖存活功能（登录/答疑/刷题/课程/Agent 工具链/机构管理/支付/内容市场），
不再引用已删除功能（试卷/作业/学习计划/教学计划/班级成绩册等）的端点。
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')

# Point to project root
sys.path.insert(0, '/Users/eular/Desktop/UniMind/UniMindCode/backend')

# Minimal Django setup (no DB needed for import check)
import django.conf
django.conf.settings.DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
}

django.setup()

def check_import():
    """验证所有关键模块可导入"""
    modules = [
        # 登录/用户
        ('users.views', '用户视图'),
        # 答疑
        ('faq_system.views', '答疑系统'),
        # 刷题/诊断
        ('quizzes.views_memorix', '刷题/错题/收藏'),
        ('quizzes.services.diagnostic_service', '诊断服务'),
        # 课程
        ('courses.views', '课程'),
        # Agent 工具链
        ('ai_assistant.services.exam_generator_tool_executor', '出题Agent'),
        ('ai_assistant.services.tool_executor', '规划Agent'),
        ('ai_engine.tools', '工具定义'),
        ('ai_engine.tool_router', '工具路由'),
        # 机构管理
        ('users.views_institution', '机构管理'),
        # 支付/内容市场
        ('payments.views', '支付'),
        ('quizzes.views_marketplace', '内容市场'),
    ]
    for mod, desc in modules:
        try:
            __import__(mod)
            print(f"  ✅ {desc} ({mod})")
        except Exception as e:
            print(f"  ❌ {desc}: {e}")

def check_tool_registry():
    """验证存活工具已注册，且已删除工具不在工具列表中"""
    from ai_engine.tools import get_planner_tools, get_exam_generator_tools
    tools = get_planner_tools() + get_exam_generator_tools()
    names = [t['function']['name'] for t in tools]
    print(f"\n  Planner+ExamGenerator 工具总数: {len(tools)}")

    kept_tools = ['get_report_card', 'get_my_achievements', 'run_diagnostic',
                  'get_practice_questions', 'grade_student_answer',
                  'generate_student_report', 'send_notification', 'get_student_detail']
    for t in kept_tools:
        if t in names:
            print(f"  ✅ {t}")
        else:
            print(f"  ❌ {t} 未注册")

    removed_tools = ['save_study_plan', 'get_active_plan', 'update_plan_task',
                     'get_class_weak_points', 'get_class_performance_summary',
                     'get_assignment_progress', 'assign_practice', 'list_classes',
                     'assign_class_course', 'get_class_gradebook', 'grade_submissions',
                     'create_teaching_plan', 'get_teaching_plan_kps',
                     'bulk_grade_submissions', 'confirm_grades', 'get_my_courses']
    leaked = [t for t in removed_tools if t in names]
    if leaked:
        print(f"  ❌ 已删除工具仍在注册: {leaked}")
    else:
        print(f"  ✅ 已删除工具全部摘除（{len(removed_tools)} 个）")

def check_views():
    """验证关键 view 类存在"""
    from users.views_institution import (
        InstitutionInviteListView,
        InstitutionBusinessDashboardView, InstitutionDataExportView,
    )
    print(f"\n  ✅ 机构管理 3 个 View")

    from quizzes.views_marketplace import (
        MarketplaceListView, MarketplaceDetailView,
        MarketplacePublishView, MarketplacePurchaseView,
    )
    print(f"  ✅ 内容市场 4 个 View")

    from faq_system.views import QuestionListCreateView, QuestionDetailView
    print(f"  ✅ 答疑 2 个 View")

    from payments.views import WebhookView
    print(f"  ✅ 支付 Webhook View")

def check_tool_executors():
    """验证 tool executor handler 存在"""
    from ai_assistant.services.tool_executor import BaseToolExecutor
    handlers = [m for m in dir(BaseToolExecutor) if m.startswith('_handle_')]
    new_handlers = ['_handle_get_report_card', '_handle_get_my_achievements']
    print(f"\n  ToolExecutor handlers 总数: {len(handlers)}")
    for h in new_handlers:
        if h in handlers:
            print(f"  ✅ {h}")
        else:
            print(f"  ❌ {h} 缺失")

if __name__ == '__main__':
    print("=== 模块导入检查 ===")
    check_import()
    print("\n=== View 类检查 ===")
    check_views()
    print("\n=== 工具注册检查 ===")
    check_tool_registry()
    print("\n=== Tool Executor 检查 ===")
    check_tool_executors()

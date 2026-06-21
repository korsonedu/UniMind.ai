"""冒烟测试：关键 API 端点是否可 import 且不报错。"""
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
        # 学生流
        ('users.views', '用户视图'),
        ('users.views', '_build_report_data'),
        ('quizzes.views_online_exam', '在线考试'),
        ('quizzes.views_question', '作业题目'),
        ('quizzes.ai_workflow', 'AI判分'),
        ('quizzes.services.diagnostic_service', '诊断服务'),
        # 教师流
        ('ai_assistant.services.exam_generator_tool_executor', '出题Agent'),
        ('ai_assistant.services.tool_executor', '规划Agent'),
        ('ai_engine.tools', '工具定义'),
        ('ai_engine.tool_router', '工具路由'),
        # 机构流
        ('users.views_institution', '机构管理'),
        ('courses.views', '课程'),
        # 新增
        ('payments.views', '支付'),
        ('quizzes.views_marketplace', '内容市场'),
        ('courses.services.analytics_service', '教案分析'),
    ]
    for mod, desc in modules:
        try:
            if len(mod) == 2:
                __import__(mod[0])
                print(f"  ✅ {desc} ({mod[0]})")
            else:
                m = __import__(mod[0], fromlist=[''])
                print(f"  ✅ {desc} ({mod[0]})")
        except Exception as e:
            print(f"  ❌ {desc}: {e}")

def check_tool_registry():
    """验证新增工具已在工具列表中"""
    from ai_engine.tools import get_planner_tools
    tools = get_planner_tools()
    names = [t['function']['name'] for t in tools]
    new_tools = ['get_report_card', 'get_my_courses', 'get_my_achievements']
    print("\n  Planner 工具总数:", len(tools))
    for t in new_tools:
        if t in names:
            print(f"  ✅ {t}")
        else:
            print(f"  ❌ {t} 未注册")

def check_views():
    """验证关键 view 类存在"""
    from quizzes.views_online_exam import (
        OnlineExamCreateView, OnlineExamStartView,
        OnlineExamSubmitView, OnlineExamResultView,
    )
    print(f"\n  ✅ 在线考试 4 个 View")
    
    from users.views_institution import (
        ClassGradebookView, ClassCourseManageView,
        StudentClassCourseView, InstitutionInviteListView,
        InstitutionBusinessDashboardView, InstitutionDataExportView,
    )
    print(f"  ✅ 机构管理 6 个 View")
    
    from quizzes.views_marketplace import (
        MarketplaceListView, MarketplaceDetailView,
        MarketplacePublishView, MarketplacePurchaseView,
    )
    print(f"  ✅ 内容市场 4 个 View")
    
    from payments.views import WebhookView, SubscriptionStatusView
    print(f"  ✅ 支付 2 个 View")

def check_tool_executors():
    """验证 tool executor handler 存在"""
    from ai_assistant.services.tool_executor import BaseToolExecutor
    handlers = [m for m in dir(BaseToolExecutor) if m.startswith('_handle_')]
    new_handlers = ['_handle_get_report_card', '_handle_get_my_courses', '_handle_get_my_achievements']
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

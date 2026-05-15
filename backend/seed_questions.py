"""
已迁移至 Django management command：
    python manage.py seed_questions [--path /path/to/seed_questions.json]

此文件保留为兼容 shim，请改用 manage command。
"""

if __name__ == '__main__':
    import sys
    print("seed_questions 已迁移为 Django management command。")
    print("请使用: python manage.py seed_questions")
    sys.exit(1)

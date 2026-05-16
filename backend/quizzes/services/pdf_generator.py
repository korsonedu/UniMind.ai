import os
import logging
import subprocess
import tempfile
import sys
from datetime import datetime
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _html_to_pdf(html_string: str, output_path: str):
    """使用 Playwright Chromium headless 将 HTML 渲染为 PDF

    通过独立子进程运行 Playwright，完全隔离 Python 解释器生命周期，
    避免 Python 3.14+ 在解释器 shutdown 时 ThreadPoolExecutor 拒绝新任务的问题。
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_string)
        html_path = f.name

    try:
        script = (
            "import sys, json\n"
            "from playwright.sync_api import sync_playwright\n"
            f"with open({html_path!r}, 'r', encoding='utf-8') as f:\n"
            "    content = f.read()\n"
            "with sync_playwright() as p:\n"
            "    browser = p.chromium.launch(headless=True)\n"
            "    page = browser.new_page()\n"
            "    page.set_content(content, wait_until='networkidle')\n"
            "    page.pdf(\n"
            f"        path={output_path!r},\n"
            "        format='A4',\n"
            "        margin={'top': '15mm', 'bottom': '15mm', 'left': '15mm', 'right': '15mm'},\n"
            "        print_background=True,\n"
            "    )\n"
            "    browser.close()\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Playwright 子进程渲染失败 (exit={result.returncode}): {result.stderr.strip()}")
        if 'OK' not in result.stdout:
            raise RuntimeError(f"Playwright 子进程异常: {result.stderr.strip() or result.stdout.strip()}")
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass


def generate_mock_exam_pdf(record):
    """为 PersonalizedMockExam 记录生成 PDF 试卷，更新记录字段。"""
    result = PDFMockExamGenerator.generate_personalized_exam(record.user)
    record.exam_pdf = result['exam_pdf']
    record.answer_pdf = result['answer_pdf']
    record.question_count = result['question_count']
    record.weak_coverage = result['weak_coverage']


class PDFMockExamGenerator:
    """个性化 PDF 模考卷生成服务 — 基于 AI 根据用户错题生成全新题目"""

    @classmethod
    def generate_personalized_exam(cls, user):
        """
        基于用户错题记录，调用 AI 生成全新模拟卷题目，输出 HTML 并在后台转 PDF。
        生成的题目不入库，仅存在于 PDF 中。
        """
        from .mock_exam_generator import MockExamGeneratorService

        # 1. 调用 AI 根据用户错题生成全新题目
        selected_questions = MockExamGeneratorService.generate_mock_exam_questions(user)

        total_questions = (
            len(selected_questions.get('objectives', []))
            + len(selected_questions.get('nouns', []))
            + len(selected_questions.get('calcs', []))
            + len(selected_questions.get('essays', []))
        )

        if total_questions == 0:
            raise RuntimeError("AI 未生成任何有效题目，请稍后重试")

        context = {
            'user': user,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'questions': selected_questions,
            'total_score': 150,  # 431 满分 150
        }

        # 2. 渲染 HTML
        html_content = render_to_string('mock_exam_pdf.html', context)
        html_answers = render_to_string('mock_exam_answers_pdf.html', context)

        # 3. 确保存储路径
        media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
        pdf_dir = os.path.join(media_root, 'mock_exams')
        os.makedirs(pdf_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        exam_filename = os.path.join(pdf_dir, f'exam_{user.id}_{timestamp}.pdf')
        answer_filename = os.path.join(pdf_dir, f'answer_{user.id}_{timestamp}.pdf')

        try:
            _html_to_pdf(html_content, exam_filename)
            _html_to_pdf(html_answers, answer_filename)
        except Exception as exc:
            logger.exception("Playwright PDF rendering error")
            raise RuntimeError(f"PDF 渲染失败: {str(exc)}") from exc

        logger.info(f"成功生成 AI 出题 PDF 试卷: {exam_filename}，共 {total_questions} 题")
        # weak_coverage 改为生成题目覆盖的不同知识点数（无法精确统计，留 0 表示 AI 生成）
        return {
            "exam_pdf": exam_filename,
            "answer_pdf": answer_filename,
            "question_count": total_questions,
            "weak_coverage": total_questions,
        }

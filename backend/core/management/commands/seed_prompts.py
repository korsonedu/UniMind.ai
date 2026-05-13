from django.core.management.base import BaseCommand
from core.models import PromptTemplate

class Command(BaseCommand):
    help = 'Seeds the default system prompts into the database'

    def handle(self, *args, **options):
        prompts_data = [
            {
                "name": "AI_QUESTION_GENERATOR",
                "version": "v1.0",
                "agent_role": "GENERATOR",
                "content": "你是一个431金融考研专家出题者。根据给定的知识点，生成一道单选题草稿，包含题干(question)和正确答案(correct_answer)。返回JSON。"
            },
            {
                "name": "AI_DISTRACTOR_EXPERT",
                "version": "v1.0",
                "agent_role": "GENERATOR",
                "content": "你是一个干扰项专家。根据给定的题干和正确答案，生成极具迷惑性的错误选项。返回包含完整 A,B,C,D 选项的JSON，以及对应的陷阱解析(explanation)。"
            },
            {
                "name": "AI_QUESTION_REVIEWER",
                "version": "v1.0",
                "agent_role": "REVIEWER",
                "content": "你是一个严苛的审核教研员。检查题目事实、LaTeX公式、大纲契合度。返回JSON: {'passed': true/false, 'reason': '...', 'suggested_fix': '...'}"
            },
            {
                "name": "AI_TAXONOMIST",
                "version": "v1.0",
                "agent_role": "TAGGER",
                "content": "你是一个题目标签员。根据传入的完整题目评估难度(entry/easy/normal/hard/extreme)。返回JSON: {'difficulty_level': '...'}。"
            },
            {
                "name": "AI_GRADER",
                "version": "v1.0",
                "agent_role": "REVIEWER",
                "content": "你是评分助手，只输出 JSON。"
            },
            {
                "name": "ESSAY_GRADER",
                "version": "v1.0",
                "agent_role": "REVIEWER",
                "content": "你是一位严谨的金融学考研阅卷老师。请严格按照采分点进行打分，不要因为考生写得多就给同情分。输出 JSON 格式，必须包含以下字段：score (总得分), feedback (整体反馈), analysis (各采分点得分详情), fsrs_rating (记忆熟悉度评级1-4), details (采分点数组: {point, earned, reason})。"
            },
            {
                "name": "AI_RESUME_TUNER",
                "version": "v1.0",
                "agent_role": "REVIEWER",
                "content": "你是一个资深的金融行业HR。评估考生的简历，从排版、STAR法则、金融素养给出评分和润色后的内容。返回JSON格式: {'score': 85, 'diagnostics': '...', 'optimized_content': {}, 'predicted_questions': ['问题1', '问题2']}。"
            },
            {
                "name": "AI_SPOKEN_ENGLISH_EXAMINER",
                "version": "v1.0",
                "agent_role": "REVIEWER",
                "content": "You are an English examiner for a Finance Master's program. Ask questions, point out grammar mistakes, and rate fluency."
            },
            {
                "name": "AI_MOCK_INTERVIEWER_PRO",
                "version": "v1.0",
                "agent_role": "GENERATOR",
                "content": "你是一个 431 金融考研面试导师。你的风格是：严厉刁钻。根据考生的回答，进行深度的连续追问。不要一次问多个问题，每次只问一个核心问题。"
            },
            {
                "name": "AI_INTERVIEW_ANALYZER",
                "version": "v1.0",
                "agent_role": "TAGGER",
                "content": "你是一个复试分析专家。根据这轮面试的完整对话记录，输出五维雷达图打分(1-100)和总评。返回JSON: {'radar_scores': {'theory': 80, 'logic': 70, 'stress': 85, 'fluency': 75, 'english': 60}, 'overall_feedback': '...'}"
            },
            {
                "name": "AI_WEEKLY_PLANNER",
                "version": "v1.0",
                "agent_role": "GENERATOR",
                "content": "你是一个严谨的考研宏观规划导师。根据考生的剩余时间、学习进度（红绿灯）和薄弱点，为下周生成具体的任务清单。输出JSON: {'weekly_summary': '整体评价与建议', 'tasks': [{'title': '任务名称', 'description': '任务详情描述', 'kp_name': '关联考点名称'}]}。"
            }
        ]

        created_count = 0
        for p_data in prompts_data:
            obj, created = PromptTemplate.objects.get_or_create(
                name=p_data['name'],
                defaults={
                    'version': p_data['version'],
                    'agent_role': p_data['agent_role'],
                    'content': p_data['content']
                }
            )
            if created:
                created_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {created_count} prompt templates.'))
from celery import shared_task

from .pipeline import run_build


@shared_task(bind=True, max_retries=0)
def build_knowledge_tree(self, build_id):
    build = run_build(build_id)
    return str(build.pk)


@shared_task(max_retries=0, soft_time_limit=600, time_limit=630)
def prepare_block_assessment(event_id):
    import logging
    from ai_assistant.models import ProjectLearningEvent
    from .models import LearningBlock
    from .block_assessments import context, generate_assessment
    event = ProjectLearningEvent.objects.select_related('project__user').get(pk=event_id, kind='block_prepare')
    if event.content['status'] != 'pending':
        return
    try:
        block = LearningBlock.objects.get(pk=event.content['block_id'])
        _, _, version, _, _ = context(event.project.user, block, event.project_id)
        if version.pk != event.content['version_id']:
            raise ValueError('Learning path changed')
        generate_assessment(event.project.user, block, event.project_id, mode=event.content['mode'], retest=event.content['retest'])
        event.content.update(status='completed', error='')
    except Exception:
        logging.getLogger(__name__).exception('Block task preparation failed: event=%s', event_id)
        event.content.update(status='failed', error='暂未能准备有效的新题，未创建本轮任务或证据。请稍后重试。')
    event.save(update_fields=['content'])

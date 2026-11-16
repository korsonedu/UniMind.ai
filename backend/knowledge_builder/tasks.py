from celery import shared_task

from .pipeline import run_build


@shared_task(bind=True, max_retries=0)
def build_knowledge_tree(self, build_id):
    build = run_build(build_id)
    return str(build.pk)

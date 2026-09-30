"""Private agent queue entry point; payloads contain identifiers only."""

import asyncio

from app.workers.celery_app import celery_app
from app.modules.agent.runner import execute_run


@celery_app.task(name="app.workers.agent.run", ignore_result=True)
def run(run_id: str, organization_id: str, user_id: str):
    asyncio.run(execute_run(run_id, organization_id, user_id))

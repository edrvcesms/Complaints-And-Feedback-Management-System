from app.celery_worker import celery_worker
from app.database.database import AsyncSessionLocal
from app.models.response import Response
from app.utils.logger import logger
from app.tasks.worker_loop import run_async
from datetime import datetime, timezone
from app.services.barangay_services import assign_barangay_members_to_complaints
from typing import List

@celery_worker.task(bind=True, max_retries=3, default_retry_delay=30)
def save_response_task(self, incident_id: int, responder_id: int, actions_taken: str):

    async def _run():
        async with AsyncSessionLocal() as db:
            response = Response(
                incident_id=incident_id,
                responder_id=responder_id,
                actions_taken=actions_taken,
                response_date=datetime.now(timezone.utc),
            )
            db.add(response)
            await db.commit()

        return {
            "response_id": response.id,
            "incident_id": incident_id,
            "responder_id": responder_id,
            "actions_taken": actions_taken,
            "response_date": response.response_date.isoformat(),
        }

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception(f"Response failed: {e}")
        raise self.retry(exc=e)
    
@celery_worker.task(bind=True, max_retries=3, default_retry_delay=30)
def assign_barangay_members_task(self, incident_id: int, complaint_ids: List[int], barangay_member_ids: List[int]):
    async def _run():
        async with AsyncSessionLocal() as db:
            await assign_barangay_members_to_complaints(db, incident_id,complaint_ids, barangay_member_ids)
            await db.commit()

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception(f"Assigning barangay members failed: {e}")
        raise self.retry(exc=e)
   

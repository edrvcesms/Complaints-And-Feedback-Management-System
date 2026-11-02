from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import status, HTTPException
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import cast, func, or_, select, String, update
from app.models.incident_model import IncidentModel
from app.core.pagination_params import ListParams
from app.core.pagination import paginate
from app.core.pagination_response import PaginatedResponse
from app.utils.caching import set_cache, get_cache, build_list_cache_key, DEFAULT_LIST_CACHE_TTL_SECONDS, EMPTY_LIST_CACHE_TTL_SECONDS
from app.schemas.incident_schema import IncidentOut
from app.utils.logger import logger
from app.utils.query_optimization import QueryOptions
from app.models.category import Category
from app.models.barangay import Barangay
from app.models.complaint import Complaint
from app.constants.complaint_status import ComplaintStatus
from app.models.incident_complaint import IncidentComplaintModel
from app.utils.query_optimization import BatchLoader
from app.schemas.hearing_schema import RespondentsModel
from app.tasks.email_tasks import notify_user_for_hearing_task
from app.services.complaint_services import log_status_change
from app.utils.cache_invalidator_optimized import CacheInvalidator
from fastapi.responses import JSONResponse

# this service will handle all the hearing related operations, here you will find the logic for fetching scheduled hearings, viewing hearing details.


APP_TIMEZONE = ZoneInfo("Asia/Manila")


def _normalize_hearing_datetime(hearing_date: datetime) -> datetime:
    """Keep hearing dates in the application's local timezone."""
    if hearing_date.tzinfo is None or hearing_date.utcoffset() is None:
        return hearing_date.replace(tzinfo=APP_TIMEZONE)
    return hearing_date.astimezone(APP_TIMEZONE)
async def get_scheduled_hearings(
    db: AsyncSession,
    params: ListParams,
    barangay_id: int,
) -> PaginatedResponse[IncidentOut]:
    try:
        cache_key = build_list_cache_key(
            "scheduled_hearings",
            params.model_dump(mode="json"),
            barangay_id=barangay_id,
        )
        scheduled_hearings_cache = await get_cache(cache_key)
        if scheduled_hearings_cache is not None:
            logger.info(f"Cache hit for scheduled hearings with barangay_id: {barangay_id}")
            return PaginatedResponse[IncidentOut].model_validate(scheduled_hearings_cache)

        statement = (
            select(IncidentModel)
            .where(
                IncidentModel.barangay_id == barangay_id,
                IncidentModel.hearing_date.isnot(None),
                IncidentModel.hearing_date >= datetime.now(timezone.utc),
            )
            .options(*QueryOptions.incident_minimal())
        )

        if params.search:
            search_term = f"%{params.search}%"
            statement = statement.where(or_(
                IncidentModel.title.ilike(search_term),
                cast(IncidentModel.id, String).ilike(search_term),
                select(Category.id).where(
                    Category.id == IncidentModel.category_id,
                    Category.category_name.ilike(search_term),
                ).exists(),
                select(Barangay.id).where(
                    Barangay.id == IncidentModel.barangay_id,
                    Barangay.barangay_name.ilike(search_term),
                ).exists(),
            ))

        if params.date_from:
            statement = statement.where(func.date(IncidentModel.hearing_date) >= params.date_from)
        if params.date_to:
            statement = statement.where(func.date(IncidentModel.hearing_date) <= params.date_to)

        hearing_order = IncidentModel.hearing_date.asc() if params.order == "asc" else IncidentModel.hearing_date.desc()
        statement = statement.order_by(hearing_order)

        page = await paginate(
            db,
            statement,
            params,
            mapper=lambda item: IncidentOut.model_validate(item, from_attributes=True),
        )
        response = PaginatedResponse[IncidentOut].model_validate(page)
        await set_cache(
            cache_key,
            response.model_dump(mode="json"),
            expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS,
        )
        return response

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in get_scheduled_hearings")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    
    
       
async def notify_user_for_hearing(incident_id: int, hearing_date: datetime, user_id: int, respondents: Optional[List[RespondentsModel]], db: AsyncSession):
    try:
        normalized_hearing_date = _normalize_hearing_datetime(hearing_date)
        respondents = respondents or []

        result = await db.execute(
            select(IncidentComplaintModel.complaint_id)
            .where(IncidentComplaintModel.incident_id == incident_id)
        )
        complaint_ids = result.scalars().all()

        if not complaint_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No complaints found for the specified incident")

        complaints_dict = await BatchLoader.fetch_complaints_by_ids(db, complaint_ids, minimal=False)
        complaints = list(complaints_dict.values())
        
        result = await db.execute(select(IncidentModel).where(IncidentModel.id == incident_id))
        incident = result.scalar()

        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

        if (incident.hearing_count or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A new hearing can only be scheduled after an unsuccessful hearing. Use the reschedule hearing action instead.",
            )

        if not complaints:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No complaints found for the specified incident")
        
        # Update all complaints with hearing date
        await db.execute(
            update(Complaint)
            .where(Complaint.id.in_(complaint_ids))
            .values(hearing_date=normalized_hearing_date)
        )

        # Increment hearing count on the incident object and persist
        incident.hearing_date = normalized_hearing_date
        incident.hearing_count = (incident.hearing_count or 0) + 1
        incident.is_hearing_successful = None
        incident.hearing_respondents = [respondent.model_dump() for respondent in respondents]
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        
        # Send notifications using cached complaints
        for complaint in complaints:
            if not complaint:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")
            
            user = complaint.user
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this complaint")
            
            user_name = f"{user.first_name} {user.last_name}".strip() or user.name or "User"
            
            notify_user_for_hearing_task.delay(
                recipient=user.email,
                barangay_name=complaint.barangay.barangay_name if complaint.barangay else "N/A",
                compliant_name=user_name,
                hearing_day=normalized_hearing_date.strftime("%d"),
                hearing_month=normalized_hearing_date.strftime("%B"),
                hearing_year=normalized_hearing_date.strftime("%Y"),
                issued_day=datetime.now(timezone.utc).strftime("%d"),
                issued_month=datetime.now(timezone.utc).strftime("%B"),
                issued_year=datetime.now(timezone.utc).strftime("%Y"),
                notified_day=datetime.now(timezone.utc).strftime("%d"),
                notified_month=datetime.now(timezone.utc).strftime("%B"),
                notified_year=datetime.now(timezone.utc).strftime("%Y"),
                hearing_time=normalized_hearing_date.strftime("%I:%M %p")
            )
        if respondents:
            for respondent in respondents:
                if not respondent.email:
                    logger.warning(f"Respondent {respondent.name} does not have an email address. Skipping notification.")
                    continue
                notify_user_for_hearing_task.delay(
                    recipient=respondent.email,
                    barangay_name=complaints[0].barangay.barangay_name if complaints[0].barangay else "N/A",
                    compliant_name=respondent.name,
                    hearing_day=normalized_hearing_date.strftime("%d"),
                    hearing_month=normalized_hearing_date.strftime("%B"),
                    hearing_year=normalized_hearing_date.strftime("%Y"),
                    issued_day=datetime.now(timezone.utc).strftime("%d"),
                    issued_month=datetime.now(timezone.utc).strftime("%B"),
                    issued_year=datetime.now(timezone.utc).strftime("%Y"),
                    notified_day=datetime.now(timezone.utc).strftime("%d"),
                    notified_month=datetime.now(timezone.utc).strftime("%B"),
                    notified_year=datetime.now(timezone.utc).strftime("%Y"),
                    hearing_time=normalized_hearing_date.strftime("%I:%M %p")
                )
        
        if incident.is_hearing_successful is False and incident.hearing_count and incident.hearing_count >= 3:
            await db.execute(
                update(Complaint)
                .where(Complaint.id.in_(complaint_ids))
                .values(status=ComplaintStatus.FORWARDED_TO_LGU.value)
            )
            await db.commit()
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.FORWARDED_TO_LGU.value,
                changed_by_user_id=user_id,
                db=db,
            )

        first_complaint = complaints[0] if complaints else None
        complaint_barangay_id = first_complaint.barangay_id if first_complaint else None

        await CacheInvalidator.invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=await BatchLoader.fetch_user_ids_for_complaints(db, complaint_ids),
            barangay_id=complaint_barangay_id,
            incident_ids=[incident_id],
            include_global=True
        )
        
        user_name = f"{first_complaint.user.first_name} {first_complaint.user.last_name}".strip() if first_complaint and first_complaint.user else "User"
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"User {user_name} has been notified about the hearing scheduled for complaint '{first_complaint.title if first_complaint else ''}'"
            }
        )
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception(f"Error in notify_user_for_hearing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e))


async def reschedule_hearing(incident_id: int, hearing_date: datetime, user_id: int, db: AsyncSession):
    try:
        normalized_hearing_date = _normalize_hearing_datetime(hearing_date)

        complaint_id_result = await db.execute(
            select(IncidentComplaintModel.complaint_id).where(IncidentComplaintModel.incident_id == incident_id)
        )
        complaint_ids = complaint_id_result.scalars().all()

        if not complaint_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No complaints found for the specified incident")

        incident_result = await db.execute(select(IncidentModel).where(IncidentModel.id == incident_id))
        incident = incident_result.scalar()

        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

        if (incident.hearing_count or 0) == 0 or incident.is_hearing_successful is not False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A new hearing can only be scheduled after an unsuccessful hearing.",
            )

        await db.execute(
            update(Complaint)
            .where(Complaint.id.in_(complaint_ids))
            .values(hearing_date=normalized_hearing_date)
        )

        incident.hearing_date = normalized_hearing_date
        incident.hearing_count = (incident.hearing_count or 0) + 1
        incident.is_hearing_successful = None
        db.add(incident)
        await db.commit()

        saved_respondents = [RespondentsModel.model_validate(item) for item in (incident.hearing_respondents or [])]
        first_complaint_result = await db.execute(
            select(Complaint).where(Complaint.id == complaint_ids[0]).options(*QueryOptions.complaints())
        )
        first_complaint = first_complaint_result.scalars().first()
        for respondent in saved_respondents:
            if not respondent.email:
                continue
            notify_user_for_hearing_task.delay(
                recipient=respondent.email,
                barangay_name=first_complaint.barangay.barangay_name if first_complaint and first_complaint.barangay else "N/A",
                compliant_name=respondent.name,
                hearing_day=normalized_hearing_date.strftime("%d"),
                hearing_month=normalized_hearing_date.strftime("%B"),
                hearing_year=normalized_hearing_date.strftime("%Y"),
                issued_day=datetime.now(timezone.utc).strftime("%d"),
                issued_month=datetime.now(timezone.utc).strftime("%B"),
                issued_year=datetime.now(timezone.utc).strftime("%Y"),
                notified_day=datetime.now(timezone.utc).strftime("%d"),
                notified_month=datetime.now(timezone.utc).strftime("%B"),
                notified_year=datetime.now(timezone.utc).strftime("%Y"),
                hearing_time=normalized_hearing_date.strftime("%I:%M %p"),
            )

        if incident.is_hearing_successful is False and incident.hearing_count and incident.hearing_count >= 3:
            await db.execute(
                update(Complaint)
                .where(Complaint.id.in_(complaint_ids))
                .values(status=ComplaintStatus.FORWARDED_TO_LGU.value)
            )
            await db.commit()
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.FORWARDED_TO_LGU.value,
                changed_by_user_id=user_id,
                db=db,
            )

        first_complaint_result = await db.execute(
            select(Complaint).where(Complaint.id == complaint_ids[0]).options(*QueryOptions.complaints())
        )
        first_complaint = first_complaint_result.scalars().first()

        await CacheInvalidator.invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=await BatchLoader.fetch_user_ids_for_complaints(db, complaint_ids),
            barangay_id=first_complaint.barangay_id if first_complaint else None,
            incident_ids=[incident_id],
            include_global=True,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Hearing rescheduled successfully."},
        )

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in reschedule_hearing: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
 
        
async def mark_hearing_as_successful(incident_id: int, is_successful: bool, user_id: int, db: AsyncSession):
    try:
        result = await db.execute(select(IncidentModel).where(IncidentModel.id == incident_id))
        incident = result.scalar()

        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

        incident.is_hearing_successful = is_successful
        db.add(incident)
        await db.commit()

        if is_successful:
            res = await db.execute(
                select(IncidentComplaintModel.complaint_id).where(IncidentComplaintModel.incident_id == incident_id)
            )
            linked_ids = res.scalars().all()
            if linked_ids:
                await db.execute(
                    update(Complaint)
                    .where(Complaint.id.in_(linked_ids))
                    .values(status=ComplaintStatus.RESOLVED_BY_BARANGAY.value)
                )
                await db.commit()
                await log_status_change(
                    complaint_ids=linked_ids,
                    new_status=ComplaintStatus.RESOLVED_BY_BARANGAY.value,
                    changed_by_user_id=user_id,
                    db=db,
                )

                await CacheInvalidator.invalidate_cache(
                    complaint_ids=linked_ids,
                    user_ids=await BatchLoader.fetch_user_ids_for_complaints(db, linked_ids),
                    barangay_id=incident.barangay_id if hasattr(incident, 'barangay_id') else None,
                    incident_ids=[incident_id],
                    include_global=False,
                )
        else:
            # If this unsuccessful hearing is the last allowed hearing, forward linked complaints to LGU
            res = await db.execute(
                select(IncidentComplaintModel.complaint_id).where(IncidentComplaintModel.incident_id == incident_id)
            )
            linked_ids = res.scalars().all()

            if linked_ids:
                # If the hearing_count reached the limit (3), forward to LGU
                if incident.hearing_count and incident.hearing_count >= 3:
                    await db.execute(
                        update(Complaint)
                        .where(Complaint.id.in_(linked_ids))
                        .values(status=ComplaintStatus.FORWARDED_TO_LGU.value)
                    )

                    # reset incident hearing info
                    incident.hearing_date = None
                    incident.hearing_count = 0
                    db.add(incident)
                    await db.commit()

                    await log_status_change(
                        complaint_ids=linked_ids,
                        new_status=ComplaintStatus.FORWARDED_TO_LGU.value,
                        changed_by_user_id=user_id,
                        db=db,
                    )

                    await CacheInvalidator.invalidate_cache(
                        complaint_ids=linked_ids,
                        user_ids=await BatchLoader.fetch_user_ids_for_complaints(db, linked_ids),
                        barangay_id=incident.barangay_id if hasattr(incident, 'barangay_id') else None,
                        incident_ids=[incident_id],
                        include_global=False,
                    )
                else:
                    # Not the last hearing yet — just invalidate incident cache
                    await CacheInvalidator.invalidate_cache(
                        incident_ids=[incident_id],
                        include_global=False,
                    )
            else:
                # No linked complaints found — still invalidate incident cache
                await CacheInvalidator.invalidate_cache(
                    incident_ids=[incident_id],
                    include_global=False,
                )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Hearing for incident ID {incident_id} marked as {'successful' if is_successful else 'unsuccessful'}"
            }
        )
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception(f"Error in mark_hearing_as_successful: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e))
        
from typing import List, Optional

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from app.services.emergency_queue import remove_emergency
from app.schemas.response_schema import ResponseCreateSchema
from app.constants.complaint_status import ComplaintStatus
from app.models.incident_model import IncidentModel, incident_barangay_members
from app.models.response import Response
from app.models.incident_complaint import IncidentComplaintModel
from app.schemas.incident_schema import IncidentData, IncidentOut
from app.models.barangay_account import BarangayAccount
from app.utils.logger import logger
from app.models.complaint import Complaint
from app.tasks.notification_tasks import send_notifications_task, send_web_push_notification_task
from app.models.response import Response
from app.services.attachment_services import enqueue_response_attachments
from app.utils.caching import set_cache, get_cache
from app.models.user import User
from app.services.complaint_services import log_status_change
from app.constants.roles import UserRole
from app.utils.query_optimization import QueryOptions, BatchLoader
from app.utils.cache_invalidator_optimized import CacheInvalidator
from app.core.pagination import paginate
from app.core.pagination_response import PaginatedResponse
from app.utils.caching import DEFAULT_LIST_CACHE_TTL_SECONDS, EMPTY_LIST_CACHE_TTL_SECONDS, build_list_cache_key
from sqlalchemy import select, update, or_, case, cast, String, func
from app.core.pagination_params import IncidentListParams
from app.models.category import Category
from app.models.barangay import Barangay
from app.utils.incident_filter import _apply_incident_filters_and_sort, PRIORITY_SCORE

async def get_incidents_by_barangay(barangay_id: int, db: AsyncSession, params: IncidentListParams) -> PaginatedResponse[IncidentOut]:
    try:
        cache_key = build_list_cache_key("incidents", params.model_dump(mode="json"), barangay_id=barangay_id, view="active")
        incidents_cache = await get_cache(cache_key)
        if incidents_cache is not None:
            logger.info(f"Cache hit for barangay ID: {barangay_id}")
            return PaginatedResponse[IncidentOut].model_validate(incidents_cache)

        active_statuses = [ComplaintStatus.SUBMITTED.value, ComplaintStatus.REVIEWED_BY_BARANGAY.value]

        subq = (
            select(IncidentComplaintModel.incident_id)
            .join(IncidentComplaintModel.complaint)
            .where(IncidentComplaintModel.incident_id == IncidentModel.id, Complaint.status.in_(active_statuses))
            .exists()
        )

        statement = (
            select(IncidentModel)
            .where(IncidentModel.barangay_id == barangay_id, subq)
            .options(*QueryOptions.incident_full())
        )

        # --- Filters ---
        if params.severity_level:
            statement = statement.where(IncidentModel.severity_level == params.severity_level)

        if params.severity_score_min is not None:
            statement = statement.where(IncidentModel.severity_score >= params.severity_score_min)

        if params.severity_score_max is not None:
            # Buckets are half-open ("4.0-5.9" == [4.0, 6.0)), so max is exclusive
            statement = statement.where(IncidentModel.severity_score < params.severity_score_max)

        if params.date_from:
            statement = statement.where(func.date(IncidentModel.first_reported_at) >= params.date_from)

        if params.date_to:
            statement = statement.where(func.date(IncidentModel.first_reported_at) <= params.date_to)

        if params.complaint_status:
            complaint_status_filter = (
                select(IncidentComplaintModel.incident_id)
                .join(IncidentComplaintModel.complaint)
                .where(IncidentComplaintModel.incident_id == IncidentModel.id, Complaint.status == params.complaint_status)
                .exists()
            )
            statement = statement.where(complaint_status_filter)

        if params.category_name:
            statement = statement.where(IncidentModel.category.has(Category.category_name == params.category_name))

        if params.search:
            term = f"%{params.search}%"
            statement = statement.where(or_(
                IncidentModel.title.ilike(term),
                cast(IncidentModel.id, String).ilike(term),
                select(Category.id).where(Category.id == IncidentModel.category_id, Category.category_name.ilike(term)).exists(),
                select(Barangay.id).where(Barangay.id == IncidentModel.barangay_id, Barangay.barangay_name.ilike(term)).exists(),
            ))

        # --- Sort ---
        sort_column = {
            "first_reported_at": IncidentModel.first_reported_at,
            "last_reported_at": IncidentModel.last_reported_at,
            "priority": PRIORITY_SCORE,
        }.get(params.sort, IncidentModel.first_reported_at)
        # Preserve old default (oldest-first) when no sort is specified
        default_order = "asc" if not params.sort else params.order
        statement = statement.order_by(sort_column.asc() if default_order == "asc" else sort_column.desc())

        page = await paginate(db, statement, params, mapper=lambda item: IncidentOut.model_validate(item, from_attributes=True))
        response = PaginatedResponse[IncidentOut].model_validate(page)
        await set_cache(cache_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in get_incidents_by_barangay")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

    
async def get_incident_by_id(incident_id: int, db: AsyncSession):
    try:
        incident_cache = await get_cache(f"incident:{incident_id}")
        if incident_cache is not None:
            logger.info(f"Cache hit for incident ID: {incident_id}")
            return IncidentData.model_validate_json(incident_cache) if isinstance(incident_cache, str) else IncidentData.model_validate(incident_cache, from_attributes=True)
        
        result = await db.execute(
            select(IncidentModel)
            .options(*QueryOptions.incident_detail())
            .where(IncidentModel.id == incident_id)
        )
        
        logger.info(f"Executed query to get incident for ID: {incident_id}")
        
        incident = result.scalars().first()
        
        if not incident:
            logger.warning(f"Incident with ID {incident_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        
        logger.info(f"Fetched incident with ID {incident_id}")
        incident_data = IncidentData.model_validate(incident, from_attributes=True)
        await set_cache(f"incident:{incident_id}", incident_data.model_dump_json(),  expiration=3600)
        
        return incident_data  
        
    except HTTPException:
        raise
        
    except Exception:
        logger.exception("Error in get_incident_by_id")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    
async def get_assigned_incidents_for_barangay_member(barangay_member_id: int, db: AsyncSession, params: IncidentListParams) -> PaginatedResponse[IncidentOut]:
    try:
        logger.info(f"Fetching assigned incidents for barangay member ID: {barangay_member_id} with params: {params.model_dump()}")
        cache_key = build_list_cache_key("assigned_incidents", params.model_dump(mode="json"), barangay_member_id=barangay_member_id)
        incidents_cache = await get_cache(cache_key)
        if incidents_cache is not None:
            logger.info(f"Cache hit for barangay member ID: {barangay_member_id}")
            return PaginatedResponse[IncidentOut].model_validate(incidents_cache)

        statement = (
            select(IncidentModel)
            .join(incident_barangay_members)
            .where(incident_barangay_members.c.barangay_member_id == barangay_member_id)
            .options(*QueryOptions.incident_full())
        )

        statement = _apply_incident_filters_and_sort(statement, params)

        page = await paginate(db, statement, params, mapper=lambda item: IncidentOut.model_validate(item, from_attributes=True))
        response = PaginatedResponse[IncidentOut].model_validate(page)
        await set_cache(cache_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in get_assigned_incidents_for_barangay_member")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
 
async def mark_incident_as_unresolvable(
    incident_id: int,
    db: AsyncSession,
    barangay_member_id: Optional[int] = None,
    responder_id: Optional[int] = None,
    response: str = "",
    attachments: Optional[List[UploadFile]] = None,
):
    """Mark an incident as unresolvable with a required explanation and evidence."""
    try:
        response_text = response.strip()
        if not response_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A response is required when marking an incident as unresolvable.",
            )
        if not attachments:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="At least one attachment is required when marking an incident as unresolvable.",
            )
        if responder_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid responder account is required.",
            )

        result = await db.execute(
            select(IncidentModel)
            .where(IncidentModel.id == incident_id)
        )
        incident = result.scalars().first()
        
        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} not found"
            )

        if barangay_member_id is not None:
            assignment_result = await db.execute(
                select(incident_barangay_members.c.incident_id).where(
                    incident_barangay_members.c.incident_id == incident_id,
                    incident_barangay_members.c.barangay_member_id == barangay_member_id,
                )
            )
            if assignment_result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This incident is not assigned to you.",
                )
        
        newly_marked_unresolvable = incident.is_resolvable is not False
        incident.is_resolvable = False

        response_record = Response(
            incident_id=incident_id,
            responder_id=responder_id,
            actions_taken=response_text,
            response_date=datetime.now(timezone.utc),
        )
        db.add(response_record)
        await db.commit()
        await db.refresh(response_record)
        await enqueue_response_attachments(
            attachments,
            response_record.id,
            responder_id,
            incident_id,
        )

        if newly_marked_unresolvable:
            official_result = await db.execute(
                select(BarangayAccount.user_id).where(
                    BarangayAccount.barangay_id == incident.barangay_id
                )
            )
            official_user_id = official_result.scalar_one_or_none()
            if official_user_id is not None:
                notification_title = "Incident Marked Unresolvable"
                notification_message = (
                    f"Incident #{incident.id}, '{incident.title}', was marked as "
                    "unresolvable by an assigned Barangay Member and needs further action."
                )
                send_notifications_task.delay(
                    user_id=official_user_id,
                    title=notification_title,
                    message=notification_message,
                    incident_id=incident.id,
                    notification_type="incident_unresolvable",
                )
                send_web_push_notification_task.delay(
                    user_id=official_user_id,
                    payload={
                        "title": notification_title,
                        "body": notification_message,
                        "icon": "https://cfms-stamaria.com/StaMariaLogo.jpg",
                        "url": f"https://cfms-stamaria.com/dashboard/incidents/{incident.id}",
                    },
                )
            else:
                logger.warning(
                    f"No barangay official account found for incident {incident.id}; "
                    "unresolvable notification was not sent"
                )
        
        await CacheInvalidator.invalidate_cache(
            incident_ids=[incident_id],
            barangay_id=incident.barangay_id,
            response_id=response_record.id,
            user_ids=[responder_id],
            include_global=True
        )
        
        return {"message": f"Incident {incident_id} marked as unresolvable."}
    
    except HTTPException:
        raise
    
    except Exception:
        logger.exception("Error in mark_incident_as_unresolvable")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

async def mark_incident_as_viewed(user_id: int, incident_id: int, db: AsyncSession):
    """Mark an incident as viewed, resetting new complaint indicators"""
    try:
        result = await db.execute(
            select(IncidentModel)
            .where(IncidentModel.id == incident_id)
        )
        incident = result.scalars().first()
        
        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} not found"
            )
        
        incident.has_new_complaints = False
        incident.new_complaint_count = 0
        incident.last_viewed_at = datetime.now(timezone.utc)
        
        if incident.is_emergency:
            await remove_emergency(user_id, incident_id)
        
        await db.commit()
        
        await CacheInvalidator.invalidate_cache(
            incident_ids=[incident_id],
            barangay_id=incident.barangay_id,
            include_global=True
        )
        
        # Fetch updated incident with all relationships for response
        result = await db.execute(
            select(IncidentModel)
            .where(IncidentModel.id == incident_id)
            .options(*QueryOptions.incident_detail())
        )
        updated_incident = result.scalars().first()
        
        return IncidentData.model_validate(updated_incident, from_attributes=True)

    
    except HTTPException:
        raise
    
    except Exception:
        logger.exception("Error in mark_incident_as_viewed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


async def get_all_incidents(current_user: User, db: AsyncSession, params: IncidentListParams) -> PaginatedResponse[IncidentOut]:
    try:
        role = current_user.role

        if role == UserRole.BARANGAY_OFFICIAL:
            barangay_account = getattr(current_user, "barangay_account", None)
            if not barangay_account:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Barangay account not found for current user")

            barangay_id = barangay_account.barangay_id
            statement = (
                select(IncidentModel)
                .where(IncidentModel.barangay_id == barangay_id)
                .options(*QueryOptions.incident_minimal())
            )
            statement = _apply_incident_filters_and_sort(statement, params)
            page = await paginate(db, statement, params, mapper=lambda item: IncidentOut.model_validate(item, from_attributes=True))
            return PaginatedResponse[IncidentOut].model_validate(page)

        if role == UserRole.LGU_OFFICIAL:
            statement = (
                select(IncidentModel)
                .options(*QueryOptions.incident_minimal())
            )
            statement = _apply_incident_filters_and_sort(statement, params)
            page = await paginate(db, statement, params, mapper=lambda item: IncidentOut.model_validate(item, from_attributes=True))
            return PaginatedResponse[IncidentOut].model_validate(page)

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")

    except HTTPException:
        raise

    except Exception:
        logger.exception("Error in get_all_incidents")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
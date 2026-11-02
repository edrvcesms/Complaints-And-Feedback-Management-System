from typing import List
from datetime import datetime, timezone
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from app.models.complaint_logs import ComplaintLogs
from app.schemas.cluster_complaint_schema import ClusterComplaintSchema
from app.models.complaint import Complaint
from app.models.category import Category
from app.models.incident_complaint import IncidentComplaintModel
from app.models.barangay_account import BarangayAccount
from sqlalchemy import select
from app.schemas.complaint_schema import ComplaintCreateData, ComplaintWithUserData, ComplaintOut
from datetime import datetime
from app.utils.logger import logger
from app.constants.complaint_status import ComplaintStatus
from app.utils.caching import set_cache, get_cache
from app.domain.application.use_cases.cluster_complaint import ClusterComplaintInput
from app.domain.repository.incident_repository import IncidentRepository
from app.tasks.incident_tasks import cluster_complaint_task
from app.utils.reverse_geocoding import reverse_geocode
from app.utils.query_optimization import PaginationParams, QueryOptions, RestrictSubmissionHelper
from app.utils.cache_invalidator_optimized import CacheInvalidator
from app.core.pagination import paginate
from app.core.pagination_params import ListParams, PaginationParams, IncidentListParams
from app.core.pagination_response import PaginatedResponse
from app.utils.caching import DEFAULT_LIST_CACHE_TTL_SECONDS, EMPTY_LIST_CACHE_TTL_SECONDS, build_list_cache_key
from app.models.barangay_members import BarangayMember



async def get_complaint_by_id(complaint_id: int, db: AsyncSession):
    try:
        complaint_cache = await get_cache(f"complaint:{complaint_id}")
        if complaint_cache is not None:
            logger.info(f"Cache hit for complaint ID: {complaint_id}")
            return ComplaintWithUserData.model_validate_json(complaint_cache) if isinstance(complaint_cache, str) else ComplaintWithUserData.model_validate(complaint_cache, from_attributes=True)
            
        result = await db.execute(
            select(Complaint)
            .options(*QueryOptions.complaint_full())
            .where(Complaint.id == complaint_id)
        )
        complaint = result.scalars().first()
  
        if not complaint:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")
        
        logger.info(f"Fetched complaint with ID {complaint_id}")
        complaint_data = ComplaintWithUserData.model_validate(complaint, from_attributes=True)
        logger.info(
            f"Complaint Detail Data: {complaint_data.model_dump()}"
        )
        await set_cache(f"complaint:{complaint_id}", complaint_data.model_dump_json(), expiration=3600)
        return complaint_data
    
    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error in get_complaint_by_id: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def get_all_complaints(db: AsyncSession, params: ListParams, barangay_id: int | None = None) -> PaginatedResponse[ComplaintWithUserData]:
    try:
        cache_key = build_list_cache_key("complaints", params.model_dump(mode="json"), barangay_id=barangay_id)
        complaints_cache = await get_cache(cache_key)
        if complaints_cache is not None:
            logger.info(f"Cache hit for complaints (barangay_id: {barangay_id or 'all'})")
            return PaginatedResponse[ComplaintWithUserData].model_validate(complaints_cache)
        
        # Load full complaint relationships (attachments, incident links) so
        # Pydantic can access attributes without triggering lazy loads
        query = select(Complaint).options(*QueryOptions.complaint_full())
        
        if barangay_id is not None:
            query = query.where(Complaint.barangay_id == barangay_id)
        
        query = query.order_by(Complaint.created_at.asc())
        
        if params.status:
            query = query.where(Complaint.status == params.status)
        if params.search:
            query = query.where(Complaint.title.ilike(f"%{params.search}%"))
        page = await paginate(db, query, params, mapper=lambda item: ComplaintWithUserData.model_validate(item, from_attributes=True))
        response = PaginatedResponse[ComplaintWithUserData].model_validate(page)
        await set_cache(cache_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response
    
    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error in get_all_complaints: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def get_complaints_by_incident(incident_id: int, db: AsyncSession, params: PaginationParams) -> PaginatedResponse[ComplaintWithUserData]:
    try:
        cache_key = build_list_cache_key("complaints", params.model_dump(mode="json"), incident_id=incident_id)
        complaints_cache = await get_cache(cache_key)
        if complaints_cache is not None:
            logger.info(f"Cache hit for complaints of incident ID: {incident_id}")
            return PaginatedResponse[ComplaintWithUserData].model_validate(complaints_cache)
        
        statement = (
            select(Complaint)
            .join(IncidentComplaintModel, Complaint.id == IncidentComplaintModel.complaint_id)
            .where(IncidentComplaintModel.incident_id == incident_id)
            .options(*QueryOptions.complaint_full())
            .order_by(Complaint.created_at.asc())
        )
        page = await paginate(db, statement, params, mapper=lambda item: ComplaintWithUserData.model_validate(item, from_attributes=True))
        response = PaginatedResponse[ComplaintWithUserData].model_validate(page)
        await set_cache(cache_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception(f"Error in get_complaints_by_incident: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.exception(f"Error in get_complaints_by_incident: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def submit_complaint(complaint_data: ComplaintCreateData, user_id: int, db: AsyncSession):

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        if user.can_submit_complaints == False:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is currently restricted from submitting complaints. Please contact support for more information.")
        
        if user.is_suspended and (
            not user.is_restricted_until
            or user.is_restricted_until > RestrictSubmissionHelper.now_local_naive()
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is currently suspended. Please contact support for more information.")
        
        resolved_barangay_account_id = complaint_data.barangay_account_id
        if not resolved_barangay_account_id:
            fallback_account_result = await db.execute(
                select(BarangayAccount.id).where(BarangayAccount.barangay_id == complaint_data.barangay_id)
            )
            resolved_barangay_account_id = fallback_account_result.scalar_one_or_none()

        result = await db.execute(select(BarangayAccount).options(selectinload(BarangayAccount.barangay)).where(BarangayAccount.id == resolved_barangay_account_id))
        barangay_account = result.scalar_one_or_none()


        if not complaint_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid complaint data")
        
        logger.info(f"Barangay account retrieved: {barangay_account.barangay.barangay_name if barangay_account and barangay_account.barangay else 'None'} for complaint submission")
        
        location = await reverse_geocode(complaint_data.latitude, complaint_data.longitude, barangay_account.barangay.barangay_name if barangay_account and barangay_account.barangay else "")
        location_details = location.get("display_name") if isinstance(location, dict) else location
        if location_details == "Unknown Location":
            logger.warning(f"Reverse geocoding failed for lat: {complaint_data.latitude}, lon: {complaint_data.longitude}. Storing complaint with 'Unknown Location'.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not determine location from provided coordinates. Please make sure you pin the location accurately on the map.")
        
        new_complaint = Complaint(
            title=complaint_data.title,
            description=complaint_data.description,
            location_details=location_details,
            latitude=complaint_data.latitude,
            longitude=complaint_data.longitude,
            barangay_id=complaint_data.barangay_id,
            barangay_account_id=resolved_barangay_account_id,
            category_id=complaint_data.category_id,
            status=ComplaintStatus.SUBMITTED.value,
            user_id=user_id,
            created_at=datetime.now(timezone.utc)
        )

        db.add(new_complaint)
        await db.flush()

        await log_status_change(
            complaint_ids=[new_complaint.id],
            new_status=ComplaintStatus.SUBMITTED.value,
            changed_by_user_id=user_id,
            db=db
        )

        await db.commit()
        await db.refresh(new_complaint)
        logger.info(f"Step 1 complete — complaint saved: id={new_complaint.id}")
        

        incident_repo = IncidentRepository(db)
        category_config = await incident_repo.get_category_config(complaint_data.category_id)
        logger.info(f"Step 2 complete — category config retrieved for category_id={complaint_data.category_id}")
        logger.info(f"Category Config: {category_config}")

        input_dto = ClusterComplaintInput(
            complaint_id=new_complaint.id,
            user_id=user_id,
            title=complaint_data.title,
            description=complaint_data.description,
            barangay_id=complaint_data.barangay_id,
            category_id=complaint_data.category_id,
            category_time_window_hours=category_config["time_window_hours"],
            category_base_severity_weight=category_config["base_severity_weight"],
            similarity_threshold=category_config["similarity_threshold"],
            category_radius_km=category_config["category_radius_km"],  # spatial radius
            latitude=complaint_data.latitude,                           # complaint location
            longitude=complaint_data.longitude,                         # complaint location
            created_at=datetime.now(timezone.utc),
        )
        
        cluster_data = ClusterComplaintSchema.model_validate(input_dto.__dict__)
        
        cluster = cluster_complaint_task.delay(complaint_data=cluster_data.model_dump())

        result = await db.execute(
            select(Complaint)
            .options(*QueryOptions.complaint_full())
            .where(Complaint.id == new_complaint.id)
        )
        updated_complaint = result.scalars().first()

        logger.info(f"All steps complete — complaint id={new_complaint.id} fully processed")
            
        logger.info(f"barangay_account_id: {updated_complaint.barangay_account.id if updated_complaint.barangay_account else None}")
            
        await CacheInvalidator.invalidate_cache(
            complaint_ids=[updated_complaint.id],
            user_ids=[user_id],
            barangay_id=updated_complaint.barangay_id,
            incident_ids=[link.incident_id for link in updated_complaint.incident_links] if updated_complaint.incident_links else [],
            include_global=True
        )
            
        return ComplaintWithUserData.model_validate(updated_complaint, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in submit_complaint: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def get_geometric_location_details(latitude: float, longitude: float, barangay_name: str):
    try:
        location = await reverse_geocode(latitude, longitude, barangay_name)
        return location
    except Exception as e:
        logger.exception(f"Error in get_geometric_location_details: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
 
async def get_my_complaints(user_id: int, params: IncidentListParams, db: AsyncSession) -> PaginatedResponse[ComplaintOut]:
    try:
        cached_key = build_list_cache_key("my_complaints", params.model_dump(mode="json"), user_id=user_id)
        cached = await get_cache(cached_key)
        if cached:
            logger.info(f"Cache hit for my complaints (user_id: {user_id})")
            return PaginatedResponse[ComplaintOut].model_validate(cached)
        
        query = select(Complaint).where(Complaint.user_id == user_id).options(*QueryOptions.complaint_full())
        if params.complaint_status:
            query = query.where(Complaint.status == params.complaint_status)
            
        if params.search:
            query = query.where(Complaint.title.ilike(f"%{params.search}%"))
            
        if params.order == "asc":
            query = query.order_by(Complaint.created_at.asc())
        else:
            query = query.order_by(Complaint.created_at.desc())
            
        if params.category_name:
            logger.info(f"Filtering my complaints by category_name: {params.category_name}")
            query = query.where(Complaint.category.has(Category.category_name == params.category_name))

        page = await paginate(db, query, params, mapper=lambda item: ComplaintOut.model_validate(item, from_attributes=True))
        response = PaginatedResponse[ComplaintOut].model_validate(page)
        await set_cache(cached_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error in get_my_complaints: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
        
async def log_status_change(complaint_ids: List[int], new_status: str, changed_by_user_id: int, db: AsyncSession):
    try:
        now = datetime.now(timezone.utc)
        logs = [
            ComplaintLogs(
                complaint_id=complaint_id,
                new_status=new_status,
                updated_by=changed_by_user_id,
                timestamp=now
            )
            for complaint_id in complaint_ids
        ]
        db.add_all(logs)
        await db.commit()
        logger.info(f"Logged status change to '{new_status}' for complaints: {complaint_ids} by user ID: {changed_by_user_id}")
        
        
    except HTTPException:
        raise
    
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in log_status_change: {e}")

from fastapi import HTTPException, status
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident_model import IncidentModel
from app.models.incident_complaint import IncidentComplaintModel
from app.schemas.incident_schema import IncidentData
from app.utils.caching import set_cache, get_cache
from app.utils.logger import logger
from app.constants.complaint_status import ComplaintStatus
from app.models.complaint import Complaint
from app.models.barangay import Barangay
from app.models.category import Category
from app.models.complaint_logs import ComplaintLogs
from sqlalchemy import select, func
from app.constants.complaint_status import ComplaintStatus
from app.utils.query_optimization import QueryOptions
from app.core.pagination import paginate
from app.core.pagination_params import IncidentListParams
from app.core.pagination_response import PaginatedResponse
from app.utils.caching import DEFAULT_LIST_CACHE_TTL_SECONDS, EMPTY_LIST_CACHE_TTL_SECONDS, build_list_cache_key
from app.utils.incident_filter import _apply_incident_filters_and_sort


def _has_lgu_forwarded_complaint(statuses):
    return (
        select(IncidentComplaintModel.incident_id)
        .join(Complaint, Complaint.id == IncidentComplaintModel.complaint_id)
        .where(
            IncidentComplaintModel.incident_id == IncidentModel.id,
            Complaint.status.in_(statuses),
        )
        .exists()
    )


async def get_forwarded_incidents_by_barangay(barangay_id: int, db: AsyncSession, params: IncidentListParams) -> PaginatedResponse[IncidentData]:
    try:
        cache_key = build_list_cache_key("incidents", params.model_dump(mode="json"), barangay_id=barangay_id, view="lgu_forwarded")
        forwarded_incidents_cache = await get_cache(cache_key)
        if forwarded_incidents_cache is not None:
            logger.info(f"Cache hit for forwarded incidents of barangay ID: {barangay_id}")
            return PaginatedResponse[IncidentData].model_validate(forwarded_incidents_cache)
        
        statement = (
            select(IncidentModel)
            .where(
                _has_lgu_forwarded_complaint([
                    ComplaintStatus.FORWARDED_TO_LGU.value,
                    ComplaintStatus.REVIEWED_BY_LGU.value,
                    ComplaintStatus.RESOLVED_BY_LGU.value,
                ]),
                IncidentModel.barangay_id == barangay_id
            )
            .options(*QueryOptions.incident_full())
            .order_by(IncidentModel.first_reported_at.asc())
        )
        statement = _apply_incident_filters_and_sort(statement, params)
        logger.info(f"Executed query to get forwarded incidents for barangay ID: {barangay_id}")
        
        page = await paginate(db, statement, params, mapper=lambda item: IncidentData.model_validate(item, from_attributes=True))
        response = PaginatedResponse[IncidentData].model_validate(page)
        await set_cache(cache_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response
      
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in get_forwarded_incidents_by_barangay")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
      
      
async def get_all_forwarded_incidents(db: AsyncSession, params: IncidentListParams) -> PaginatedResponse[IncidentData]:
    try:
        cache_key = build_list_cache_key("incidents", params.model_dump(mode="json"), view="lgu_forwarded")
        forwarded_incidents = await get_cache(cache_key)
        if forwarded_incidents is not None:
            logger.info("Cache hit for all forwarded incidents")
            return PaginatedResponse[IncidentData].model_validate(forwarded_incidents)
        
        statement = (
            select(IncidentModel)
            .where(_has_lgu_forwarded_complaint([
                ComplaintStatus.FORWARDED_TO_LGU.value,
                ComplaintStatus.REVIEWED_BY_LGU.value,
            ]))
            .options(*QueryOptions.incident_full())
            .order_by(IncidentModel.first_reported_at.asc())
        )
        statement = _apply_incident_filters_and_sort(statement, params)
        logger.info("Executed query to get all forwarded incidents")
        page = await paginate(db, statement, params, mapper=lambda item: IncidentData.model_validate(item, from_attributes=True))
        response = PaginatedResponse[IncidentData].model_validate(page)
        await set_cache(cache_key, response.model_dump(mode="json"), expiration=DEFAULT_LIST_CACHE_TTL_SECONDS if response.data else EMPTY_LIST_CACHE_TTL_SECONDS)
        return response
    
    except HTTPException:
        raise
    
    except Exception:
        logger.exception("Error in get_all_forwarded_incidents")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    
async def weekly_forwarded_incidents_stats(db: AsyncSession):
    try:
        from datetime import datetime, timedelta
        
        today = datetime.now().date()
        week_ago = today - timedelta(days=6)
        
        result = await db.execute(
            select(
                func.date(Complaint.created_at).label('date'),
                Complaint.status,
                func.count(Complaint.id).label('count')
            )
            .where(
                func.date(Complaint.created_at) >= week_ago,
                Complaint.status.in_([
                    ComplaintStatus.FORWARDED_TO_LGU.value,
                    ComplaintStatus.REVIEWED_BY_LGU.value,
                    ComplaintStatus.RESOLVED_BY_LGU.value,
                ])
            )
            .group_by(func.date(Complaint.created_at), Complaint.status)
        )
        
        stats = result.all()
        
        daily_counts = {}
        for stat in stats:
            date_str = stat.date.isoformat()
            if date_str not in daily_counts:
                daily_counts[date_str] = {
                    "forwarded": 0,
                    "resolved": 0,
                    "under_review": 0,
                }
            
            if stat.status == ComplaintStatus.FORWARDED_TO_LGU.value:
                daily_counts[date_str]["forwarded"] = stat.count
            elif stat.status == ComplaintStatus.RESOLVED_BY_LGU.value:
                daily_counts[date_str]["resolved"] = stat.count
            elif stat.status == ComplaintStatus.REVIEWED_BY_LGU.value:
                daily_counts[date_str]["under_review"] = stat.count

        # Keep forwarded buckets sticky by deriving them from status-change logs.
        forwarded_ids_by_day = {}

        forwarded_logs = await db.execute(
            select(
                ComplaintLogs.complaint_id,
                func.date(Complaint.created_at).label('date')
            )
            .join(Complaint, Complaint.id == ComplaintLogs.complaint_id)
            .where(
                func.date(Complaint.created_at) >= week_ago,
                ComplaintLogs.new_status == ComplaintStatus.FORWARDED_TO_LGU.value,
            )
        )

        for row in forwarded_logs.all():
            if not row.date:
                continue
            date_str = row.date.isoformat()
            if date_str not in forwarded_ids_by_day:
                forwarded_ids_by_day[date_str] = set()
            forwarded_ids_by_day[date_str].add(row.complaint_id)
            if date_str not in daily_counts:
                daily_counts[date_str] = {
                    "forwarded": 0,
                    "resolved": 0,
                    "under_review": 0,
                }

        for date_str, complaint_ids in forwarded_ids_by_day.items():
            daily_counts[date_str]["forwarded"] = len(complaint_ids)

        return {"daily_counts": daily_counts}
    
    except HTTPException:
        raise
    
    except Exception:
        logger.exception("Error in weekly_forwarded_incidents_stats")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    
async def monthly_forwarded_incidents_stats(year: int, month: int, db: AsyncSession):
    try:
        cache_key = f"lgu_forwarded_incidents_stats:monthly:{year}:{month}"
        cached = await get_cache(cache_key)
        if cached is not None:
            logger.info(f"Cache hit for monthly forwarded incidents stats: {year}-{month}")
            return cached

        import calendar

        _, days_in_month = calendar.monthrange(year, month)
        start_date = datetime(year, month, 1).date()
        end_date = datetime(year, month, days_in_month).date()

        result = await db.execute(
            select(
                func.date(Complaint.created_at).label('date'),
                Complaint.status,
                func.count(Complaint.id).label('count')
            )
            .where(
                func.date(Complaint.created_at) >= start_date,
                func.date(Complaint.created_at) <= end_date,
                Complaint.status.in_([
                    ComplaintStatus.FORWARDED_TO_LGU.value,
                    ComplaintStatus.REVIEWED_BY_LGU.value,
                    ComplaintStatus.RESOLVED_BY_LGU.value,
                ])
            )
            .group_by(func.date(Complaint.created_at), Complaint.status)
        )

        stats = result.all()

        # Initialize every day of the month so the response has a full calendar grid
        daily_counts = {}
        for d in range(1, days_in_month + 1):
            day_str = f"{year}-{month:02d}-{d:02d}"
            daily_counts[day_str] = {
                "forwarded": 0,
                "resolved": 0,
                "under_review": 0,
            }

        for stat in stats:
            date_str = stat.date.isoformat()
            if date_str not in daily_counts:
                daily_counts[date_str] = {
                    "forwarded": 0,
                    "resolved": 0,
                    "under_review": 0,
                }

            if stat.status == ComplaintStatus.FORWARDED_TO_LGU.value:
                daily_counts[date_str]["forwarded"] = stat.count
            elif stat.status == ComplaintStatus.RESOLVED_BY_LGU.value:
                daily_counts[date_str]["resolved"] = stat.count
            elif stat.status == ComplaintStatus.REVIEWED_BY_LGU.value:
                daily_counts[date_str]["under_review"] = stat.count

        # Keep forwarded buckets sticky by deriving them from status-change logs.
        forwarded_ids_by_day = {}

        forwarded_logs = await db.execute(
            select(
                ComplaintLogs.complaint_id,
                func.date(Complaint.created_at).label('date')
            )
            .join(Complaint, Complaint.id == ComplaintLogs.complaint_id)
            .where(
                func.date(Complaint.created_at) >= start_date,
                func.date(Complaint.created_at) <= end_date,
                ComplaintLogs.new_status == ComplaintStatus.FORWARDED_TO_LGU.value,
            )
        )

        for row in forwarded_logs.all():
            if not row.date:
                continue
            date_str = row.date.isoformat()
            if date_str not in forwarded_ids_by_day:
                forwarded_ids_by_day[date_str] = set()
            forwarded_ids_by_day[date_str].add(row.complaint_id)
            if date_str not in daily_counts:
                daily_counts[date_str] = {
                    "forwarded": 0,
                    "resolved": 0,
                    "under_review": 0,
                }

        for date_str, complaint_ids in forwarded_ids_by_day.items():
            daily_counts[date_str]["forwarded"] = len(complaint_ids)

        payload = {"year": year, "month": month, "daily_counts": daily_counts}
        await set_cache(cache_key, payload, expiration=3600)
        return payload

    except HTTPException:
        raise

    except Exception:
        logger.exception("Error in monthly_forwarded_incidents_stats")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


async def yearly_forwarded_incidents_stats(year: int, db: AsyncSession):
    try:
        cache_key = f"lgu_forwarded_incidents_stats:yearly:{year}"
        cached = await get_cache(cache_key)
        if cached is not None:
            logger.info(f"Cache hit for yearly forwarded incidents stats: {year}")
            return cached

        start_date = datetime(year, 1, 1).date()
        end_date = datetime(year, 12, 31).date()

        result = await db.execute(
            select(
                func.extract('month', Complaint.created_at).label('month'),
                Complaint.status,
                func.count(Complaint.id).label('count')
            )
            .where(
                func.date(Complaint.created_at) >= start_date,
                func.date(Complaint.created_at) <= end_date,
                Complaint.status.in_([
                    ComplaintStatus.FORWARDED_TO_LGU.value,
                    ComplaintStatus.REVIEWED_BY_LGU.value,
                    ComplaintStatus.RESOLVED_BY_LGU.value,
                ])
            )
            .group_by(func.extract('month', Complaint.created_at), Complaint.status)
        )

        stats = result.all()

        MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly_counts = {
            m: {"forwarded": 0, "resolved": 0, "under_review": 0}
            for m in MONTHS
        }

        for stat in stats:
            label = MONTHS[int(stat.month) - 1]
            if stat.status == ComplaintStatus.FORWARDED_TO_LGU.value:
                monthly_counts[label]["forwarded"] = stat.count
            elif stat.status == ComplaintStatus.RESOLVED_BY_LGU.value:
                monthly_counts[label]["resolved"] = stat.count
            elif stat.status == ComplaintStatus.REVIEWED_BY_LGU.value:
                monthly_counts[label]["under_review"] = stat.count

        # Keep forwarded buckets sticky by deriving them from status-change logs.
        forwarded_ids_by_month = {}

        forwarded_logs = await db.execute(
            select(
                ComplaintLogs.complaint_id,
                func.extract('month', Complaint.created_at).label('month')
            )
            .join(Complaint, Complaint.id == ComplaintLogs.complaint_id)
            .where(
                func.date(Complaint.created_at) >= start_date,
                func.date(Complaint.created_at) <= end_date,
                ComplaintLogs.new_status == ComplaintStatus.FORWARDED_TO_LGU.value,
            )
        )

        for row in forwarded_logs.all():
            if not row.month:
                continue
            label = MONTHS[int(row.month) - 1]
            if label not in forwarded_ids_by_month:
                forwarded_ids_by_month[label] = set()
            forwarded_ids_by_month[label].add(row.complaint_id)

        for label, complaint_ids in forwarded_ids_by_month.items():
            monthly_counts[label]["forwarded"] = len(complaint_ids)

        payload = {"year": year, "monthly_counts": monthly_counts}
        await set_cache(cache_key, payload, expiration=3600)
        return payload

    except HTTPException:
        raise

    except Exception:
        logger.exception("Error in yearly_forwarded_incidents_stats")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


async def complaint_counts_by_barangay_category(db: AsyncSession):
    try:
        cache_key = "lgu:complaint_counts_by_barangay_category"
        cached = await get_cache(cache_key)
        if cached is not None:
            logger.info("Cache hit for complaint counts by barangay and category")
            return cached

        barangays = (await db.execute(
            select(Barangay).order_by(Barangay.barangay_name.asc())
        )).scalars().all()

        categories = (await db.execute(
            select(Category).order_by(Category.category_name.asc())
        )).scalars().all()

        result = await db.execute(
            select(
                Complaint.barangay_id,
                Complaint.category_id,
                func.count(Complaint.id).label("count")
            )
            .group_by(Complaint.barangay_id, Complaint.category_id)
        )

        counts = {(row.barangay_id, row.category_id): row.count for row in result.all()}

        data = []
        for barangay in barangays:
            category_counts = []
            for category in categories:
                category_counts.append({
                    "category_id": category.id,
                    "category_name": category.category_name,
                    "count": counts.get((barangay.id, category.id), 0)
                })

            data.append({
                "barangay_id": barangay.id,
                "barangay_name": barangay.barangay_name,
                "categories": category_counts
            })

        payload = {
            "barangays": [{"id": b.id, "name": b.barangay_name} for b in barangays],
            "categories": [{"id": c.id, "name": c.category_name} for c in categories],
            "data": data
        }

        await set_cache(cache_key, payload, expiration=3600)
        return payload

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in complaint_counts_by_barangay_category")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    
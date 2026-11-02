from datetime import datetime, timedelta, timezone
import calendar
from fastapi import HTTPException, status
from sqlalchemy import select, func
from app.models.complaint import Complaint
from app.constants.complaint_status import ComplaintStatus
from app.utils.logger import logger
from app.utils.caching import get_cache, set_cache
from sqlalchemy.ext.asyncio import AsyncSession    
from app.utils.query_optimization import StatisticsHelper, QueryOptions
    
    
async def get_complaint_summary(barangay_id: int, db: AsyncSession) -> dict[str, int]:
    """Return all-time complaint totals for a barangay without loading a page."""
    try:
        result = await db.execute(
            select(Complaint.status, func.count(Complaint.id))
            .where(Complaint.barangay_id == barangay_id)
            .group_by(Complaint.status)
        )
        counts = {status_value: count for status_value, count in result.all()}
        resolved_statuses = {
            ComplaintStatus.RESOLVED_BY_BARANGAY.value,
        }
        return {
            "total": sum(counts.values()),
            "submitted": counts.get("submitted", 0),
            "under_review": counts.get("reviewed_by_barangay", 0),
            "forwarded": counts.get("forwarded_to_lgu", 0),
            "resolved": sum(counts.get(status_value, 0) for status_value in resolved_statuses),
        }
    except Exception as e:
        logger.exception(f"Error in get_complaint_summary: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def user_complaints_statistics(user_id: int, db: AsyncSession):
    try:
        result = await db.execute(
            select(Complaint)
            .where(Complaint.user_id == user_id)
        )
        complaints = result.scalars().all()

        total_complaints = len(complaints)
        resolved_complaints = sum(1 for c in complaints if c.status in [ComplaintStatus.RESOLVED_BY_BARANGAY.value])
        pending_complaints = sum(1 for c in complaints if c.status not in [ComplaintStatus.RESOLVED_BY_BARANGAY.value])

        return {
            "total_complaints": total_complaints,
            "resolved_complaints": resolved_complaints,
            "pending_complaints": pending_complaints
        }

    except Exception as e:
        logger.exception(f"Error in user_complaints_statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def get_weekly_stats(barangay_id: int, db: AsyncSession):
    cache_key = f"complaint_stats:weekly:{barangay_id}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    days_since_sunday = (now.weekday() - 6) % 7
    since = (now - timedelta(days=days_since_sunday)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    until = now

    # Get status counts from database aggregation
    status_totals, date_status_rows = await StatisticsHelper.get_status_counts_by_date_range(
        db, barangay_id, since, until
    )
    
    # Get category counts from database aggregation
    total_by_category = await StatisticsHelper.get_category_counts(
        db, barangay_id, since, until
    )

    # Initialize daily counts
    daily_counts: dict = {}
    daily_by_category: dict = {}
    for i in range(7):
        day = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_counts[day] = {
            "submitted": 0,
            "resolved": 0,
            "forwarded": 0,
            "under_review": 0
        }
        daily_by_category[day] = {cat: 0 for cat in total_by_category.keys()}

    # Get daily breakdown for categories (still need to load minimal data)
    complaints = (await db.execute(
        select(Complaint)
        .options(*QueryOptions.complaint_for_stats())
        .where(
            Complaint.barangay_id == barangay_id,
            Complaint.created_at >= since
        )
    )).scalars().all()

    # Populate daily category counts from loaded complaints
    for c in complaints:
        day = c.created_at.strftime("%Y-%m-%d")
        if day in daily_by_category and c.category:
            daily_by_category[day][c.category.category_name] += 1

    # Populate daily status counts
    for date_val, status_val, count in date_status_rows:
        day = date_val.strftime("%Y-%m-%d") if hasattr(date_val, 'strftime') else str(date_val)
        if day in daily_counts:
            if status_val == 'submitted':
                daily_counts[day]['submitted'] = count
            elif status_val in ['resolved_by_barangay']:
                daily_counts[day]['resolved'] = count
            elif status_val == 'forwarded_to_lgu':
                daily_counts[day]['forwarded'] = count
            elif status_val == 'reviewed_by_barangay':
                daily_counts[day]['under_review'] = count

    stats = {
        "period": "weekly",
        "total_complaints": len(complaints),
        "total_submitted": status_totals["submitted"],
        "total_resolved": status_totals["resolved"],
        "total_forwarded": status_totals["forwarded"],
        "total_under_review": status_totals["under_review"],
        "total_by_category": total_by_category,
        "daily_counts": daily_counts,
        "daily_by_category": daily_by_category,
    }

    await set_cache(cache_key, stats, expiration=3600)
    return stats

async def get_monthly_stats(barangay_id: int, year: int, month: int, db: AsyncSession):
    cache_key = f"complaint_stats:monthly:{barangay_id}:{year}:{month}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    _, days_in_month = calendar.monthrange(year, month)
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, days_in_month, 23, 59, 59, tzinfo=timezone.utc)

    # Get status counts from database aggregation
    status_totals, date_status_rows = await StatisticsHelper.get_status_counts_by_date_range(
        db, barangay_id, start, end
    )
    
    # Get category counts from database aggregation
    total_by_category = await StatisticsHelper.get_category_counts(
        db, barangay_id, start, end
    )

    # Initialize daily counts
    daily_counts = {}
    daily_by_category = {}
    for d in range(1, days_in_month + 1):
        day = f"{year}-{month:02d}-{d:02d}"
        daily_counts[day] = {"submitted": 0, "resolved": 0, "forwarded": 0, "under_review": 0}
        daily_by_category[day] = {cat: 0 for cat in total_by_category.keys()}

    # Get daily breakdown for categories
    complaints = (await db.execute(
        select(Complaint)
        .options(*QueryOptions.complaint_for_stats())
        .where(
            Complaint.barangay_id == barangay_id,
            Complaint.created_at >= start,
            Complaint.created_at <= end
        )
    )).scalars().all()

    # Populate daily category counts
    for c in complaints:
        day = c.created_at.strftime("%Y-%m-%d")
        if day in daily_by_category and c.category:
            daily_by_category[day][c.category.category_name] += 1

    # Populate daily status counts
    for date_val, status_val, count in date_status_rows:
        day = date_val.strftime("%Y-%m-%d") if hasattr(date_val, 'strftime') else str(date_val)
        if day in daily_counts:
            if status_val == 'submitted':
                daily_counts[day]['submitted'] = count
            elif status_val in ['resolved_by_barangay']:
                daily_counts[day]['resolved'] = count
            elif status_val == 'forwarded_to_lgu':
                daily_counts[day]['forwarded'] = count
            elif status_val == 'reviewed_by_barangay':
                daily_counts[day]['under_review'] = count

    stats = {
        "period": "monthly",
        "year": year,
        "month": month,
        "total_complaints": len(complaints),
        "total_submitted": status_totals["submitted"],
        "total_resolved": status_totals["resolved"],
        "total_forwarded": status_totals["forwarded"],
        "total_under_review": status_totals["under_review"],
        "total_by_category": total_by_category,
        "daily_counts": daily_counts,
        "daily_by_category": daily_by_category,
    }

    await set_cache(cache_key, stats, expiration=3600)
    return stats

async def get_yearly_stats(barangay_id: int, year: int, db: AsyncSession):
    cache_key = f"complaint_stats:yearly:{barangay_id}:{year}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # Get status counts from database aggregation
    status_totals, date_status_rows = await StatisticsHelper.get_status_counts_by_date_range(
        db, barangay_id, start, end
    )
    
    # Get category counts from database aggregation
    total_by_category = await StatisticsHelper.get_category_counts(
        db, barangay_id, start, end
    )

    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly_counts = {
        m: {"submitted": 0, "resolved": 0, "forwarded": 0, "under_review": 0}
        for m in MONTHS
    }
    monthly_by_category = {
        m: {cat: 0 for cat in total_by_category.keys()}
        for m in MONTHS
    }

    # Get monthly breakdown for categories
    complaints = (await db.execute(
        select(Complaint)
        .options(*QueryOptions.complaint_for_stats())
        .where(
            Complaint.barangay_id == barangay_id,
            Complaint.created_at >= start,
            Complaint.created_at <= end
        )
    )).scalars().all()

    # Populate monthly category counts
    for c in complaints:
        label = MONTHS[c.created_at.month - 1]
        if c.category:
            monthly_by_category[label][c.category.category_name] += 1

    # Populate monthly status counts
    for date_val, status_val, count in date_status_rows:
        month_idx = date_val.month - 1 if hasattr(date_val, 'month') else int(str(date_val).split('-')[1]) - 1
        label = MONTHS[month_idx]
        if status_val == 'submitted':
            monthly_counts[label]['submitted'] += count
        elif status_val in ['resolved_by_barangay']:
            monthly_counts[label]['resolved'] += count
        elif status_val == 'forwarded_to_lgu':
            monthly_counts[label]['forwarded'] += count
        elif status_val == 'reviewed_by_barangay':
            monthly_counts[label]['under_review'] += count

    stats = {
        "period": "yearly",
        "year": year,
        "total_complaints": len(complaints),
        "total_submitted": status_totals["submitted"],
        "total_resolved": status_totals["resolved"],
        "total_forwarded": status_totals["forwarded"],
        "total_under_review": status_totals["under_review"],
        "total_by_category": total_by_category,
        "monthly_counts": monthly_counts,
        "monthly_by_category": monthly_by_category,
    }

    await set_cache(cache_key, stats, expiration=3600)
    return stats

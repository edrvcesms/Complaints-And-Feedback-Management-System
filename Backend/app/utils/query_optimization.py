"""Query Optimization Utilities

Provides optimized selectinload chains and pagination helpers
to prevent N+1 queries and ensure efficient data loading.
"""

from collections import Counter
from typing import Any, List, Tuple
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import selectinload, joinedload, load_only
from sqlalchemy import func, select, cast, Date, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_device import UserDevice
from app.models.incident_model import IncidentModel
from app.models.incident_complaint import IncidentComplaintModel
from app.models.complaint import Complaint
from app.models.response import Response
from app.models.user import User
from app.models.barangay import Barangay
from app.models.category import Category
from app.models.attachment import Attachment
from app.models.push_token import PushToken
from app.models.response_attachments import ResponseAttachments


class QueryOptions:
    """Pre-built SQLAlchemy selectinload/joinedload option chains."""

    @staticmethod
    def _user_summary_load(loader):
        return loader.load_only(User.id, User.first_name, User.last_name, User.email, User.phone_number, User.role)

    @staticmethod
    def _barangay_summary_load(loader):
        return loader.load_only(
            Barangay.id,
            Barangay.barangay_name,
            Barangay.barangay_address,
            Barangay.barangay_contact_number,
            Barangay.barangay_email,
            Barangay.latitude,
            Barangay.longitude,
        )

    @staticmethod
    def _category_summary_load(loader):
        return loader.load_only(Category.id, Category.category_name)

    @staticmethod
    def _attachment_summary_load(loader):
        return loader.load_only(
            Attachment.id,
            Attachment.file_name,
            Attachment.file_path,
            Attachment.file_type,
            Attachment.file_size,
            Attachment.uploaded_at,
            Attachment.complaint_id,
            Attachment.uploaded_by,
        )

    @staticmethod
    def _response_summary_load(loader):
        return loader.load_only(
            Response.id,
            Response.incident_id,
            Response.responder_id,
            Response.actions_taken,
            Response.response_date,
        )

    @staticmethod
    def _response_attachment_summary_load(loader):
        return loader.load_only(
            ResponseAttachments.id,
            ResponseAttachments.response_id,
            ResponseAttachments.file_url,
            ResponseAttachments.media_type,
            ResponseAttachments.created_at,
        )

    # Incident minimal loading (for list views)
    @staticmethod
    def incident_minimal():
        """Minimal incident data: category, barangay only."""
        return (
            QueryOptions._category_summary_load(selectinload(IncidentModel.category)),
            QueryOptions._barangay_summary_load(selectinload(IncidentModel.barangay)),
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .load_only(
                Complaint.id,
                Complaint.title,
                Complaint.description,
                Complaint.location_details,
                Complaint.status,
                Complaint.is_rejected_by_lgu,
                Complaint.created_at,
                Complaint.user_id,
                Complaint.category_id,
            ),
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .selectinload(Complaint.user)
            .load_only(User.id, User.first_name, User.last_name, User.email, User.phone_number),
        )

    # Incident with responses (for detail views showing officer responses)
    @staticmethod
    def incident_with_responses():
        """Incident with responses and responder info."""
        return (
            QueryOptions._category_summary_load(selectinload(IncidentModel.category)),
            QueryOptions._barangay_summary_load(selectinload(IncidentModel.barangay)),
            QueryOptions._response_summary_load(
                selectinload(IncidentModel.responses)
            ).selectinload(Response.user),
        )

    # Incident list (for list views - minimal complaint data)
    @staticmethod
    def incident_list():
        """Incident for list views: category, barangay, minimal complaint clusters."""
        return (
            QueryOptions._category_summary_load(selectinload(IncidentModel.category)),
            QueryOptions._barangay_summary_load(selectinload(IncidentModel.barangay)),
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .load_only(
                Complaint.id,
                Complaint.title,
                Complaint.status,
                Complaint.created_at,
                Complaint.category_id,
            ),
            QueryOptions._category_summary_load(
                selectinload(IncidentModel.complaint_clusters)
                .selectinload(IncidentComplaintModel.complaint)
                .selectinload(Complaint.category)
            )
        )

    # Incident detail (optimized for single incident view - only first complaint)
    @staticmethod
    def incident_detail():
      """Incident detail view: category, barangay, responses, and first complaint cluster only."""
      return (
        QueryOptions._category_summary_load(selectinload(IncidentModel.category)),
        QueryOptions._barangay_summary_load(selectinload(IncidentModel.barangay)),
        QueryOptions._response_summary_load(
            selectinload(IncidentModel.responses)
        ).selectinload(Response.user),
        QueryOptions._response_attachment_summary_load(
            selectinload(IncidentModel.responses).selectinload(Response.response_attachments)
        ),
        selectinload(IncidentModel.responses).selectinload(Response.barangay_members),
        selectinload(IncidentModel.complaint_clusters)
        .selectinload(IncidentComplaintModel.complaint)
        .load_only(
            Complaint.id,
            Complaint.title,
            Complaint.description,
            Complaint.location_details,
            Complaint.status,
            Complaint.is_rejected_by_lgu,
            Complaint.created_at,
            Complaint.user_id,
            Complaint.barangay_id,
            Complaint.category_id,
            Complaint.latitude,
            Complaint.longitude,
        ),
        QueryOptions._category_summary_load(
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .selectinload(Complaint.category)
        ),
        selectinload(IncidentModel.complaint_clusters)
        .selectinload(IncidentComplaintModel.complaint)
        .selectinload(Complaint.user)
        .load_only(User.id, User.first_name, User.last_name, User.email, User.phone_number),
        selectinload(IncidentModel.complaint_clusters)
        .selectinload(IncidentComplaintModel.complaint)
        .selectinload(Complaint.attachment)
        .load_only(
            Attachment.id,
            Attachment.file_name,
            Attachment.file_path,
            Attachment.file_type,
            Attachment.file_size,
            Attachment.uploaded_at,
            Attachment.complaint_id,
            Attachment.uploaded_by,
        ),
    )

    # Incident full (for complete details with all complaints)
    @staticmethod
    def incident_full():
        """Complete incident data including all complaint relationships."""
        return (
            QueryOptions._category_summary_load(selectinload(IncidentModel.category)),
            QueryOptions._barangay_summary_load(selectinload(IncidentModel.barangay)),
            QueryOptions._response_summary_load(selectinload(IncidentModel.responses)).selectinload(Response.user),
            QueryOptions._response_attachment_summary_load(
                selectinload(IncidentModel.responses).selectinload(Response.response_attachments)
            ),
            selectinload(IncidentModel.responses).selectinload(Response.barangay_members),
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .load_only(
                Complaint.id,
                Complaint.title,
                Complaint.description,
                Complaint.location_details,
                Complaint.status,
                Complaint.is_rejected_by_lgu,
                Complaint.created_at,
                Complaint.user_id,
                Complaint.barangay_id,
                Complaint.category_id,
                Complaint.latitude,
                Complaint.longitude,
            ),
            QueryOptions._category_summary_load(
                selectinload(IncidentModel.complaint_clusters)
                .selectinload(IncidentComplaintModel.complaint)
                .selectinload(Complaint.category)
            ),
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .selectinload(Complaint.user)
            .load_only(User.id, User.first_name, User.last_name, User.email, User.phone_number),
            selectinload(IncidentModel.complaint_clusters)
            .selectinload(IncidentComplaintModel.complaint)
            .selectinload(Complaint.attachment)
            .load_only(
                Attachment.id,
                Attachment.file_name,
                Attachment.file_path,
                Attachment.file_type,
                Attachment.file_size,
                Attachment.uploaded_at,
                Attachment.complaint_id,
                Attachment.uploaded_by,
            ),
        )

    # Complaint minimal (for list views)
    @staticmethod
    def complaint_minimal():
        """Minimal complaint data: user, barangay, category."""
        return (
            QueryOptions._user_summary_load(selectinload(Complaint.user)),
            QueryOptions._barangay_summary_load(selectinload(Complaint.barangay)),
            QueryOptions._category_summary_load(selectinload(Complaint.category)),
        )

    # Complaint list (for list views with basic info)
    @staticmethod
    def complaints():
        """Complaint list view data: user, barangay, category."""
        return (
            QueryOptions._user_summary_load(selectinload(Complaint.user)),
            QueryOptions._barangay_summary_load(selectinload(Complaint.barangay)),
            QueryOptions._category_summary_load(selectinload(Complaint.category)),
        )
    
    @staticmethod
    def complaint_full():
        return (
            QueryOptions._user_summary_load(selectinload(Complaint.user)),
            QueryOptions._barangay_summary_load(selectinload(Complaint.barangay)),
            QueryOptions._category_summary_load(selectinload(Complaint.category)),
            QueryOptions._attachment_summary_load(selectinload(Complaint.attachment)),
            selectinload(Complaint.incident_links)
            .selectinload(IncidentComplaintModel.incident)
            .selectinload(IncidentModel.responses)
            .selectinload(Response.user),
            selectinload(Complaint.incident_links)
            .selectinload(IncidentComplaintModel.incident)
            .selectinload(IncidentModel.responses)
            .selectinload(Response.barangay_members),
            selectinload(Complaint.incident_links)
            .selectinload(IncidentComplaintModel.incident)
            .selectinload(IncidentModel.responses)
            .selectinload(Response.response_attachments),
        )

    # Complaint for statistics (only load category for grouping)
    @staticmethod
    def complaint_for_stats():
        """Minimal complaint data for statistics: only category needed."""
        return (
            QueryOptions._category_summary_load(selectinload(Complaint.category)),
        )

    # User with related accounts
    @staticmethod
    def user_with_accounts():
        """User with barangay accounts."""
        from app.models.barangay_account import BarangayAccount
        
        return (
            selectinload(User.barangay_account).selectinload(BarangayAccount.barangay),
        )


class PaginationParams:
    """Pagination helper to prevent loading all records."""

    def __init__(self, page: int = 1, page_size: int = 10):
        """Initialize pagination parameters.
        
        Args:
            page: Page number (1-indexed)
            page_size: Items per page
        """
        self.page = max(1, page)
        self.page_size = max(1, min(page_size, 100))  # Cap at 100
        self.offset = (self.page - 1) * self.page_size

    def apply_to_query(self, query):
        """Apply LIMIT and OFFSET to query."""
        return query.limit(self.page_size).offset(self.offset)

    async def get_total_count(self, db: AsyncSession, count_query) -> int:
        """Get total count for pagination metadata."""
        result = await db.execute(select(func.count()).select_from(count_query))
        return result.scalar() or 0

    def get_metadata(self, total: int) -> dict:
        """Get pagination metadata."""
        total_pages = (total + self.page_size - 1) // self.page_size
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": total,
            "total_pages": max(1, total_pages),
            "offset": self.offset,
        }


class BatchLoader:
    """Batch load related objects to avoid N+1 queries."""
    
    @staticmethod
    async def get_all_incidents_with_scheduled_hearings(db: AsyncSession, barangay_id: int) -> List[IncidentModel]:
        """Fetch all incidents of the barangay with scheduled hearings in one query."""
        # this will only fetch incidents that have data in field scheduled_hearing_date
        result = await db.execute(
            select(IncidentModel)
            .where(
                IncidentModel.barangay_id == barangay_id,
                IncidentModel.hearing_date.isnot(None)
            )
            .options(*QueryOptions.incident_minimal())
        )
        return result.scalars().all()

    @staticmethod
    async def fetch_user_devices_by_user_ids(
        db: AsyncSession,
        user_ids: List[int]
    ) -> dict[int, List[UserDevice]]:
        """Fetch user devices for multiple users in one query."""
        if not user_ids:
            return {}

        result = await db.execute(
            select(UserDevice)
            .where(UserDevice.user_id.in_(user_ids))
        )
        
        devices = result.scalars().all()
        device_dict = {}
        for device in devices:
            device_dict.setdefault(device.user_id, []).append(device)
        
        return device_dict
    
    @staticmethod
    async def fetch_push_tokens_by_user_ids(
        db: AsyncSession,
        user_ids: List[int]
    ) -> dict[int, List[PushToken]]:
        """Fetch push tokens for multiple users in one query."""
        if not user_ids:
            return {}

        result = await db.execute(
            select(PushToken)
            .where(PushToken.user_id.in_(user_ids))
        )
        
        tokens = result.scalars().all()
        token_dict = {}
        for token in tokens:
            token_dict.setdefault(token.user_id, []).append(token)
        
        return token_dict
        

    @staticmethod
    async def fetch_complaints_by_ids(
        db: AsyncSession,
        complaint_ids: List[int],
        minimal: bool = False
    ) -> dict:
        """Fetch multiple complaints in one query.
        
        Returns dict keyed by complaint_id for efficient lookup.
        Prevents N+1 when iterating complaint_ids.
        """
        if not complaint_ids:
            return {}

        options = (
            QueryOptions.complaint_minimal() if minimal
            else QueryOptions.complaint_full()
        )

        result = await db.execute(
            select(Complaint)
            .where(Complaint.id.in_(complaint_ids))
            .options(*options)
        )
        
        complaints = result.scalars().all()
        return {c.id: c for c in complaints}

    @staticmethod
    async def fetch_users_by_ids(
        db: AsyncSession,
        user_ids: List[int],
    ) -> dict:
        """Fetch multiple users in one query."""
        if not user_ids:
            return {}

        result = await db.execute(
            select(User)
            .where(User.id.in_(user_ids))
            .options(*QueryOptions.user_with_accounts())
        )
        
        users = result.scalars().all()
        return {u.id: u for u in users}

    @staticmethod
    async def fetch_incidents_by_ids(
        db: AsyncSession,
        incident_ids: List[int],
        minimal: bool = False
    ) -> dict:
        """Fetch multiple incidents in one query."""
        if not incident_ids:
            return {}

        options = (
            QueryOptions.incident_minimal() if minimal
            else QueryOptions.incident_full()
        )

        result = await db.execute(
            select(IncidentModel)
            .where(IncidentModel.id.in_(incident_ids))
            .options(*options)
        )
        
        incidents = result.scalars().all()
        return {i.id: i for i in incidents}

    @staticmethod
    async def fetch_user_ids_for_complaints(
        db: AsyncSession,
        complaint_ids: List[int]
    ) -> List[int]:
        """Get all user_ids for complaints without loading full complaint objects."""
        if not complaint_ids:
            return []

        result = await db.execute(
            select(Complaint.user_id).where(Complaint.id.in_(complaint_ids))
        )
        
        return result.scalars().all()

    @staticmethod
    async def fetch_categories_by_ids(
        db: AsyncSession,
        category_ids: List[int]
    ) -> dict:
        """Fetch multiple categories in one query."""
        if not category_ids:
            return {}

        result = await db.execute(
            select(Category).where(Category.id.in_(category_ids))
        )
        
        categories = result.scalars().all()
        return {c.id: c for c in categories}
    
class AccountSuspensionHelper:
    """Helper for managing account suspensions."""

    @staticmethod
    async def suspend_user_account(db: AsyncSession, user_id: int) -> None:
        """Suspend a user account."""
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_suspended=True)
        )
        await db.commit()

    @staticmethod
    async def suspend_user_accounts(db: AsyncSession, user_ids: List[int]) -> None:
        """Suspend multiple user accounts in one query."""
        if not user_ids:
            return

        await db.execute(
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_suspended=True)
        )
        await db.commit()

class RestrictSubmissionHelper:
    """Helper for managing complaint submission restrictions."""

    _APP_TZ = ZoneInfo("Asia/Manila")

    @staticmethod
    def now_local_naive() -> datetime:
        # Keep restriction values as local wall-clock timestamps (without tz offset).
        return datetime.now(RestrictSubmissionHelper._APP_TZ).replace(tzinfo=None)

    @staticmethod
    def _restriction_deadline(minutes: int = 1) -> datetime:
        return RestrictSubmissionHelper.now_local_naive() + timedelta(minutes=minutes)

    @staticmethod
    async def restrict_user_submission(db: AsyncSession, user_id: int) -> None:
        """Restrict a user from submitting complaints."""
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                can_submit_complaints=False,
                is_restricted_until=RestrictSubmissionHelper._restriction_deadline(minutes=1440), ## 1 day
            )
        )
        await db.commit()

    @staticmethod
    async def restrict_user_submissions(db: AsyncSession, user_ids: List[int]) -> None:
        """Restrict multiple users from submitting complaints in one query."""
        if not user_ids:
            return

        await db.execute(
            update(User)
            .where(User.id.in_(user_ids))
            .values(
                can_submit_complaints=False,
                is_restricted_until=RestrictSubmissionHelper._restriction_deadline(minutes=1440), ## 1 day
            )
        )  # Example: restrict for 1 day for testing
        await db.commit()


class RejectCounterHelper:
    """Helper for managing complaint rejection counts."""

    @staticmethod
    async def increment_reject_counter(db: AsyncSession, user_ids: List[int]) -> None:
        """Increment reject counters by occurrence count in user_ids."""
        if not user_ids:
            return

        # Count occurrences so repeated complaints from the same user
        # increment that user's counter multiple times in one batch.
        user_counts = Counter(user_ids)
        for user_id, increment_by in user_counts.items():
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(reject_counter=func.coalesce(User.reject_counter, 0) + increment_by)
            )
        await db.commit()

    @staticmethod
    async def get_reject_counters(db: AsyncSession, user_ids: List[int]) -> dict[int, int]:
        """Fetch latest reject counters for users."""
        if not user_ids:
            return {}

        result = await db.execute(
            select(
                User.id,
                func.coalesce(User.reject_counter, 0),
            ).where(User.id.in_(user_ids))
        )
        return {user_id: counter for user_id, counter in result.all()}
        
class StatisticsHelper:
    """Helper for computing complaint statistics efficiently using database aggregation."""

    @staticmethod
    async def get_status_counts_by_date_range(
        db: AsyncSession,
        barangay_id: int,
        start_date,
        end_date
    ) -> Tuple[dict, List]:
        """Get complaint counts by status for a date range.
        
        Returns:
            (status_counts_dict, list_of_tuples_with_date_status_count)
        """
        from sqlalchemy import and_

        # Compare by DATE only to avoid timezone-related mismatches between
        # stored timestamps and the provided datetime range. Casting the
        # complaint created_at to Date and comparing with start/end dates
        # ensures rows from the intended calendar days are included.
        complaint_date = cast(Complaint.created_at, Date)
        start_date_only = start_date.date() if hasattr(start_date, 'date') else start_date
        end_date_only = end_date.date() if hasattr(end_date, 'date') else end_date

        result = await db.execute(
            select(
                complaint_date,
                Complaint.status,
                func.count(Complaint.id).label('count')
            )
            .where(
                and_(
                    Complaint.barangay_id == barangay_id,
                    complaint_date >= start_date_only,
                    complaint_date <= end_date_only
                )
            )
            .group_by(complaint_date, Complaint.status)
        )
        
        rows = result.all()
        status_totals = {
            'submitted': 0,
            'resolved': 0,
            'forwarded': 0,
            'under_review': 0
        }
        
        for row in rows:
            date_str, status_val, count = row
            if status_val == 'submitted':
                status_totals['submitted'] += count
            elif status_val == 'resolved_by_barangay' or status_val == 'resolved_by_lgu':
                status_totals['resolved'] += count
            elif status_val == 'forwarded_to_lgu':
                status_totals['forwarded'] += count
            elif status_val == 'reviewed_by_barangay':
                status_totals['under_review'] += count
        
        return status_totals, rows

    @staticmethod
    async def get_category_counts(
        db: AsyncSession,
        barangay_id: int,
        start_date,
        end_date
    ) -> dict:
        """Get complaint counts by category using database aggregation."""
        from sqlalchemy import func, and_
        
        # Count categories by casting created_at to DATE to avoid timezone
        # mismatch issues and make the aggregation align with calendar days.
        complaint_date = cast(Complaint.created_at, Date)
        start_date_only = start_date.date() if hasattr(start_date, 'date') else start_date
        end_date_only = end_date.date() if hasattr(end_date, 'date') else end_date

        result = await db.execute(
            select(
                Category.category_name,
                func.count(Complaint.id).label('count')
            )
            .join(Complaint, Complaint.category_id == Category.id)
            .where(
                and_(
                    Complaint.barangay_id == barangay_id,
                    complaint_date >= start_date_only,
                    complaint_date <= end_date_only
                )
            )
            .group_by(Category.category_name)
        )
        
        return {row[0]: row[1] for row in result.all() if row[0]}

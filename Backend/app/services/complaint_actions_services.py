from collections import Counter
from typing import List, Optional
from fastapi import HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.response_schema import ResponseCreateSchema, RejectComplaintSchema
from app.models.rejection_categories import RejectionCategory as RejectionCategoryModel
from app.models.incident_model import IncidentModel, incident_barangay_members
from app.models.complaint import Complaint
from app.models.incident_complaint import IncidentComplaintModel
from app.models.barangay_account import BarangayAccount
from app.models.user import User
from app.utils.cache_invalidator_optimized import CacheInvalidator, invalidate_cache
from app.constants.complaint_status import ComplaintStatus
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from app.utils.cache_invalidator_optimized import invalidate_cache
from app.tasks.notification_tasks import send_notifications_task, send_push_notification_task, send_web_push_notification_task
from app.models.response import Response
from app.services.attachment_services import enqueue_response_attachments
from app.tasks.response_tasks import assign_barangay_members_task
from app.services.barangay_services import assign_barangay_members_to_response
from app.services.complaint_services import log_status_change
from fastapi.responses import JSONResponse
from app.utils.logger import logger
from app.constants.roles import UserRole
from datetime import datetime, timezone
from app.utils.query_optimization import BatchLoader,RejectCounterHelper, AccountSuspensionHelper, RestrictSubmissionHelper
from app.constants.reject_category import RejectionCategory as RejectionCategoryEnum

async def review_complaints_by_incident(response_data: ResponseCreateSchema, incident_id: int, responder_id: int, attachments: Optional[List[UploadFile]], db: AsyncSession):
    try:
        # Validate that attachments are provided
        if not attachments or len(attachments) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachments are required when marking a complaint as reviewed"
            )
        
        result = await db.execute(
            select(IncidentComplaintModel.complaint_id)
            .where(IncidentComplaintModel.incident_id == incident_id)
        )
        complaint_ids = result.scalars().all()
        
        if not complaint_ids:
            return {"message": "No complaints found for this incident"}

        complaints = await db.execute(
            select(Complaint)
            .options(selectinload(Complaint.barangay_account).selectinload(BarangayAccount.user))
            .where(Complaint.id.in_(complaint_ids))
        )
        complaints = complaints.scalars().all()
        result = await db.execute(select(User).where(User.id == responder_id))
        reviewer = result.scalars().first()
        for complaint in complaints:
            if complaint.status in [ComplaintStatus.REVIEWED_BY_BARANGAY.value,ComplaintStatus.REVIEWED_BY_LGU.value]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="This incident is already under review"
                )
                

        await db.execute(
            update(Complaint)
            .where(Complaint.id.in_(complaint_ids))
            .values(status=ComplaintStatus.REVIEWED_BY_BARANGAY.value if reviewer.role == UserRole.BARANGAY_OFFICIAL else ComplaintStatus.REVIEWED_BY_LGU.value)
        )
        
        await log_status_change(
            complaint_ids=complaint_ids,
            new_status=ComplaintStatus.REVIEWED_BY_BARANGAY.value if reviewer.role == UserRole.BARANGAY_OFFICIAL else ComplaintStatus.REVIEWED_BY_LGU.value,
            changed_by_user_id=responder_id,
            db=db
        )
        
        assign_barangay_members_task.delay(incident_id=incident_id, complaint_ids=complaint_ids, barangay_member_ids=response_data.barangay_member_ids)

        await db.commit()
        
        response = Response(
            incident_id=incident_id,
            responder_id=responder_id,
            actions_taken=response_data.actions_taken,
            response_date=datetime.now(timezone.utc),
        )
        db.add(response)
        await assign_barangay_members_to_response(db, response, response_data.barangay_member_ids)
        await db.commit()
        await db.refresh(response)

        if attachments:
            await enqueue_response_attachments(attachments, response.id, responder_id, incident_id)

        first_complaint = complaints[0] if complaints else None
        barangay_id = first_complaint.barangay_id if first_complaint else None
        
        user_ids = list({c.user_id for c in complaints})

        users_dict = await BatchLoader.fetch_users_by_ids(
            db,
            user_ids
        )

        push_tokens_dict = await BatchLoader.fetch_push_tokens_by_user_ids(
            db,
            user_ids
        )

        for complaint in complaints:
            complaint_user = users_dict.get(complaint.user_id)

            user_push_tokens = push_tokens_dict.get(complaint.user_id, [])

            logger.info(
                f"Fetched push tokens for user {complaint.user_id}: "
                f"{[token.token for token in user_push_tokens]}"
            )

            if complaint_user:
                for push_token in user_push_tokens:
                    send_push_notification_task.delay(
                        token=push_token.token,
                        enabled=complaint_user.push_notifications_enabled,
                        title=complaint.title,
                        body=f"Your complaint about '{complaint.title}' is now under review",
                        data={
                            "complaint_id": complaint.id,
                            "notification_type": "complaint_under_review",
                        },
                    )

                    logger.info(
                        f"Sent push notification for complaint {complaint.id} "
                        f"to user {complaint.user_id} with token {push_token.token}"
                    )

                logger.info(
                    f"Sending notification for complaint {complaint.id} "
                    f"to user {complaint.user_id}"
                )

                send_notifications_task.delay(
                    user_id=complaint.user_id,
                    title=complaint.title,
                    incident_id=incident_id,
                    message=f"Your complaint about '{complaint.title}' is now under review",
                    complaint_id=complaint.id,
                    notification_type="complaint_under_review",
                )
                
        await invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=[complaint.user_id for complaint in complaints],
            barangay_id=barangay_id,
            incident_ids=[incident_id],
            include_global=True
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "All complaints under this incident are now under review"}
        )

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


async def resolve_complaints_by_incident(response_data: ResponseCreateSchema, incident_id: int, responder_id: int, attachments: Optional[List[UploadFile]], db: AsyncSession):
    try:
        # Validate that attachments are provided
        if not attachments or len(attachments) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachments are required when resolving a complaint"
            )
        
        result = await db.execute(
            select(IncidentComplaintModel.complaint_id)
            .where(IncidentComplaintModel.incident_id == incident_id)
        )
        complaint_ids = result.scalars().all()
        result = await db.execute(select(User).where(User.id == responder_id))
        resolver = result.scalars().first()

        if not complaint_ids:
            return {"message": "No complaints found for this incident"}

        complaints = await db.execute(
            select(Complaint)
            .options(selectinload(Complaint.barangay_account).selectinload(BarangayAccount.user))
            .where(Complaint.id.in_(complaint_ids))
        )
        complaints = complaints.scalars().all()
        for complaint in complaints:
            if complaint.status in [ComplaintStatus.RESOLVED_BY_BARANGAY.value, ComplaintStatus.RESOLVED_BY_LGU.value]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This incident is already resolved"
                )
                
        await db.execute(
            update(IncidentModel)
            .where(IncidentModel.id == incident_id)
            .values(resolver_id=responder_id)
        )

        await db.execute(
            update(Complaint)
            .where(Complaint.id.in_(complaint_ids))
            .values(status=ComplaintStatus.RESOLVED_BY_BARANGAY.value if resolver.role in [UserRole.BARANGAY_OFFICIAL, UserRole.BARANGAY_MEMBER] else ComplaintStatus.RESOLVED_BY_LGU.value, resolved_at=datetime.now(timezone.utc))
        )
        
        await log_status_change(
            complaint_ids=complaint_ids,
            new_status=ComplaintStatus.RESOLVED_BY_BARANGAY.value if resolver.role in [UserRole.BARANGAY_OFFICIAL, UserRole.BARANGAY_MEMBER] else ComplaintStatus.RESOLVED_BY_LGU.value,
            changed_by_user_id=responder_id,
            db=db
        )

        response_barangay_member_ids = response_data.barangay_member_ids or []
        if resolver.role == UserRole.BARANGAY_MEMBER:
            assigned_members_result = await db.execute(
                select(incident_barangay_members.c.barangay_member_id).where(
                    incident_barangay_members.c.incident_id == incident_id
                )
            )
            response_barangay_member_ids = assigned_members_result.scalars().all()
        else:
            assign_barangay_members_task.delay(
                incident_id=incident_id,
                complaint_ids=complaint_ids,
                barangay_member_ids=response_barangay_member_ids,
            )
            
        await db.commit()
    
        response = Response(
            incident_id=incident_id,
            responder_id=responder_id,
            actions_taken=response_data.actions_taken,
            response_date=datetime.now(timezone.utc),
        )
        db.add(response)
        await assign_barangay_members_to_response(db, response, response_barangay_member_ids)
        await db.commit()
        await db.refresh(response)

        if attachments:
            await enqueue_response_attachments(attachments, response.id, responder_id, incident_id)

        first_complaint = complaints[0] if complaints else None
        barangay_id = first_complaint.barangay_id if first_complaint else None
        
        # Batch load all users to avoid N+1 queries
        user_ids = list({c.user_id for c in complaints})
        
        users_dict = await BatchLoader.fetch_users_by_ids(db, user_ids)
        
        user_push_tokens_dict = await BatchLoader.fetch_push_tokens_by_user_ids(db, user_ids)
        
        for complaint in complaints:
            complaint_user = users_dict.get(complaint.user_id)
            user_push_tokens = user_push_tokens_dict.get(complaint.user_id, [])
            
            logger.info(
                f"Fetched push tokens for user {complaint.user_id}: "
                f"{[token.token for token in user_push_tokens]}"
            )
            
            if complaint_user:
                
                for token in user_push_tokens:
                    send_push_notification_task.delay(
                        token=token.token,
                        enabled=complaint_user.push_notifications_enabled,
                        title=complaint.title,
                        body=f"Your complaint '{complaint.title}' has been resolved",
                        data={"complaint_id": complaint.id, "notification_type": "success"},
                    )
                    logger.info(
                        f"Sent push notification for complaint {complaint.id} "
                        f"to user {complaint.user_id} with token {token.token}"
                    )
                    
                logger.info(
                    f"Sending notification for complaint {complaint.id} "
                    f"to user {complaint.user_id}"
                )
                send_notifications_task.delay(
                    user_id=complaint.user_id,
                    title=complaint.title,
                    incident_id=incident_id,
                    message=f"Your complaint '{complaint.title}' has been resolved",
                    complaint_id=complaint.id,
                    notification_type="success"
                )
            

                
        await invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=[complaint.user_id for complaint in complaints],
            barangay_id=barangay_id,
            incident_ids=[incident_id],
            include_global=True
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "All complaints under this incident have been resolved"}
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    


async def reject_complaints_by_incident(incident_id: int, rejector_id: int, response_data: RejectComplaintSchema, attachments: Optional[List[UploadFile]], db: AsyncSession):
    try:
        # Validate that attachments are provided
        if not attachments or len(attachments) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachments are required when rejecting or forwarding a complaint"
            )
        
        result = await db.execute(
            select(IncidentComplaintModel.complaint_id)
            .where(IncidentComplaintModel.incident_id == incident_id)
        )
    
        complaint_ids = result.scalars().all()
        result = await db.execute(select(User).where(User.id == rejector_id))
        rejector = result.scalars().first()
        rejected_by = rejector.role.replace("_", " ").title()
        result = await db.execute(select(RejectionCategoryModel).where(RejectionCategoryModel.id == response_data.rejection_category_id))
        rejection_category = result.scalars().first()

        if not complaint_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No complaints found for this incident")
        
        complaints = await db.execute(
            select(Complaint)
            .options(
                selectinload(Complaint.user),
                selectinload(Complaint.barangay_account).selectinload(BarangayAccount.user)
                )
            .where(Complaint.id.in_(complaint_ids))
        )
        complaints = complaints.scalars().all()
        complaint_snapshots = [
            {
                "id": complaint.id,
                "user_id": complaint.user_id,
                "title": complaint.title,
                "barangay_id": complaint.barangay_id,
            }
            for complaint in complaints
        ]
        
        
        if rejector.role == UserRole.LGU_OFFICIAL:
            notification_type = "rejected_by_lgu"
        else:
           notification_type = "rejected_by_barangay"
        
        if rejector.role == UserRole.LGU_OFFICIAL:
            await db.execute(
                update(Complaint)
                .where(Complaint.id.in_(complaint_ids))
                .values(is_rejected_by_lgu=True, status=ComplaintStatus.SUBMITTED.value)
            )
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.SUBMITTED.value,
                changed_by_user_id=rejector_id,
                db=db
            )
            send_notifications_task.delay(
                user_id=complaints[0].barangay_account.user_id if complaints and complaints[0].barangay_account and complaints[0].barangay_account.user_id else None,
                title="The LGU has rejected the complaints under this incident",
                message=f"The LGU has rejected the complaints under the incident you forwarded '{complaints[0].title if complaints else 'N/A'}'.",
                incident_id=incident_id,
                complaint_id=complaints[0].id if complaints else None,
                notification_type=notification_type,
                event="reject"
            )
            payload = {
                "title": "The LGU has rejected the complaints under this incident",
                "body": f"The LGU has rejected the complaints under the incident you forwarded '{complaints[0].title if complaints else 'N/A'}'.",
                "icon": "https://cfms-stamaria.com/StaMariaLogo.jpg",
                "url": f"https://cfms-stamaria.com/dashboard/incidents/{incident_id}"
            }
            send_web_push_notification_task.delay(
                user_id=complaints[0].barangay_account.user_id if complaints and complaints[0].barangay_account and complaints[0].barangay_account.user_id else None,
                payload=payload
            )
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.FORWARDED_TO_LGU.value,
                changed_by_user_id=rejector_id,
                db=db
            )
            lgu = await db.execute(
                select(User).where(User.role == UserRole.LGU_OFFICIAL)
                )
            lgu = lgu.scalars().first()
            logger.info(f"LGU user found for notification: {lgu.id if lgu else 'No LGU user found'}")
            
        else:
            await db.execute(
                update(Complaint)
                .where(Complaint.id.in_(complaint_ids))
                .values(status=ComplaintStatus.REJECTED.value, rejection_category_id=response_data.rejection_category_id)
            )
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.REJECTED.value,
                changed_by_user_id=rejector_id,
                db=db
            )

        assign_barangay_members_task.delay(incident_id=incident_id, complaint_ids=complaint_ids, barangay_member_ids=response_data.barangay_member_ids)
        
        response = Response(
            incident_id=incident_id,
            responder_id=rejector_id,
            actions_taken=response_data.actions_taken,
            response_date=datetime.now(timezone.utc),
        )
        db.add(response)
        await assign_barangay_members_to_response(db, response, response_data.barangay_member_ids)
        await db.commit()
        await db.refresh(response)

        if attachments:
            await enqueue_response_attachments(attachments, response.id, rejector_id, incident_id)
        
        first_complaint = complaint_snapshots[0] if complaint_snapshots else None
        barangay_id = first_complaint["barangay_id"] if first_complaint else None
            
        # Batch load all users to avoid N+1 queries
        user_ids = list({c["user_id"] for c in complaint_snapshots})
        users_dict = await BatchLoader.fetch_users_by_ids(db, user_ids)
        user_push_tokens_dict = await BatchLoader.fetch_push_tokens_by_user_ids(db, user_ids)
        complaint_ids = [c["id"] for c in complaint_snapshots]
        user_complaint_counts = Counter(user_ids)

        reject_counters = {}
        if rejection_category.name in [RejectionCategoryEnum.SPAM.value, RejectionCategoryEnum.FALSE_REPORT.value]:
            await RejectCounterHelper.increment_reject_counter(db, user_ids)
            reject_counters = await RejectCounterHelper.get_reject_counters(db, user_ids)

        restricted_users = set()
        
        for complaint in complaint_snapshots:
            complaint_user = users_dict.get(complaint["user_id"])
            user_push_tokens = user_push_tokens_dict.get(complaint["user_id"], [])
            if complaint_user:
                if rejector.role == UserRole.BARANGAY_OFFICIAL:
                    current_reject_counter = reject_counters.get(complaint["user_id"], 0)

                    if current_reject_counter == 1:
                        message = (
                            f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by} "
                            "and has been marked as invalid or inappropriate. Please ensure that your complaint "
                            "adheres to the guidelines to avoid further rejections. Repeated rejections may lead to suspension of your account."
                        )

                    elif current_reject_counter == 2:
                        message = (
                            f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by} "
                            "for the second time and has been marked as invalid or inappropriate. This is the last warning. "
                            "Please ensure that your complaints adhere to the guidelines to avoid further rejections."
                        )

                    elif current_reject_counter >= 3:
                        message = (
                            f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by} "
                            "for the third time and has been marked as invalid or inappropriate. "
                            "Your account is now suspended due to repeated violations. Please contact support."
                        )

                    else:
                        message = None

                    if message:
                        send_notifications_task.delay(
                            user_id=complaint["user_id"],
                            title=complaint["title"],
                            message=message,
                            complaint_id=complaint["id"],
                            incident_id=incident_id,
                            notification_type=notification_type
                        )
                        
                    if current_reject_counter >= 3:
                        restricted_users.add(complaint["user_id"])
                        
                for token in user_push_tokens:
                    logger.info(
                        f"Sending push notification for complaint {complaint['id']} to user {complaint['user_id']} with token {token.token}"
                    )
                    send_push_notification_task.delay(
                        token=token.token,
                        enabled=complaint_user.push_notifications_enabled,
                        title=complaint["title"],
                        body=f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by}.",
                        data={"complaint_id": complaint["id"], "notification_type": notification_type},
                    )

        if (
            rejector.role != UserRole.BARANGAY_OFFICIAL
            and rejection_category.name in [RejectionCategoryEnum.SPAM.value, RejectionCategoryEnum.FALSE_REPORT.value]
        ):
            for user_id, current_reject_counter in reject_counters.items():
                if current_reject_counter >= 3:
                    restricted_users.add(user_id)

        if (
            rejector.role == UserRole.BARANGAY_OFFICIAL
            and rejection_category.name in [RejectionCategoryEnum.SPAM.value, RejectionCategoryEnum.FALSE_REPORT.value]
        ):
            notified_users = set()
            for complaint in complaint_snapshots:
                user_id = complaint["user_id"]
                if user_id in notified_users:
                    continue

                current_reject_counter = reject_counters.get(user_id, 0)
                increment_in_batch = user_complaint_counts.get(user_id, 0)
                previous_reject_counter = max(0, current_reject_counter - increment_in_batch)

                if previous_reject_counter < 1 <= current_reject_counter:
                    message = (
                        f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by} "
                        "and has been marked as invalid or inappropriate. Please ensure that your complaint "
                        "adheres to the guidelines to avoid further rejections. Repeated rejections may lead to suspension of your account."
                    )
                elif previous_reject_counter < 2 <= current_reject_counter:
                    message = (
                        f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by} "
                        "for the second time and has been marked as invalid or inappropriate. This is the last warning. "
                        "Please ensure that your complaints adhere to the guidelines to avoid further rejections."
                    )
                elif previous_reject_counter < 3 <= current_reject_counter:
                    message = (
                        f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by} "
                        "for the third time and has been marked as invalid or inappropriate. "
                        "Your account is now suspended due to repeated violations. Please contact support."
                    )
                else:
                    message = None

                if message:
                    send_notifications_task.delay(
                        user_id=user_id,
                        title=complaint["title"],
                        message=message,
                        complaint_id=complaint["id"],
                        incident_id=incident_id,
                        notification_type=notification_type,
                    )
                notified_users.add(user_id)

        if restricted_users:
            await RestrictSubmissionHelper.restrict_user_submissions(db, list(restricted_users))

        await invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=[complaint["user_id"] for complaint in complaint_snapshots],
            barangay_id=barangay_id,
            incident_ids=[incident_id],
            include_global=True
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "All complaints under this incident have been rejected"}
        )
        
    except HTTPException:
        raise
        
    
    except Exception as e:
        logger.exception(
            "Error in reject_complaints_by_incident",
            extra={
                "incident_id": incident_id,
                "rejector_id": rejector_id,
                "complaint_ids": complaint_ids if "complaint_ids" in locals() else None,
            },
        )
        await db.rollback()
        logger.error(f"Error in reject_complaints_by_incident: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))



async def reject_incident(incident_id: int, rejector_id: int, response_data: ResponseCreateSchema, attachments: Optional[List[UploadFile]], db: AsyncSession):
    try:
        if not attachments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachments are required when rejecting an incident",
            )

        result = await db.execute(
            select(IncidentComplaintModel.complaint_id)
            .where(IncidentComplaintModel.incident_id == incident_id)
        )
    
        complaint_ids = result.scalars().all()
        result = await db.execute(select(User).where(User.id == rejector_id))
        rejector = result.scalars().first()
        rejected_by = rejector.role.replace("_", " ").title()

        if not complaint_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No complaints found for this incident")
        
        complaints = await db.execute(
            select(Complaint)
            .options(
                selectinload(Complaint.user),
                selectinload(Complaint.barangay_account).selectinload(BarangayAccount.user)
                )
            .where(Complaint.id.in_(complaint_ids))
        )
        complaints = complaints.scalars().all()
        complaint_snapshots = [
            {
                "id": complaint.id,
                "user_id": complaint.user_id,
                "title": complaint.title,
                "barangay_id": complaint.barangay_id,
            }
            for complaint in complaints
        ]
        
        
        if rejector.role == UserRole.LGU_OFFICIAL:
            notification_type = "rejected_by_lgu"
        else:
           notification_type = "rejected_by_barangay"
        
        if rejector.role in [UserRole.LGU_OFFICIAL]:

            for complaint in complaints:
                if complaint.is_rejected_by_lgu:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This incident has already been rejected by the LGU")

        if rejector.role == UserRole.LGU_OFFICIAL:
            await db.execute(
                update(Complaint)
                .where(Complaint.id.in_(complaint_ids))
                .values(is_rejected_by_lgu=True, status=ComplaintStatus.REVIEWED_BY_BARANGAY.value)
            )
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.REVIEWED_BY_BARANGAY.value,
                changed_by_user_id=rejector_id,
                db=db
            )
            send_notifications_task.delay(
                user_id=complaints[0].barangay_account.user_id if complaints and complaints[0].barangay_account and complaints[0].barangay_account.user_id else None,
                title="The LGU has rejected the complaints under this incident",
                message=f"The LGU has rejected the complaints under the incident you forwarded '{complaints[0].title if complaints else 'N/A'}'.",
                incident_id=incident_id,
                complaint_id=complaints[0].id if complaints else None,
                notification_type=notification_type,
                event="reject"
            )
            payload = {
                "title": "The LGU has rejected the complaints under this incident",
                "body": f"The LGU has rejected the complaints under the incident you forwarded '{complaints[0].title if complaints else 'N/A'}'.",
                "icon": "https://cfms-stamaria.com/StaMariaLogo.jpg",
                "url": f"https://cfms-stamaria.com/dashboard/incidents/{incident_id}"
            }
            send_web_push_notification_task.delay(
                user_id=complaints[0].barangay_account.user_id if complaints and complaints[0].barangay_account and complaints[0].barangay_account.user_id else None,
                payload=payload
            )
            
        else:
            await db.execute(
                update(Complaint)
                .where(Complaint.id.in_(complaint_ids))
                .values(status=ComplaintStatus.REJECTED.value)
            )
            await log_status_change(
                complaint_ids=complaint_ids,
                new_status=ComplaintStatus.REJECTED.value,
                changed_by_user_id=rejector_id,
                db=db
            )
        
        response = Response(
            incident_id=incident_id,
            responder_id=rejector_id,
            actions_taken=response_data.actions_taken,
            response_date=datetime.now(timezone.utc),
        )
        db.add(response)
        await assign_barangay_members_to_response(db, response, response_data.barangay_member_ids)
        await db.commit()
        await db.refresh(response)

        if attachments:
            await enqueue_response_attachments(attachments, response.id, rejector_id, incident_id)
        
        first_complaint = complaint_snapshots[0] if complaint_snapshots else None
        barangay_id = first_complaint["barangay_id"] if first_complaint else None
            
        # Batch load all users to avoid N+1 queries
        user_ids = list({c["user_id"] for c in complaint_snapshots})
        users_dict = await BatchLoader.fetch_users_by_ids(db, user_ids)
        user_push_tokens_dict = await BatchLoader.fetch_push_tokens_by_user_ids(db, user_ids)
        complaint_ids = [c["id"] for c in complaint_snapshots]
        
                
        for complaint in complaint_snapshots:
            complaint_user = users_dict.get(complaint["user_id"])
            user_push_tokens = user_push_tokens_dict.get(complaint["user_id"], [])
            if complaint_user:
                for token in user_push_tokens:
                    send_push_notification_task.delay(
                        token=token.token,
                        enabled=complaint_user.push_notifications_enabled,
                        title=complaint["title"],
                        body=f"Your complaint '{complaint['title']}' has been rejected by the {rejected_by}.",
                        data={"complaint_id": complaint["id"], "notification_type": notification_type},
                    )

        await invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=[complaint["user_id"] for complaint in complaint_snapshots],
            barangay_id=barangay_id,
            incident_ids=[incident_id],
            include_global=True
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "All complaints under this incident have been rejected"}
        )
        
    except HTTPException:
        raise
        
    
    except Exception as e:
        logger.exception(
            "Error in reject_complaints_by_incident",
            extra={
                "incident_id": incident_id,
                "rejector_id": rejector_id,
                "complaint_ids": complaint_ids if "complaint_ids" in locals() else None,
            },
        )
        await db.rollback()
        logger.error(f"Error in reject_complaints_by_incident: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    
   
async def forward_incident_to_lgu(response_data: ResponseCreateSchema, incident_id: int, responder_id: int, attachments: Optional[List[UploadFile]], db: AsyncSession):
    try:
        if not attachments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachments are required when escalating an incident",
            )

        incident_result = await db.execute(select(IncidentModel).where(IncidentModel.id == incident_id))
        incident = incident_result.scalars().first()
        
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        
        
        barangay_id = incident.barangay_id
        
        result = await db.execute(select(IncidentComplaintModel.complaint_id).where(IncidentComplaintModel.incident_id == incident_id))
        
        complaint_ids = result.scalars().all()
        
        if not complaint_ids:
            return {"message": "No complaints found for this incident"}
        
        result = await db.execute(select(Complaint).where(Complaint.id.in_(complaint_ids)))
        complaints = result.scalars().all()
        
        if complaints[0].is_rejected_by_lgu:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot forward incident. You cannot forward an incident that has been rejected by the LGU.")
        
        await db.execute(
            update(Complaint)   
            .where(Complaint.id.in_(complaint_ids))
            .values(
                status=ComplaintStatus.FORWARDED_TO_LGU.value,
                forwarded_at=datetime.now(timezone.utc),
                is_rejected_by_lgu=False
            )
        )
        
        await log_status_change(
            complaint_ids=complaint_ids,
            new_status=ComplaintStatus.FORWARDED_TO_LGU.value,
            changed_by_user_id=responder_id,
            db=db
        )
        logger.info(f"Updated {len(complaint_ids)} complaints to FORWARDED_TO_LGU status for incident ID: {incident_id}")
        incident.new_complaint_count = len(complaint_ids)
        incident.has_new_complaints = True
        incident.updated_at = datetime.now(timezone.utc)
        if incident.hearing_date:
            incident.hearing_date = None
        await db.commit()
        
        # OPTIMIZED: Batch fetch all complaints at once instead of in loop
        complaints_dict = await BatchLoader.fetch_complaints_by_ids(db, complaint_ids, minimal=True)
        
        # Send notifications using cached complaints
        for complaint_id in complaint_ids:
            complaint = complaints_dict.get(complaint_id)
            if complaint:
                send_notifications_task.delay(
                    user_id=complaint.user_id,
                    title="Complaint Forwarded to LGU",
                    incident_id=incident_id,
                    message="Your complaint has been forwarded to the LGU for further processing.",
                    complaint_id=complaint.id,
                    notification_type="update",
                    event="info"
                )
                
        response = Response(
            incident_id=incident_id,
            responder_id=responder_id,
            actions_taken=response_data.actions_taken,
            response_date=datetime.now(timezone.utc),
        )
        db.add(response)
        await db.commit()
        await db.refresh(response)

        if attachments:
            await enqueue_response_attachments(attachments, response.id, responder_id, incident_id)
        
        result = await db.execute(
            select(User).options(selectinload(User.push_subscriptions)).where(User.role == "lgu_official")
        )
        lgu_officials = result.scalars().all()

        for official in lgu_officials:
            send_notifications_task.delay(
                user_id=official.id,
                title="New Incident Forwarded to LGU",
                message=f"A new incident with ID {incident.id} has been forwarded to the LGU.",
                complaint_id=None,
                incident_id=incident_id,
                notification_type="info",
                event="info"
            )

            payload = {
                "title": "New Incident Forwarded to LGU",
                "body": f"A new incident with ID {incident.id} has been forwarded to the LGU.",
                "icon": "https://cfms-stamaria.com/StaMariaLogo.jpg",
                "url": f"https://cfms-stamaria.com/lgu/incidents/{incident.id}"
            }

            send_web_push_notification_task.delay(
                user_id=official.id,
                payload=payload
            )

            incident.lgu_account_id = official.id

        await db.commit()
            
        # OPTIMIZED: Use new CacheInvalidator with pipeline
        await CacheInvalidator.invalidate_cache(
            complaint_ids=complaint_ids,
            user_ids=await BatchLoader.fetch_user_ids_for_complaints(db, complaint_ids),
            barangay_id=barangay_id,
            incident_ids=[incident_id],
            include_global=True
        )
            
            
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "All complaints under this incident have been forwarded to LGU"}
        )
        
    except HTTPException:
        raise
    
    except Exception:
        await db.rollback()
        logger.exception("Error in forward_incident_to_lgu")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    

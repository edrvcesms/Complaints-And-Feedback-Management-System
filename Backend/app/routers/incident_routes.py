from typing import List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from datetime import datetime
from sqlalchemy import select
from app.dependencies.rate_limiter import limiter
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.incidents_services import get_incidents_by_barangay, get_incident_by_id, mark_incident_as_viewed, get_all_incidents, get_assigned_incidents_for_barangay_member, mark_incident_as_unresolvable
from app.dependencies.auth_dependency import get_current_user
from app.services.complaint_services import get_complaints_by_incident
from app.services.hearing_services import notify_user_for_hearing, mark_hearing_as_successful, reschedule_hearing
from app.services.hearing_services import get_scheduled_hearings
from app.services.complaint_actions_services import resolve_complaints_by_incident, review_complaints_by_incident, reject_complaints_by_incident, reject_incident, forward_incident_to_lgu
from app.dependencies.db_dependency import get_async_db
from app.constants.roles import UserRole
from app.schemas.response_schema import ResponseCreateSchema, RejectComplaintSchema
from app.models.user import User
from app.models.incident_model import incident_barangay_members
from app.schemas.hearing_schema import RespondentsModel
from app.utils.logger import logger
from app.core.pagination_params import IncidentListParams, ListParams, PaginationParams

router = APIRouter()


def parse_response_data(
    response_data: Optional[str],
    actions_taken: Optional[str],
    is_marked_as_spam: bool = False,
) -> ResponseCreateSchema:
    response_text = response_data.strip() if response_data else ""
    if response_text:
        try:
            payload = ResponseCreateSchema.model_validate_json(response_text)
            return payload.model_copy(update={"is_marked_as_spam": is_marked_as_spam})
        except Exception:
            try:
                payload = ResponseCreateSchema.model_validate(json.loads(response_text))
                return payload.model_copy(update={"is_marked_as_spam": is_marked_as_spam})
            except Exception:
                return ResponseCreateSchema(
                    actions_taken=response_text,
                    is_marked_as_spam=is_marked_as_spam,
                )

    actions_text = actions_taken.strip() if actions_taken else ""
    if actions_text:
        return ResponseCreateSchema(
            actions_taken=actions_text,
            is_marked_as_spam=is_marked_as_spam,
        )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Missing response data.",
    )


async def verify_member_incident_assignment(incident_id: int, current_user: User, db: AsyncSession) -> None:
    if current_user.role != UserRole.BARANGAY_MEMBER:
        return
    if not current_user.barangay_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Barangay member account is required.")
    assigned = await db.execute(
        select(incident_barangay_members.c.incident_id).where(
            incident_barangay_members.c.incident_id == incident_id,
            incident_barangay_members.c.barangay_member_id == current_user.barangay_member.id,
        )
    )
    if assigned.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")

@router.get("/", status_code=status.HTTP_200_OK)
async def get_incidents(params: IncidentListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    
    return await get_incidents_by_barangay(current_user.barangay_account.barangay_id, db, params)

@router.get("/archive", status_code=status.HTTP_200_OK)
async def get_all_incidents_endpoint(params: IncidentListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")

    return await get_all_incidents(current_user, db, params)

@router.get("/assigned", status_code=status.HTTP_200_OK)
async def get_assigned_incidents_endpoint(params: IncidentListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.BARANGAY_MEMBER or not current_user.barangay_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assigned incidents are only available to barangay members.")
    return await get_assigned_incidents_for_barangay_member(current_user.barangay_member.id, db, params)

@router.get("/scheduled-hearings", status_code=status.HTTP_200_OK)
async def get_scheduled_hearings_endpoint(
    params: ListParams = Depends(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.BARANGAY_OFFICIAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scheduled hearings are only available to barangay officials.",
        )
    if not current_user.barangay_account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Barangay account is required.")

    return await get_scheduled_hearings(
        db,
        params,
        current_user.barangay_account.barangay_id,
    )

@router.get("/{incident_id}", status_code=status.HTTP_200_OK)
async def get_incident(incident_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.BARANGAY_MEMBER, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")

    await verify_member_incident_assignment(incident_id, current_user, db)
    
    return await get_incident_by_id(incident_id, db)
    
@router.get("/{incident_id}/complaints", status_code=status.HTTP_200_OK)
async def get_incident_complaints(incident_id: int, params: PaginationParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.BARANGAY_MEMBER, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")

    await verify_member_incident_assignment(incident_id, current_user, db)
    
    return await get_complaints_by_incident(incident_id, db, params)

@router.patch("/{incident_id}/resolve", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def resolve_incident_complaints(
    request: Request,
    incident_id: int,
    response_data: Optional[str] = Form(None),
    actions_taken: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.BARANGAY_MEMBER, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")

    if current_user.role == UserRole.BARANGAY_MEMBER:
        await verify_member_incident_assignment(incident_id, current_user, db)
    
    response_payload = parse_response_data(response_data, actions_taken)
    return await resolve_complaints_by_incident(response_payload, incident_id, current_user.id, attachments=attachments, db=db)


@router.patch("/{incident_id}/unresolvable", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def mark_incident_unresolvable(
    request: Request,
    incident_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.BARANGAY_MEMBER or not current_user.barangay_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only assigned barangay members may mark an incident as unresolvable.")

    return await mark_incident_as_unresolvable(
        incident_id,
        db,
        barangay_member_id=current_user.barangay_member.id,
    )

@router.patch("/{incident_id}/review", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def review_incident_complaints(
    request: Request,
    incident_id: int,
    response_data: Optional[str] = Form(None),
    actions_taken: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    
    response_payload = parse_response_data(response_data, actions_taken)
    return await review_complaints_by_incident(response_payload, incident_id, current_user.id, attachments=attachments, db=db)

@router.patch("/{incident_id}/reject", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def reject_incident_complaints(
    request: Request,
    incident_id: int,
    response_data: Optional[str] = Form(None),
    actions_taken: Optional[str] = Form(None),
    rejection_category_id: int = Form(...),
    attachments: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    
    if current_user.role not in [UserRole.LGU_OFFICIAL, UserRole.BARANGAY_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    
    parsed_response = parse_response_data(response_data, actions_taken)
    response_payload = RejectComplaintSchema(
        actions_taken=parsed_response.actions_taken,
        rejection_category_id=rejection_category_id,
        barangay_member_ids=parsed_response.barangay_member_ids,
    )
    return await reject_complaints_by_incident(incident_id, current_user.id, response_payload, attachments=attachments, db=db)

@router.patch("/{incident_id}/reject-incident", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def reject_entire_incident(
    request: Request,
    incident_id: int,
    actions_taken: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    
    response_payload = ResponseCreateSchema(
        actions_taken=actions_taken.strip() if actions_taken else "",
    )
    return await reject_incident(incident_id, current_user.id, response_payload, attachments=attachments, db=db)

@router.patch("/{incident_id}/forward/lgu", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def forward_incident_lgu(
    request: Request,
    incident_id: int,
    response_data: Optional[str] = Form(None),
    actions_taken: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    
    if current_user.role != UserRole.BARANGAY_OFFICIAL:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    
    response_payload = parse_response_data(response_data, actions_taken)
    return await forward_incident_to_lgu(response_payload, incident_id, current_user.id, attachments=attachments, db=db)

@router.post("/{incident_id}/mark-viewed", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def mark_incident_viewed(request: Request, incident_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    
    return await mark_incident_as_viewed(current_user.id, incident_id, db)

@router.post("/notify-hearing/{incident_id}", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def notify_hearing(request: Request, incident_id: int, hearing_date: datetime = Form(...), respondents: str = Form("[]"), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    try:
        respondent_payload = json.loads(respondents)
        if not isinstance(respondent_payload, list):
            raise ValueError("Respondents must be a list")
        parsed_respondents = [RespondentsModel.model_validate(item) for item in respondent_payload]
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid respondents payload") from error

    return await notify_user_for_hearing(incident_id, hearing_date, current_user.id, parsed_respondents, db)


@router.post("/mark-hearing/{incident_id}", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def mark_hearing(request: Request, incident_id: int, is_successful: bool = Form(...), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    return await mark_hearing_as_successful(incident_id, is_successful, current_user.id, db)


@router.post("/reschedule-hearing/{incident_id}", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def reschedule_hearing_route(request: Request, incident_id: int, hearing_date: datetime = Form(...), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
        logger.warning(f"Unauthorized access attempt by user ID: {current_user.id} with role: {current_user.role}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    return await reschedule_hearing(incident_id, hearing_date, current_user.id, db)

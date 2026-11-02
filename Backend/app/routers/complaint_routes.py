from datetime import datetime
from fastapi import APIRouter, Depends, status, Form, UploadFile, File
from typing import List
from app.dependencies.db_dependency import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.complaint_schema import ComplaintCreateData
from app.dependencies.rate_limiter import limiter
from app.services.complaint_services import submit_complaint, get_my_complaints, get_all_complaints, get_complaint_by_id, get_geometric_location_details
from app.services.complaint_stats_services import get_complaint_summary, get_weekly_stats, get_monthly_stats, get_yearly_stats, user_complaints_statistics
from app.dependencies.auth_dependency import get_current_user
from app.services.attachment_services import upload_attachments
from app.utils.attachments import validate_upload_files
from app.models.user import User
from fastapi.requests import Request
from app.core.pagination_params import ListParams, IncidentListParams

router = APIRouter()

@router.get("/all", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def list_all_complaints(request: Request, params: ListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    return await get_all_complaints(db, params, barangay_id=current_user.barangay_account.barangay_id)

@router.get("/summary", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def complaint_summary(request: Request, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_complaint_summary(current_user.barangay_account.barangay_id, db)

@router.get("/weekly", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def weekly_complaint_stats(request: Request, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_weekly_stats(current_user.barangay_account.barangay_id, db)


@router.get("/location-details", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_location_details(request: Request, latitude: float, longitude: float, barangay_name: str, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_geometric_location_details(latitude, longitude, barangay_name)


@router.get("/monthly/{year}/{month}", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def monthly_complaint_stats(request: Request, year: int, month: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_monthly_stats(current_user.barangay_account.barangay_id, year, month, db)

@router.get("/yearly/{year}", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def yearly_complaint_stats(request: Request, year: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_yearly_stats(current_user.barangay_account.barangay_id, year, db)

@router.get("/my-complaints", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def list_my_complaints(request: Request, params: IncidentListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_my_complaints(current_user.id, params, db)

@router.get("/my-stats", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def my_complaint_stats(request: Request, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await user_complaints_statistics(current_user.id, db)

@router.get("/{complaint_id}", status_code=status.HTTP_200_OK)
@limiter.limit("50/minute")
async def get_complaint(request: Request, complaint_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_complaint_by_id(complaint_id, db)
    
@router.post("/submit-complaint", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_complaint(request: Request, data: str = Form(...), attachments: List[UploadFile] = File(default=[]), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    complaint_data = ComplaintCreateData.parse_raw(data)
    if attachments:
        await validate_upload_files(attachments)

    complaint = await submit_complaint(complaint_data, current_user.id, db)
    if attachments:
        await upload_attachments(attachments, current_user.id, complaint.id, db)
#await cluster_complaints(complaint_data, current_user.id, complaint.id, db)
    return {"message": "Complaint submitted successfully", "complaint_id": complaint.id}


    
@router.post("/submit-complaints", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_complaint(request: Request, user_id: int,data: str = Form(...), attachments: List[UploadFile] = File(default=[]), db: AsyncSession = Depends(get_async_db)):
    complaint_data = ComplaintCreateData.parse_raw(data)
    if attachments:
        await validate_upload_files(attachments)

    complaint = await submit_complaint(complaint_data, user_id=user_id, db=db)
    if attachments:
        await upload_attachments(attachments, user_id, complaint.id, db)
#await cluster_complaints(complaint_data, user_id, complaint.id, db)
    return {"message": "Complaint submitted successfully", "complaint_id": complaint.id}

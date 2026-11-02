from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.lgu_services import get_forwarded_incidents_by_barangay, get_all_forwarded_incidents, weekly_forwarded_incidents_stats, complaint_counts_by_barangay_category, monthly_forwarded_incidents_stats, yearly_forwarded_incidents_stats
from app.services.case_referral_services import create_case_referral, generate_referral_letter, get_active_departments, get_case_referral_by_id, get_case_referrals_for_complaint, get_department_by_id, update_case_referral
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.db_dependency import get_async_db
from app.models.user import User
from app.core.pagination_params import IncidentListParams
from app.constants.roles import UserRole
from app.schemas.case_referral_schema import CaseReferralCreate

router = APIRouter()


@router.get("/departments/active", status_code=status.HTTP_200_OK)
async def get_active_departments_route(db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access department data.")
    return await get_active_departments(db)


@router.get("/departments/{department_id}", status_code=status.HTTP_200_OK)
async def get_department_by_id_route(department_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access department data.")
    return await get_department_by_id(department_id, db)


@router.get("/complaints/{complaint_id}/referrals", status_code=status.HTTP_200_OK)
async def get_complaint_referrals_route(complaint_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access referral data.")
    return await get_case_referrals_for_complaint(complaint_id, db)


@router.get("/referrals/{referral_id}", status_code=status.HTTP_200_OK)
async def get_referral_route(referral_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access referral records.")
    return await get_case_referral_by_id(referral_id, db)


@router.post("/complaints/{complaint_id}/referrals", status_code=status.HTTP_201_CREATED)
async def create_referral_route(complaint_id: int, payload: CaseReferralCreate, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to create referral records.")
    if payload.complaint_id != complaint_id:
        payload.complaint_id = complaint_id
    return await create_case_referral(payload, db)


@router.patch("/referrals/{referral_id}", status_code=status.HTTP_200_OK)
async def update_referral_route(referral_id: int, payload: dict, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to update referral records.")
    return await update_case_referral(referral_id, payload, db)


@router.get("/referrals/{referral_id}/document", status_code=status.HTTP_200_OK)
async def generate_referral_document_route(referral_id: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN, UserRole.BARANGAY_OFFICIAL}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to download referral documents.")
    return await generate_referral_letter(referral_id, current_user, db)


@router.get("/forwarded-incidents", status_code=status.HTTP_200_OK)
async def get_all_forwarded_incidents_route(params: IncidentListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    return await get_all_forwarded_incidents(db, params)

@router.get("/forwarded-incidents/{barangay_id}", status_code=status.HTTP_200_OK)
async def get_forwarded_incidents_route(barangay_id: int, params: IncidentListParams = Depends(), db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    return await get_forwarded_incidents_by_barangay(barangay_id, db, params)

@router.get("/stats/weekly-forwarded-incidents", status_code=status.HTTP_200_OK)
async def weekly_forwarded_incidents_stats_route(db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    
    return await weekly_forwarded_incidents_stats(db)

@router.get("/stats/monthly-forwarded-incidents", status_code=status.HTTP_200_OK)
async def monthly_forwarded_incidents_stats_route(year: int, month: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await monthly_forwarded_incidents_stats(year, month, db)

@router.get("/stats/yearly-forwarded-incidents", status_code=status.HTTP_200_OK)
async def yearly_forwarded_incidents_stats_route(year: int, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await yearly_forwarded_incidents_stats(year, db)

@router.get("/stats/complaints-by-barangay-category", status_code=status.HTTP_200_OK)
async def complaints_by_barangay_category_stats_route(db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await complaint_counts_by_barangay_category(db)

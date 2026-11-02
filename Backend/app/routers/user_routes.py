from fastapi import APIRouter, Depends, Request, status
from app.dependencies.rate_limiter import limiter
from app.dependencies.db_dependency import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.user_services import request_reset_password, request_change_password, save_push_token, set_push_notifications, verify_otp_reset_password, change_password, get_user_by_id, update_user_location, forgot_password, create_new_password, delete_account, verify_delete_account_otp
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_schema import OTPData, ResetPasswordData, UserLocationData, UserPersonalData, VerifyEmailData, ChangePasswordData
from app.schemas.push_token_schema import PushNotificationRequest, SavePushTokenRequest
router = APIRouter()

@router.get("/profile", status_code=status.HTTP_200_OK)
async def get_profile(request: Request, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await get_user_by_id(current_user.id, db)

@router.post("/request-reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def request_reset_password_endpoint(request: Request, email_data: VerifyEmailData, db: AsyncSession = Depends(get_async_db)):
    return await request_reset_password(email_data, db)

@router.post("/request-change-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def request_change_password_endpoint(request: Request, current_user: User = Depends(get_current_user)):
    return await request_change_password(current_user)

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def forgot_password_endpoint(request: Request, email_data: VerifyEmailData, db: AsyncSession = Depends(get_async_db)):
    return await forgot_password(email_data, db)

@router.post("/create-new-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def create_new_password_endpoint(request: Request, password_data: ResetPasswordData, db: AsyncSession = Depends(get_async_db)):
    return await create_new_password(password_data, db)

@router.post("/verify-reset-password-otp", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def verify_password_reset_otp (request: Request, otp_data: OTPData, db: AsyncSession = Depends(get_async_db)):
    return await verify_otp_reset_password(otp_data, db)
    
@router.post("/change-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def reset_password(request: Request, password_data: ChangePasswordData, db: AsyncSession = Depends(get_async_db)):
    return await change_password(password_data, db)

@router.put("/update-current-location", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def update_current_location(request: Request, location_data: UserLocationData, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    return await update_user_location(current_user.id, location_data, db)


@router.post("/push-token", status_code=200)
async def save_token(
    request: Request,
    payload: SavePushTokenRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):

     return await save_push_token(db=db, user_id=current_user.id, token=payload.token)
 


@router.post("/enable-push-notifications", status_code=200)
async def enable_push_notifications(
    request: Request,
    body: PushNotificationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    return await set_push_notifications(db=db, user_id=current_user.id, enabled=body.enabled)
    

@router.delete("/delete-account", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def delete_account_endpoint(request: Request, email: str, db: AsyncSession = Depends(get_async_db)):
    return await delete_account(email, db)

@router.post("/verify-delete-account-otp", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def verify_delete_account_otp_endpoint(request: Request, otp_data: OTPData, db: AsyncSession = Depends(get_async_db)):
    return await verify_delete_account_otp(otp_data.email, otp_data.otp, db)
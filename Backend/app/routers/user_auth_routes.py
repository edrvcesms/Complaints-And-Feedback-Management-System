from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile
from app.dependencies.rate_limiter import limiter, rate_limit_exceeded_handler
from app.dependencies.db_dependency import   get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_auth_schema import ClerkLoginRequest, LoginData, UserLoginData, LoginResponse, RegisterData, OTPVerificationData, ResendOtpData
from app.services.user_auth_services import login_with_google, logout_user, register_user, resend_device_verification_otp, verify_otp_and_register, login_user, refresh_access_token, officials_login, barangay_member_mobile_login, superadmin_login, resend_otp_code, upload_id_images, verify_device_otp, logout_resident
from slowapi.errors import RateLimitExceeded
from app.utils.turnstile import verify_turnstile
from fastapi.requests import Request
import json
from app.schemas.user_auth_schema import DeviceInfo
router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(request: Request, user_data: RegisterData, db: AsyncSession = Depends(get_async_db)):
    return await register_user(user_data, db)

@router.post("/verify-otp", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_otp(request: Request, data: str = Form(...), front_id: UploadFile = None, back_id: UploadFile = None,selfie_with_id: UploadFile = None, db: AsyncSession = Depends(get_async_db)):
    parsed_data = json.loads(data)
    otp_data = OTPVerificationData(**parsed_data)
    return await verify_otp_and_register(otp_data.otp, otp_data, front_id, back_id, selfie_with_id, db)

@router.post("/resend-otp", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def resend_otp(request: Request, email: ResendOtpData, db: AsyncSession = Depends(get_async_db)):
    return await resend_otp_code(email, db)

@router.post("/verify-device-otp", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_device_otp_endpoint(request: Request, email: str = Form(...), otp: str = Form(...), db: AsyncSession = Depends(get_async_db)):
    return await verify_device_otp(email, otp, db)

@router.post("/resend-device-otp", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def resend_device_otp(request: Request, email: str = Form(...), db: AsyncSession = Depends(get_async_db)):
    return await resend_device_verification_otp(email, db)

@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def login(request: Request, login_data: UserLoginData, db: AsyncSession = Depends(get_async_db)):
    return await login_user(login_data, db)

@router.post("/officials-login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def officials_login_route(request: Request, login_data: LoginData, db: AsyncSession = Depends(get_async_db)):
    await verify_turnstile(login_data.turnstile_token, request, expected_action="official_login")
    return await officials_login(login_data, db)

@router.post("/barangay-member-mobile-login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def barangay_member_mobile_login_route(request: Request, login_data: LoginData, db: AsyncSession = Depends(get_async_db)):
    return await barangay_member_mobile_login(login_data, db)

@router.post("/superadmin-login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def superadmin_login_route(request: Request, login_data: LoginData, db: AsyncSession = Depends(get_async_db)):
    await verify_turnstile(login_data.turnstile_token, request, expected_action="superadmin_login")
    return await superadmin_login(login_data, db)

@router.post("/logout", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def logout(request: Request, db: AsyncSession = Depends(get_async_db)):
    return await logout_user(request)

@router.post("/logout-resident", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def logout_resident_route(request: Request, current_user: User = Depends(get_current_user)):
    return await logout_resident(current_user.id)

@router.post("/refresh-token", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")
async def refresh_token(request: Request, db: AsyncSession = Depends(get_async_db)):
    return await refresh_access_token(request, db)


@router.patch("/id-verification", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def id_verification(
    request: Request,
    id_type: str = Form(...),
    id_number: str = Form(...),
    front_id: str = Form(...),
    back_id: str = Form(...),
    selfie_with_id: str = Form(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    return await upload_id_images(current_user.id, id_type, id_number, front_id, back_id, selfie_with_id, db)

@router.post("/login/google", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login_google(request: Request, device_info: DeviceInfo, payload: ClerkLoginRequest, db: AsyncSession = Depends(get_async_db)):
    
    return await login_with_google(device_info,payload.clerk_token, db)
 
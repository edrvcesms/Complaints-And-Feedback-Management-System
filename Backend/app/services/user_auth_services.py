from fastapi import HTTPException, Request, status, UploadFile
from jose import JWTError
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.query_optimization import BatchLoader
from app.models.user import User
from app.utils.logger import logger
from app.schemas.user_auth_schema import DeviceInfo, LoginData, LoginResponse, RegisterData, UserLoginData,OTPVerificationData, ResendOtpData
from app.models.user_device import UserDevice
from sqlalchemy import select
from app.core.security import hash_password, decrypt_password, verify_token, is_token_revoked, revoke_token_jti
from datetime import datetime, timezone
from app.utils.otp_handler import generate_otp
from app.utils.cookies import set_cookies, clear_cookies
from app.utils.cache_invalidator_optimized import invalidate_cache
from app.utils.caching import set_cache, get_cache, delete_cache
from app.tasks.email_tasks import send_otp_email_task, send_otp_device_verification
from fastapi.responses import JSONResponse
from app.core.security import create_access_token, create_refresh_token
from app.utils.cloudinary import upload_multiple_files_to_cloudinary
from app.constants.roles import UserRole
from app.schemas.barangay_schema import BarangayWithUserData
from app.services.barangay_services import get_barangay_account
from app.services.sse_manager import sse_manager
from app.utils.attachments import validate_upload_files
from app.core.clerk.clerk_client import verify_clerk_token
from app.core.clerk.clerk_users import get_clerk_user_email, get_or_create_user_from_clerk
from app.utils.base64_decoder import data_uri_to_upload_file

import base64, re

def decode_data_uri(data_uri: str) -> bytes:
    match = re.match(r'^data:image/\w+;base64,(.+)$', data_uri)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid image data.")
    return base64.b64decode(match.group(1))

async def _build_login_response(user: User) -> JSONResponse:
    refresh_token = create_refresh_token(data={"user_id": user.id})
    access_token = create_access_token(data={"user_id": user.id})

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token
        })
    )
    await set_cookies(response, refresh_token=refresh_token)
    return response

async def register_user(user_data: RegisterData, db: AsyncSession):
    
    try:
        result = await db.execute(select(User).where(User.email == user_data.email))
        existing_user = result.scalars().first()

        if existing_user:
            logger.warning(f"Registration attempt with existing email: {user_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
            
        result_number = await db.execute(select(User).where(User.phone_number == user_data.phone_number))
        existing_number = result_number.scalars().first()
        
        if existing_number:
            logger.warning(f"OTP verification attempt with existing phone number: {user_data.phone_number}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already registered"
            )
            

        generated_otp = generate_otp()
        await set_cache(f"otp:{user_data.email}", generated_otp, expiration=300)
        logger.info(f"OTP generated for {user_data.email} and stored in cache.")

        send_otp_email_task.delay(user_data.email, generated_otp, purpose="Registration")
        logger.info(f"OTP task enqueued for {user_data.email}.")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "OTP sent to your email. Please verify to complete registration."}
        )
    
    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error during registration for {user_data.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration. Please try again later."
        )
    
async def verify_otp_and_register(otp: str, user_data: OTPVerificationData, front_id: UploadFile, back_id: UploadFile, selfie_with_id: UploadFile, db: AsyncSession):

    try:
        """
        result = await db.execute(select(User).where(User.phone_number == user_data.phone_number))
        existing_user = result.scalars().first()
        
        if existing_user:
            logger.warning(f"OTP verification attempt with existing phone number: {user_data.phone_number}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already registered"
            )
        """
        cached_otp = await get_cache(f"otp:{user_data.email}")
        

        if not cached_otp:
            logger.warning(f"OTP verification failed for {user_data.email}: OTP expired or not found.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired or not found. Please request a new one."
            )

        if otp != str(cached_otp):
            logger.warning(f"OTP verification failed for {user_data.email}: Invalid OTP provided.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP. Please try again."
            )

        if not front_id or not back_id or not selfie_with_id:
            logger.warning(f"OTP verification failed for {user_data.email}: Missing ID images.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All ID images (front, back, selfie with ID) are required."
            )
        
        images = [front_id, back_id, selfie_with_id]
        await validate_upload_files(images)
        image_urls = await upload_multiple_files_to_cloudinary(images, folder="ucrs/id_verification")
        logger.info(f"ID images uploaded to Cloudinary for {user_data.email}: {image_urls}")

        
        hashed_password = hash_password(user_data.password)

        new_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            middle_name=user_data.middle_name,
            suffix=user_data.suffix,
            age=user_data.age,
            birthdate=user_data.birthdate,
            phone_number=user_data.phone_number,
            gender=user_data.gender,
            barangay=user_data.barangay,
            zip_code=user_data.zip_code,
            full_address=user_data.full_address,
            longitude=user_data.longitude,
            latitude=user_data.latitude,
            id_type=user_data.id_type,
            id_number=user_data.id_number,
            front_id=image_urls[0],
            back_id=image_urls[1],
            selfie_with_id=image_urls[2],
            created_at=datetime.now(timezone.utc)
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        await delete_cache(f"otp:{user_data.email}")

        logger.info(f"User registered successfully with email: {user_data.email}")

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"message": "Registration successful. You can now log in."}
        )

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during OTP verification and registration for {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during OTP verification. Please try again later."
        )
        
async def upload_id_images(user_id: int, id_type: str, id_number: str, front_id: str, back_id: str, selfie_with_id: str, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()

        if not user:
            logger.warning(f"ID image upload attempt for non-existent user_id: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if not id_number or not id_number.strip():
            logger.warning(f"ID image upload failed for user_id: {user_id}: Missing ID number.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID number is required."
            )

        if not front_id or not back_id or not selfie_with_id:
            logger.warning(f"ID image upload failed for user_id: {user_id}: Missing ID images.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All ID images (front, back, selfie with ID) are required."
            )

        # Decode base64 data URIs into UploadFile-compatible objects
        front_id_file = data_uri_to_upload_file(front_id, "front_id")
        back_id_file = data_uri_to_upload_file(back_id, "back_id")
        selfie_file = data_uri_to_upload_file(selfie_with_id, "selfie_with_id")

        images = [front_id_file, back_id_file, selfie_file]
        await validate_upload_files(images)
        image_urls = await upload_multiple_files_to_cloudinary(images, folder="ucrs/id_verification")
        logger.info(f"ID images uploaded to Cloudinary for {user.email}: {image_urls}")

        user.id_type = id_type
        user.id_number = id_number
        user.front_id = image_urls[0]
        user.back_id = image_urls[1]
        user.selfie_with_id = image_urls[2]
        await delete_cache(f"user_data:{user_id}")

        await db.commit()
        await db.refresh(user)
        await delete_cache(f"user_profile:{user_id}")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "ID images uploaded successfully."}
        )

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during ID image upload for id_type: {id_type}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during ID image upload. Please try again later."
        )
        
async def resend_otp_code(email: ResendOtpData, db: AsyncSession):
    try:
        await delete_cache(f"otp:{email.email}")
        result = await db.execute(select(User).where(User.email == email.email))
        existing_user = result.scalars().first()

        if existing_user:
            logger.warning(f"OTP resend attempt with existing email: {email.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        generated_otp = generate_otp()
        await set_cache(f"otp:{email.email}", generated_otp, expiration=300)
        logger.info(f"OTP generated for {email.email} and stored in cache.")

        send_otp_email_task.delay(email.email, generated_otp, purpose="Registration")
        logger.info(f"OTP task enqueued for {email.email}.")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "OTP resent to your email. Please verify to complete registration."}
        )
    except HTTPException:
        raise   
    
    except Exception as e:
        logger.exception(f"Error during OTP resend for {email.email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resending OTP. Please try again later."
        )
        
async def verify_device_otp(email: str, otp: str, db: AsyncSession):
    try:
        
        response = await db.execute(select(User).where(User.email == email))
        user = response.scalars().first()
        
        device_otp_key = f"device_otp:{email}"
        cached_otp = await get_cache(device_otp_key)
        user_login_data_key = f"user_login_info:{email}"
        get_user_login_data = await get_cache(user_login_data_key)
        logger.info(f"Verifying device OTP for {email}. Cached OTP: {cached_otp}, Provided OTP: {otp}")
        
        if not cached_otp:
            logger.warning(f"Device OTP verification failed for {email}: OTP expired or not found.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired or not found. Please request a new one."
            )
            
        if otp != str(cached_otp):
            logger.warning(f"Device OTP verification failed for {email}: Incorrect OTP.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect OTP. Please try again."
            )
        logger.info(f"Device OTP verified successfully for {email}.")
        
        new_device = UserDevice(
            user_id=user.id,
            device_id=get_user_login_data.get("device_id"),
            model=get_user_login_data.get("model"),
            brand=get_user_login_data.get("brand"),
            system_name=get_user_login_data.get("system_name"),
            app_version=get_user_login_data.get("app_version"),
            build_number=get_user_login_data.get("build_number")
        )
        db.add(new_device)
        await db.commit()
        await delete_cache(user_login_data_key)
        await delete_cache(device_otp_key)
        
        refresh_token = create_refresh_token(data={"user_id": user.id})
        access_token = create_access_token(data={"user_id": user.id})
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder({
                "message": "Device verified successfully. You can now log in.",
                "access_token": access_token,
                "refresh_token": refresh_token if user.role == UserRole.USER else None
            }))
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception(f"Error during device OTP verification for {email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during device OTP verification. Please try again later."
        )
        
async def resend_device_verification_otp(email: str, db: AsyncSession):
    try:
        await delete_cache(f"device_otp:{email}")
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalars().first()

        if not existing_user:
            logger.warning(f"Device OTP resend attempt with unregistered email: {email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This email is not registered. Please check your email or register for a new account."
            )

        generated_otp = generate_otp()
        await set_cache(f"device_otp:{email}", generated_otp, expiration=300)
        logger.info(f"Device OTP generated for {email} and stored in cache.")

        send_otp_device_verification.delay(email, generated_otp)
        logger.info(f"Device OTP task enqueued for {email}.")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Device OTP resent to your email. Please verify to complete device verification."}
        )
    except HTTPException:
        raise   
    
    except Exception as e:
        logger.exception(f"Error during device OTP resend for {email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resending device OTP. Please try again later."
        )        

async def login_user(login_data: UserLoginData, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.email == login_data.email))
        user = result.scalars().first()

        if not user:
            logger.warning(f"Login attempt with unregistered email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This email is not registered. Please check your email or register for a new account.")

        if not decrypt_password(login_data.password, user.hashed_password):
            logger.warning(f"Login attempt with incorrect password for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        
        if user.role != UserRole.USER:
            logger.warning(f"Login attempt with unauthorized role for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized Access")
        
        
        user_devices_dict = await BatchLoader.fetch_user_devices_by_user_ids(db, [user.id])
        
        user_devices = user_devices_dict.get(user.id, [])
        logger.info(f"User devices retrieved for {login_data.email}: {user_devices}")
        
        if not user_devices:
            new_device = UserDevice(
                user_id=user.id,
                device_id=login_data.device_id,
                model=login_data.model,
                brand=login_data.brand,
                system_name=login_data.system_name,
                app_version=login_data.app_version,
                build_number=login_data.build_number
            )
            db.add(new_device)
            await db.commit()
            return await _build_login_response(user) 

        if any(device.device_id == login_data.device_id for device in user_devices):
            return await _build_login_response(user)

        # generate_device_otp = generate_otp()
        # logger.info(f"Device not recognized for user {login_data.email}. OTP generated.")
        # await set_cache(f"device_otp:{login_data.email}", generate_device_otp, expiration=300)
        # send_otp_device_verification.delay(login_data.email, generate_device_otp, device_info={
        #     "device_id": login_data.device_id,
        #     "model": login_data.model,
        #     "brand": login_data.brand,
        #     "system_name": login_data.system_name,
        #     "app_version": login_data.app_version,
        #     "build_number": login_data.build_number
        # })
        
        await set_cache(f"user_login_info:{login_data.email}", login_data.dict(), expiration=300)
        

        refresh_token = create_refresh_token(data={"user_id": user.id})
        access_token = create_access_token(data={"user_id": user.id})
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder({
                "is_verified": True,
                "message": "Device OTP sent successfully",
                "access_token": access_token,
                "refresh_token": refresh_token if user.role == UserRole.USER else None
            })
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during login for {login_data.email}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during login. Please try again later.")

async def officials_login(login_data: LoginData, db: AsyncSession):
    barangay_data = None

    try:
        result = await db.execute(select(User).where(User.email == login_data.email))
        user = result.scalars().first()

        if not user:
            logger.warning(f"Login attempt with unregistered email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This email is not registered. Please check your email or register for a new account.")

        if not decrypt_password(login_data.password, user.hashed_password):
            logger.warning(f"Login attempt with incorrect password for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        
        if user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL, UserRole.BARANGAY_MEMBER]:
            logger.warning(f"Login attempt with unauthorized role for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized Access")

        if user.role == UserRole.BARANGAY_OFFICIAL:
            barangay = await get_barangay_account(user.id, db)
            if not barangay:
                logger.warning(f"Login attempt for barangay official with no associated barangay: {login_data.email}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated barangay not found")
            barangay_data = BarangayWithUserData.model_validate(barangay, from_attributes=True)

        logger.info(f"User logged in successfully with email: {login_data.email}")

        refresh_token = create_refresh_token(data={"user_id": user.id})
        access_token = create_access_token(data={"user_id": user.id})

        user_cache = {
            "barangay_data": jsonable_encoder(barangay_data.model_dump()) if barangay_data else None,
        }
        await set_cache(f"user_data:{user.id}", user_cache, expiration=3600)
        logger.info(f"User data cached for user_id: {user.id}")

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder({
                "message": "Login successful",
                "access_token": access_token,
                "refresh_token": refresh_token if user.role == UserRole.USER else None,
                "role": user.role,
                "barangayAccountData": user_cache["barangay_data"] if barangay_data else None,
            })
        )

        await set_cookies(response, refresh_token=refresh_token)
        return response

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during login for {login_data.email}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during login. Please try again later.")


async def barangay_member_mobile_login(login_data: LoginData, db: AsyncSession):
    """Authenticate a barangay member from the mobile application.

    This endpoint intentionally does not use Turnstile because the mobile
    application has no browser-based Turnstile challenge. It is restricted to
    the barangay_member role and does not change the protected web login flow.
    """
    try:
        if login_data.role != UserRole.BARANGAY_MEMBER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to barangay members.",
            )

        result = await db.execute(select(User).where(User.email == login_data.email))
        user = result.scalars().first()

        if not user:
            logger.warning(f"Mobile login attempt with unregistered email: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This email is not registered. Please check your email or password.",
            )

        if not decrypt_password(login_data.password, user.hashed_password):
            logger.warning(f"Mobile login attempt with incorrect password for email: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if user.role != UserRole.BARANGAY_MEMBER:
            logger.warning(f"Mobile login attempt with unauthorized role for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized Access")

        refresh_token = create_refresh_token(data={"user_id": user.id})
        access_token = create_access_token(data={"user_id": user.id})

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder({
                "message": "Login successful",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "role": user.role,
                "barangayAccountData": None,
            }),
        )
        await set_cookies(response, refresh_token=refresh_token)
        return response

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception(f"Error during mobile login for {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login. Please try again later.",
        )


async def superadmin_login(login_data: LoginData, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.email == login_data.email))
        user = result.scalars().first()

        if not user:
            logger.warning(f"Login attempt with unregistered email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This email is not registered. Please check your email or register for a new account.")

        if not decrypt_password(login_data.password, user.hashed_password):
            logger.warning(f"Login attempt with incorrect password for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        if user.role != UserRole.SUPERADMIN:
            logger.warning(f"Login attempt with unauthorized role for email: {login_data.email}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized Access")

        logger.info(f"Super admin logged in successfully with email: {login_data.email}")

        refresh_token = create_refresh_token(data={"user_id": user.id})
        access_token = create_access_token(data={"user_id": user.id})

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder({
                "message": "Login successful",
                "access_token": access_token,
                "refresh_token": refresh_token if user.role == UserRole.USER else None,
                "role": user.role
            })
        )

        await set_cookies(response, refresh_token=refresh_token)
        return response

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during login for {login_data.email}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during login. Please try again later.")

async def refresh_access_token(request: Request, db: AsyncSession):
    try:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                refresh_token = auth_header.split(" ", 1)[1]  
  
        if not refresh_token:
            logger.warning("Invalid or missing refresh token during token refresh attempt.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Expired or invalid refresh token."
            )
        try:
            payload = verify_token(refresh_token, expected_token_type="refresh")
        except JWTError:
            logger.warning("Invalid refresh token provided during token refresh attempt.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token during token refresh attempt."
            )
        if await is_token_revoked(payload.get("jti")):
            logger.warning("Revoked refresh token used during token refresh attempt.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token during token refresh attempt."
            )
        user_id = payload.get("user_id")
        if not user_id:
            logger.warning("Invalid refresh token payload: user_id missing during token refresh attempt.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload during token refresh attempt."
            )
            
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token during token refresh attempt."
            )
        
        barangay_data = None
        cached_user_data = await get_cache(f"user_data:{user_id}")
        logger.info(f"Cache lookup completed for user_id: {user_id} during token refresh attempt.")
        
        if user.role == UserRole.BARANGAY_OFFICIAL:
            barangay_json_data = cached_user_data.get("barangay_data") if cached_user_data else None
            if barangay_json_data:
                logger.info(f"Barangay data for user_id: {user.id} retrieved from cache during token refresh.")
                barangay_data = BarangayWithUserData.model_validate(jsonable_encoder(barangay_json_data))
                logger.info(f"Barangay data for user_id: {user.id} successfully validated from cache during token refresh.")
            else:
                logger.info(f"Barangay data for user_id: {user.id} not found in cache during token refresh. Fetching from database.")
                barangay = await get_barangay_account(user.id, db)
                barangay_data = BarangayWithUserData.model_validate(barangay, from_attributes=True)
            

        new_refresh_token = create_refresh_token(data={"user_id": user_id})
        new_access_token = create_access_token(data={"user_id": user_id})
        await revoke_token_jti(payload.get("jti"), payload.get("exp"))
        logger.info(f"Access token refreshed for user_id: {user_id} during token refresh attempt.")

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder({
                "message": "Access token refreshed successfully",
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "role": user.role,
                "barangayAccountData": barangay_data if user.role == UserRole.BARANGAY_OFFICIAL else None,
            })
        )
        await set_cookies(response, refresh_token=new_refresh_token)
        return response
    
    except HTTPException:   
        raise
    except Exception as e:
        logger.exception("Error during access token refresh")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while refreshing access token. Please try again later.")

async def logout_user(request: Request):
    try:
        token = request.cookies.get("refresh_token") or request.cookies.get("access_token")
        if not token:
            logger.warning("Logout attempt with missing authentication cookies.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No authentication cookies found. Are you sure you're logged in?"
            )

        user_id = request.cookies.get("user_id")
        if not user_id:
            try:
                payload = verify_token(token)
                user_id = payload.get("user_id")
            except JWTError:
                user_id = None

        if user_id:
            await delete_cache(f"user_data:{user_id}")
            await delete_cache(f"auth_user:{user_id}")
        try:
            payload = verify_token(token)
            if payload.get("token_type") == "refresh":
                await revoke_token_jti(payload.get("jti"), payload.get("exp"))
        except JWTError:
            pass
        logger.info("User logged out successfully and cache cleared.")
        
        
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Logout successful"
            }
        )
        if user_id:
            await sse_manager.disconnect_user(user_id)
            logger.info("SSE connection closed for user during logout.")
        await clear_cookies(response, "refresh_token")
        return response
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception("Error during logout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during logout. Please try again later."
        )
        
async def logout_resident(user_id: int):
    try:
        await delete_cache(f"user_data:{user_id}")
        await delete_cache(f"auth_user:{user_id}")
        await invalidate_cache(include_global=True, user_ids=[user_id])
        logger.info(f"Resident with user_id: {user_id} logged out successfully and cache cleared.")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Logout successful"
            }
        )
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.exception(f"Error during resident logout for user_id: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during logout. Please try again later."
        )
        


async def login_with_google(device_info: DeviceInfo, clerk_token: str, db: AsyncSession) -> LoginResponse:
    # Verify Clerk JWT
    claims = verify_clerk_token(clerk_token)
    clerk_user_id = claims["sub"]

    # Get email from Clerk
    email = get_clerk_user_email(clerk_user_id)

    # Find or create local user
    user = await get_or_create_user_from_clerk(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
    )
    

    user_devices_dict = await BatchLoader.fetch_user_devices_by_user_ids(db, [user.id])
    
    user_devices = user_devices_dict.get(user.id, [])
    logger.info(f"User devices retrieved for {user.email}: {user_devices}")
    
    if not user_devices:
        new_device = UserDevice(
            user_id=user.id,
            device_id=device_info.device_id,
            model=device_info.model,
            brand=device_info.brand,
            system_name=device_info.system_name,
            app_version=device_info.app_version,
            build_number=device_info.build_number
        )
        db.add(new_device)
        await db.commit()
        return await _build_login_response(user) 

    if any(device.device_id == device_info.device_id for device in user_devices):
        return await _build_login_response(user)

    generate_device_otp = generate_otp()
    logger.info(f"Device not recognized for user {user.email}. OTP generated.")
    await set_cache(f"device_otp:{user.email}", generate_device_otp, expiration=300)
    send_otp_device_verification.delay(user.email, generate_device_otp, device_info={
        "device_id": device_info.device_id,
        "model": device_info.model,
        "brand": device_info.brand,
        "system_name": device_info.system_name,
        "app_version": device_info.app_version,
        "build_number": device_info.build_number
    })
    await set_cache(f"user_login_info:{user.email}", device_info.dict(), expiration=300)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder({
            "email": user.email,
            "is_verified": False,
            "message": "Device OTP sent successfully"
        })
    )


from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
import redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.push_token import PushToken
from app.utils.otp_handler import generate_otp
from app.schemas.user_schema import ChangePasswordData, VerifyEmailData, UserData, OTPData, UserLocationData, ResetPasswordData
from app.models.user import User
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.utils.geo_services import get_barangay
from app.utils.reverse_geocoding import reverse_geocode
from app.core.security import hash_password, decrypt_password
from fastapi.responses import JSONResponse
from app.tasks.email_tasks import send_otp_email_task
from app.utils.logger import logger
from app.utils.caching import set_cache, get_cache, delete_cache, delete_cache_prefix
from app.core.config import settings
import httpx
import math
from app.constants.roles import UserRole

async def get_user_by_id(user_id: int, db: AsyncSession) -> UserData:
    try:
        user_cached = await get_cache(f"user_profile:{user_id}")
        if user_cached:
            logger.info(f"User profile for user ID {user_id} retrieved from cache")
            return UserData.model_validate_json(user_cached)
        
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        user_data = UserData.model_validate(user, from_attributes=True)
        await set_cache(f"user_profile:{user_id}", user_data.model_dump_json(), expiration=3600)
        print(user_data)
        return user_data
    
    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error retrieving user by ID {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def forgot_password(email_data: VerifyEmailData, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.email == email_data.email))
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        if user.email == email_data.email:
            generated_otp = generate_otp()
            await set_cache(f"otp_reset_password:{email_data.email}", generated_otp, expiration=300)

            send_otp_email_task.delay(email_data.email, generated_otp, purpose="Forgot Password")

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "OTP sent to your email. Please verify to proceed."}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error requesting forgot password for email {email_data.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def create_new_password(password_data: ResetPasswordData, db: AsyncSession):
    try:
        cached = await get_cache(f"otp_reset_password:{password_data.email}")
        
        if cached:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP verification pending. Please verify the OTP sent to your email before creating a new password.")
        
        result = await db.execute(select(User).where(User.email == password_data.email))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        if password_data.new_password != password_data.confirm_new_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")
        
        user.hashed_password = hash_password(password_data.new_password)
        
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Password reset successfully"}
        )
        
    except HTTPException:
        raise
    
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error creating new password for email {password_data.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def request_reset_password(email_data: VerifyEmailData, db: AsyncSession):
    try:
        normalized_email = email_data.email.strip().lower()
        print(f"[REQUEST RESET] Normalized email: '{normalized_email}'")

        result = await db.execute(select(User).where(User.email == normalized_email))
        user = result.scalars().first()
        print(f"[REQUEST RESET] User found: {user}")

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        generated_otp = generate_otp()
        print(f"[REQUEST RESET] Generated OTP: {generated_otp}")

        cache_key = f"otp_reset_password:{normalized_email}"
        print(f"[REQUEST RESET] Setting cache key: '{cache_key}'")
        await set_cache(cache_key, generated_otp, expiration=300)
        print(f"[REQUEST RESET] Cache set successfully")

        send_otp_email_task.delay(normalized_email, generated_otp, purpose="Reset Password")
        print(f"[REQUEST RESET] Email task dispatched to: '{normalized_email}'")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "OTP sent to your email. Please verify to proceed."}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error requesting reset password for email {normalized_email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def request_change_password(user: User):
    try:
        generated_otp = generate_otp()
        await set_cache(f"otp_reset_password:{user.email}", generated_otp, expiration=300)
        send_otp_email_task.delay(user.email, generated_otp, purpose="Change Password")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"email": user.email, "message": "OTP sent to your email. Please verify to proceed."}
        )
    except Exception as e:
        logger.exception(f"Error requesting password change for user ID {user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to send password change OTP")

async def verify_otp_reset_password(otp_data: OTPData, db: AsyncSession):
    try:
        normalized_email = otp_data.email.strip().lower()
        print(f"[VERIFY OTP] Normalized email: '{normalized_email}'")

        cache_key = f"otp_reset_password:{normalized_email}"
        print(f"[VERIFY OTP] Looking up cache key: '{cache_key}'")
        cached_reset_otp = await get_cache(cache_key)
        print(f"[VERIFY OTP] Cached OTP result: {cached_reset_otp}")

        if not cached_reset_otp:
            print(f"[VERIFY OTP] No OTP found in cache for key: '{cache_key}'")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # Fixed: was HTTP_404_BAD_REQUEST (doesn't exist)
                detail="OTP expired or not found. Please request a new one."
            )

        print(f"[VERIFY OTP] Comparing input OTP: '{otp_data.otp}' with cached OTP: '{cached_reset_otp}'")
        if otp_data.otp != cached_reset_otp:
            print(f"[VERIFY OTP] OTP mismatch!")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP. Please try again."
            )

        await delete_cache(cache_key)
        print(f"[VERIFY OTP] Cache deleted for key: '{cache_key}'")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "OTP verified successfully. You can now reset your password."}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[VERIFY OTP] Unexpected error: {str(e)}")  # Added so hidden errors are visible
        logger.exception(f"Error verifying OTP for reset password: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def change_password(password_data: ChangePasswordData, db: AsyncSession):

    try:
        result = await db.execute(
            select(User).where(User.email == password_data.email)
        )
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if not decrypt_password(password_data.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        
        if password_data.new_password != password_data.confirm_new_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")
        
        user.hashed_password = hash_password(password_data.new_password)

        await db.commit()
        await delete_cache(f"user_profile:{user.id}")
        await delete_cache(f"auth_user:{user.id}")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Password changed successfully"}
        )
    
    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error changing password for user ID {password_data}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def update_user_location(user_id: int, location_data: UserLocationData, db: AsyncSession):
    try:
        try:
            latitude = float(location_data.latitude)
            longitude = float(location_data.longitude)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Latitude and longitude must be valid coordinates.",
            ) from error
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Latitude and longitude must be valid coordinates.")

        logger.info(f"Updating location for user ID {user_id}")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        user.latitude = str(latitude)
        user.longitude = str(longitude)
        user.location_updated_at = datetime.now(timezone.utc)

        if user.role == UserRole.BARANGAY_MEMBER.value:
            await delete_cache(f"user_profile:{user_id}")
            await delete_cache(f"auth_user:{user_id}")
            await db.commit()
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "message": "Location updated successfully",
                    "location_updated_at": user.location_updated_at.isoformat(),
                },
            )

        barangay_info = get_barangay(location_data.latitude, location_data.longitude)
        if barangay_info:
            user.barangay = barangay_info["name"]
        else:
            user.barangay = None 
        logger.info(f"User ID {user_id} location updated to latitude {user.latitude}, longitude {user.longitude}, barangay {user.barangay}")
        
        full_address_info = await reverse_geocode(location_data.latitude, location_data.longitude, user.barangay)
        user.full_address = full_address_info.get("display_name", "Unknown Location")
       
        await delete_cache(f"user_profile:{user_id}")
        await delete_cache(f"auth_user:{user_id}")
        await delete_cache_prefix(f"all_announcements")


        await db.commit()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Location updated successfully",
                "location_updated_at": user.location_updated_at.isoformat(),
            },
        )
    
    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error updating location for user ID {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))



async def save_push_token(db: AsyncSession, user_id: int, token: str) -> User:
    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.push_tokens))
            .where(User.id == user_id)
        )
        user = result.scalars().first()

        if not user:
            raise ValueError(f"User with id '{user_id}' not found.")

        existing_token = next(
            (
                push_token
                for push_token in user.push_tokens
                if push_token.token == token
            ),
            None
        )

        if existing_token:
            # Token already exists, make sure it is active again
            existing_token.is_active = True
        else:
            # New device/token
            db.add(
                PushToken(
                    user_id=user_id,
                    token=token,
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                )
            )

        user.push_notifications_enabled = True

        await db.commit()
        await db.refresh(user)

        await delete_cache(f"user_profile:{user_id}")

        return user

    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise Exception(
            f"Failed to save push token for user '{user_id}': {e}"
        ) from e


async def set_push_notifications(
    db: AsyncSession, user_id: int, enabled: bool
) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()

    if not user:
        raise ValueError("User not found")

    user.push_notifications_enabled = enabled

    await db.commit()
    await db.refresh(user)
    
    await delete_cache(f"user_profile:{user_id}")
    return user


async def send_push_notification(
    db: AsyncSession,
    user_id: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    try:
        user = await db.execute(
            select(User).options(selectinload(User.push_tokens)).where(User.id == user_id)
        )
        user = user.scalars().first()

        if not user:
            raise ValueError(f"User with id '{user_id}' not found.")
       
       
        if user.push_tokens is None or len(user.push_tokens) == 0:
            raise ValueError(f"User with id '{user_id}' does not have any registered push tokens.")

    except ValueError:
        raise
    except Exception as e:
        raise Exception(f"Failed to fetch user '{user_id}' from database: {e}") from e

    try:
        tokens = [push_token.token for push_token in user.push_tokens if push_token.is_active]
        if not tokens:
            raise ValueError(f"User with id '{user_id}' does not have any active push tokens.")
        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": data or {},
                "sound": "default",
                "priority": "high",
            }
            for token in tokens
        ]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.EXPO_PUSH_URL,
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            raise Exception(f"Expo push notification failed: {response.status_code} - {response.text}")

        result = response.json()

        errors = [item for item in result.get("data", []) if item.get("status") == "error"]
        if errors:
            raise Exception(f"Expo reported delivery errors: {errors}")

        return result
    except Exception as e:
        raise Exception(f"Failed to send push notification to user '{user_id}': {e}") from e
    
async def verify_delete_account_otp(email: str, otp: str, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        cached_otp = await get_cache(f"otp_delete_account:{email}")
        if not cached_otp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OTP expired or not found. Please request a new one.")
        
        if otp != cached_otp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP. Please try again.")
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        await db.delete(user)
        await db.commit()
        await delete_cache(f"otp_delete_account:{email}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "OTP verified successfully. You can now delete your account."}
        )
    
    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error verifying OTP for account deletion for email {email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

async def delete_account(email: str, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        generated_otp = generate_otp()
        await set_cache(f"otp_delete_account:{email}", generated_otp, expiration=300)
        send_otp_email_task.delay(email, generated_otp, purpose="Account Deletion")
    
    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.exception(f"Error deleting account for user ID {user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
import requests
from requests.exceptions import ConnectionError, HTTPError
from app.utils.logger import logger

def send_push_notification(
    token: str,
    enabled: bool,
    title: str = None,
    body: str = "",
    data: dict = None,
    sound: str = "default",
    channel_id: str = "complaint-updates",
    expo_token: str = None,
) -> dict:
    if not enabled:
        return {"success": False, "error": "Push notifications are disabled for this user"}

    if not token:
        return {"success": False, "error": "No push token provided"}

    try:
        session = requests.Session()
        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate",
            "content-type": "application/json",
        }
        if expo_token:
            headers["Authorization"] = f"Bearer {expo_token}"
        session.headers.update(headers)
        logger.info(f"Sending push notification with headers: {headers} and body: {{'to': {token}, 'title': {title}, 'body': {body}, 'data': {data}, 'sound': {sound}}}")

        client = PushClient(session=session)
        message = PushMessage(
            to=token,
            title=title,
            body=body,
            data=data or {},
            sound=sound,
            channel_id=channel_id,
        )
        logger.info(f"Constructed PushMessage: {message.__dict__}")

        response = client.publish(message)
        response.validate_response()
        logger.info(f"Push notification response: {response.__dict__}")
        return {
            "success": True,
            "message": "Notification sent successfully",
            "data": response.__dict__,
        }
        

    except DeviceNotRegisteredError:
        return {
            "success": False,
            "error": "Device not registered",
            "action": "Deactivate token in DB",
        }

    except PushTicketError as exc:
        return {
            "success": False,
            "error": "Push ticket error",
            "details": exc.push_response._asdict(),
        }

    except PushServerError as exc:
        return {
            "success": False,
            "error": "Expo server error",
            "details": exc.errors,
        }

    except (ConnectionError, HTTPError) as exc:
        return {
            "success": False,
            "error": "Network error",
            "details": str(exc),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "Unexpected error",
            "details": str(exc),
        }
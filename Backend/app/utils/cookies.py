from fastapi.responses import JSONResponse

async def set_cookies(response: JSONResponse, refresh_token: str, key: str = "refresh_token"):
    response.set_cookie(
        key=key,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        domain=".cfms-stamaria.com",
        max_age=7 * 24 * 60 * 60,
        path="/"
    )

async def clear_cookies(response: JSONResponse, key: str = "refresh_token"):
    response.delete_cookie(
        key=key,
        domain=".cfms-stamaria.com",
        path="/"
    )
    
    
## This is for local testing only. In production, the frontend should handle cookie clearing by setting the same cookie with an expired date.

# async def set_cookies(response: JSONResponse, refresh_token: str, key: str = "refresh_token"):
#     response.set_cookie(
#         key=key,
#         value=refresh_token,
#         httponly=True,
#         secure=False,                # keep FALSE for local testing
#         samesite="Lax",              # change from None → Lax
#         domain="127.0.0.1",          # use localhost for local testing
#         max_age=7 * 24 * 60 * 60,
#         path="/"
#     )
    
# async def clear_cookies(response: JSONResponse, key: str = "refresh_token"):
#     response.delete_cookie(
#         key=key,
#         domain="127.0.0.1",          # MUST MATCH set_cookie
#         path="/"
#     )
    
    
"""Auth routes for the dummy API service."""
import uuid
import random
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dummy_api.data import USERS, PHONE_TO_USER, OTP_STORE

router = APIRouter()


class OTPRequest(BaseModel):
    phone: str


class OTPVerify(BaseModel):
    phone: str
    otp: str


class LoginOTPRequest(BaseModel):
    phone: str


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str


# POST /v1/otp/{type}  — Request OTP
@router.post("/v1/otp/{otp_type}")
async def request_otp(otp_type: str, body: OTPRequest):
    """Generate and store a dummy OTP for the given phone."""
    otp_code = str(random.randint(1000, 9999))
    OTP_STORE[body.phone] = {
        "otp": otp_code,
        "type": otp_type,
        "verified": False,
        "user_id": PHONE_TO_USER.get(body.phone),
    }
    # In real system OTP would be sent via SMS
    return {"success": True, "message": f"OTP sent to {body.phone}", "debug_otp": otp_code}


# POST /v1/otp/{type}/verify  — Verify OTP
@router.post("/v1/otp/{otp_type}/verify")
async def verify_otp(otp_type: str, body: OTPVerify):
    """Verify OTP for the given phone."""
    entry = OTP_STORE.get(body.phone)
    if not entry:
        raise HTTPException(status_code=400, detail="No OTP requested for this phone")
    if entry["otp"] != body.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    entry["verified"] = True
    user_id = entry.get("user_id")
    token = f"tok-{uuid.uuid4().hex[:16]}"
    entry["token"] = token

    return {
        "success": True,
        "user_id": user_id,
        "token": token,
        "is_registered": user_id is not None,
    }


# POST /v2/user/auth/login/otp  — Login via OTP (step 1: request)
@router.post("/v2/user/auth/login/otp")
async def login_otp(body: LoginOTPRequest):
    """Request OTP for login."""
    otp_code = str(random.randint(1000, 9999))
    user_id = PHONE_TO_USER.get(body.phone)
    OTP_STORE[body.phone] = {
        "otp": otp_code,
        "type": "login",
        "verified": False,
        "user_id": user_id,
    }
    return {
        "success": True,
        "message": f"OTP sent to {body.phone}",
        "is_registered": user_id is not None,
        "debug_otp": otp_code,
    }


# POST /v2/user/auth/verify-otp  — Verify OTP for login (step 2)
@router.post("/v2/user/auth/verify-otp")
async def verify_login_otp(body: VerifyOTPRequest):
    """Verify OTP and return auth token + user profile."""
    entry = OTP_STORE.get(body.phone)
    if not entry:
        raise HTTPException(status_code=400, detail="No OTP requested for this phone")
    if entry["otp"] != body.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    entry["verified"] = True
    token = f"tok-{uuid.uuid4().hex[:16]}"
    entry["token"] = token
    user_id = entry.get("user_id")

    result = {
        "success": True,
        "token": token,
        "is_registered": user_id is not None,
    }
    if user_id and user_id in USERS:
        result["user"] = {
            "id": user_id,
            "name": USERS[user_id]["name"],
            "phone": USERS[user_id]["phone"],
            "email": USERS[user_id]["email"],
        }
    return result


# POST /v2/user/auth/login  — Direct login (simplified)
@router.post("/v2/user/auth/login")
async def login_direct(body: LoginOTPRequest):
    """Direct login by phone (for testing)."""
    user_id = PHONE_TO_USER.get(body.phone)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")
    token = f"tok-{uuid.uuid4().hex[:16]}"
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "name": USERS[user_id]["name"],
            "phone": USERS[user_id]["phone"],
        },
    }


# POST /v2/user/auth/logout
@router.post("/v2/user/auth/logout")
async def logout():
    return {"success": True, "message": "Logged out"}

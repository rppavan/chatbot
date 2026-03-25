"""User routes for the mock API service."""
import copy
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from mock_api.data import USERS

router = APIRouter()


class AddressCreate(BaseModel):
    label: str = "Home"
    line1: str
    line2: Optional[str] = ""
    city: str
    state: str
    pincode: str


class AddressUpdate(BaseModel):
    label: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


# GET /v2/user/{id}/profile
@router.get("/v2/user/{user_id}/profile")
async def get_profile(user_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "phone": user["phone"],
        "is_registered": user["is_registered"],
    }


# PUT /v2/user/{id}/profile
@router.put("/v2/user/{user_id}/profile")
async def update_profile(user_id: str, body: ProfileUpdate):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.name:
        user["name"] = body.name
    if body.email:
        user["email"] = body.email
    return {"success": True, "user": get_profile.__wrapped__(user_id) if False else {"id": user_id, "name": user["name"]}}


# GET /v2/user/{id}/address
@router.get("/v2/user/{user_id}/address")
async def get_addresses(user_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"addresses": copy.deepcopy(user.get("addresses", []))}


# POST /v2/user/{id}/address
@router.post("/v2/user/{user_id}/address")
async def add_address(user_id: str, body: AddressCreate):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_addr = {
        "id": f"addr-{uuid.uuid4().hex[:6]}",
        "label": body.label,
        "line1": body.line1,
        "line2": body.line2 or "",
        "city": body.city,
        "state": body.state,
        "pincode": body.pincode,
        "is_default": False,
    }
    user["addresses"].append(new_addr)
    return {"success": True, "address": new_addr}


# GET /v2/user/{id}/address/{addressId}
@router.get("/v2/user/{user_id}/address/{address_id}")
async def get_address(user_id: str, address_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for addr in user.get("addresses", []):
        if addr["id"] == address_id:
            return copy.deepcopy(addr)
    raise HTTPException(status_code=404, detail="Address not found")


# PUT /v2/user/{id}/address/{addressId}
@router.put("/v2/user/{user_id}/address/{address_id}")
async def update_address(user_id: str, address_id: str, body: AddressUpdate):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for addr in user.get("addresses", []):
        if addr["id"] == address_id:
            if body.label is not None:
                addr["label"] = body.label
            if body.line1 is not None:
                addr["line1"] = body.line1
            if body.line2 is not None:
                addr["line2"] = body.line2
            if body.city is not None:
                addr["city"] = body.city
            if body.state is not None:
                addr["state"] = body.state
            if body.pincode is not None:
                addr["pincode"] = body.pincode
            return {"success": True, "address": copy.deepcopy(addr)}
    raise HTTPException(status_code=404, detail="Address not found")


# DELETE /v2/user/{id}/address/{addressId}
@router.delete("/v2/user/{user_id}/address/{address_id}")
async def delete_address(user_id: str, address_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["addresses"] = [a for a in user.get("addresses", []) if a["id"] != address_id]
    return {"success": True}


# PUT /v2/user/{id}/preferred-address/{addressId}
@router.put("/v2/user/{user_id}/preferred-address/{address_id}")
async def set_preferred_address(user_id: str, address_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for addr in user.get("addresses", []):
        addr["is_default"] = addr["id"] == address_id
    return {"success": True}


# GET /v2/user/{id}/wallet
@router.get("/v2/user/{user_id}/wallet")
async def get_wallet(user_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "balance": user.get("wallet_balance", 0.0), "currency": "INR"}


# GET /v2/user/{id}/wishlist
@router.get("/v2/user/{user_id}/wishlist")
async def get_wishlist(user_id: str):
    return {"user_id": user_id, "items": []}


# GET /v2/product/{id}
@router.get("/v2/product/{product_id}")
async def get_product(product_id: str):
    from mock_api.data import PRODUCTS
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return copy.deepcopy(product)

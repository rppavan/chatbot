"""Order routes for the mock API service."""
import copy
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from mock_api.data import ORDERS, PRODUCTS, PHONE_TO_USER, get_orders_for_user, get_orders_by_phone

router = APIRouter()


class CancelRequest(BaseModel):
    reason: Optional[str] = "Customer requested cancellation"
    item_ids: Optional[list[str]] = None


class ReturnRequest(BaseModel):
    reason: str = "Product not as expected"
    item_ids: Optional[list[str]] = None


class ExchangeRequest(BaseModel):
    reason: str = "Size/Color change"
    item_ids: Optional[list[str]] = None
    new_variant_id: Optional[str] = None


# GET /v1/order-search
@router.get("/v1/order-search")
async def order_search(
    phone: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Search orders by phone or user_id, optionally filter by status."""
    orders = []
    if phone:
        orders = get_orders_by_phone(phone)
    elif user_id:
        orders = get_orders_for_user(user_id)
    else:
        orders = [copy.deepcopy(o) for o in ORDERS.values()]

    if status:
        orders = [o for o in orders if o["fulfillment_status"] == status]

    # Return summary (no full detail)
    summaries = []
    for o in orders:
        summaries.append({
            "id": o["id"],
            "status": o["status"],
            "fulfillment_status": o["fulfillment_status"],
            "total": o["total"],
            "currency": o["currency"],
            "created_at": o["created_at"],
            "item_count": len(o["items"]),
            "first_item_name": o["items"][0]["name"] if o["items"] else "",
        })
    return {"orders": summaries, "total": len(summaries)}


# GET /v1/order/{id}
@router.get("/v1/order/{order_id}")
async def get_order(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return copy.deepcopy(order)


# GET /v1/order/{id}/tracking-summary
@router.get("/v1/order/{order_id}/tracking-summary")
async def tracking_summary(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    status = order["fulfillment_status"]
    now = datetime.utcnow()

    tracking = {
        "order_id": order_id,
        "status": status,
        "awb": order.get("awb"),
        "courier": order.get("courier"),
        "events": [],
    }

    if status == "pre_dispatch":
        tracking["eta"] = (now + timedelta(days=5)).isoformat()
        tracking["events"] = [
            {"status": "Order Placed", "timestamp": order["created_at"]},
            {"status": "Processing", "timestamp": order["updated_at"]},
        ]
    elif status == "shipped":
        tracking["eta"] = (now + timedelta(days=3)).isoformat()
        tracking["events"] = [
            {"status": "Order Placed", "timestamp": order["created_at"]},
            {"status": "Shipped", "timestamp": order["updated_at"]},
            {"status": "In Transit", "timestamp": now.isoformat()},
        ]
    elif status == "out_for_delivery":
        tracking["eta"] = now.isoformat()
        tracking["events"] = [
            {"status": "Order Placed", "timestamp": order["created_at"]},
            {"status": "Shipped", "timestamp": (now - timedelta(days=2)).isoformat()},
            {"status": "Out for Delivery", "timestamp": order["updated_at"]},
        ]
    elif status == "delivered":
        tracking["delivered_at"] = order.get("delivered_at")
        tracking["events"] = [
            {"status": "Order Placed", "timestamp": order["created_at"]},
            {"status": "Delivered", "timestamp": order.get("delivered_at", order["updated_at"])},
        ]
    elif status == "cancelled":
        tracking["events"] = [
            {"status": "Order Placed", "timestamp": order["created_at"]},
            {"status": "Cancelled", "timestamp": order.get("cancelled_at", order["updated_at"])},
        ]

    return tracking


# GET /v1/order/{id}/cancel_options
@router.get("/v1/order/{order_id}/cancel_options")
async def cancel_options(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    status = order["fulfillment_status"]
    can_cancel = status in ("pre_dispatch", "shipped")
    reasons = []
    if can_cancel:
        reasons = [
            "Changed my mind",
            "Found a better price",
            "Ordered by mistake",
            "Delivery taking too long",
            "Other",
        ]
    return {
        "order_id": order_id,
        "can_cancel": can_cancel,
        "reasons": reasons,
        "refund_method": order.get("payment_method", "Original payment method"),
        "estimated_refund_days": 5 if can_cancel else 0,
    }


# POST /v1/order/{id}/cancel
@router.post("/v1/order/{order_id}/cancel")
async def cancel_order(order_id: str, body: CancelRequest):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order["fulfillment_status"] not in ("pre_dispatch", "shipped"):
        raise HTTPException(status_code=400, detail="Order cannot be cancelled in current status")

    # Update in-memory order
    order["status"] = "cancelled"
    order["fulfillment_status"] = "cancelled"
    order["cancelled_at"] = datetime.utcnow().isoformat()
    order["cancel_reason"] = body.reason

    return {
        "success": True,
        "order_id": order_id,
        "refund_amount": order["total"],
        "refund_method": order.get("payment_method", "Original payment method"),
        "estimated_refund_days": 5,
        "message": "Order cancelled successfully. Refund will be processed within 5 business days.",
    }


# GET /v1/order/{id}/return-options
@router.get("/v1/order/{order_id}/return-options")
async def return_options(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    can_return = order["fulfillment_status"] == "delivered"
    # Check if within return window (7 days)
    if can_return and order.get("delivered_at"):
        delivered = datetime.fromisoformat(order["delivered_at"])
        if (datetime.utcnow() - delivered).days > 7:
            can_return = False

    reasons = []
    if can_return:
        reasons = [
            "Product not as expected",
            "Wrong size/color",
            "Defective product",
            "Changed my mind",
            "Other",
        ]

    return {
        "order_id": order_id,
        "can_return": can_return,
        "return_window_days": 7,
        "reasons": reasons,
        "items": [
            {"product_id": item["product_id"], "name": item["name"], "returnable": can_return}
            for item in order["items"]
        ],
    }


# POST /v1/order/{id}/return
@router.post("/v1/order/{order_id}/return")
async def initiate_return(order_id: str, body: ReturnRequest):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order["fulfillment_status"] != "delivered":
        raise HTTPException(status_code=400, detail="Only delivered orders can be returned")

    order["status"] = "return_initiated"
    order["fulfillment_status"] = "return_initiated"
    order["return_status"] = "pickup_scheduled"
    order["return_reason"] = body.reason
    order["return_pickup_date"] = (datetime.utcnow() + timedelta(days=2)).isoformat()
    order["refund_status"] = "pending"

    return {
        "success": True,
        "order_id": order_id,
        "return_id": f"RET-{uuid.uuid4().hex[:8].upper()}",
        "pickup_date": order["return_pickup_date"],
        "refund_amount": order["total"],
        "estimated_refund_days": 7,
        "message": "Return initiated. Pickup will be scheduled within 2 days.",
    }


# GET /v1/order/{id}/exchange-options
@router.get("/v1/order/{order_id}/exchange-options")
async def exchange_options(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    can_exchange = order["fulfillment_status"] == "delivered"
    if can_exchange and order.get("delivered_at"):
        delivered = datetime.fromisoformat(order["delivered_at"])
        if (datetime.utcnow() - delivered).days > 7:
            can_exchange = False

    available_variants = []
    if can_exchange:
        for item in order["items"]:
            product = PRODUCTS.get(item["product_id"])
            if product:
                for v in product["variants"]:
                    if v["variant_id"] != item["variant_id"]:
                        available_variants.append({
                            "variant_id": v["variant_id"],
                            "product_name": product["name"],
                            "size": v.get("size", ""),
                            "color": v.get("color", ""),
                            "price": v["price"],
                            "differential_amount": v["price"] - item["price"],
                        })

    return {
        "order_id": order_id,
        "can_exchange": can_exchange,
        "exchange_window_days": 7,
        "current_items": order["items"],
        "available_variants": available_variants,
    }


# POST /v1/order/{id}/exchange
@router.post("/v1/order/{order_id}/exchange")
async def initiate_exchange(order_id: str, body: ExchangeRequest):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order["fulfillment_status"] != "delivered":
        raise HTTPException(status_code=400, detail="Only delivered orders can be exchanged")

    differential = 0.0
    if body.new_variant_id:
        for item in order["items"]:
            product = PRODUCTS.get(item["product_id"])
            if product:
                for v in product["variants"]:
                    if v["variant_id"] == body.new_variant_id:
                        differential = v["price"] - item["price"]
                        break

    exchange_id = f"EXC-{uuid.uuid4().hex[:8].upper()}"

    return {
        "success": True,
        "order_id": order_id,
        "exchange_id": exchange_id,
        "new_variant_id": body.new_variant_id,
        "differential_amount": differential,
        "pickup_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
        "message": "Exchange initiated. Pickup will be scheduled within 2 days.",
    }

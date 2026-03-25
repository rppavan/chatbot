"""
Seed data for the dummy API service.
Provides in-memory users, orders, and products for testing the chatbot.
"""
import copy
from datetime import datetime, timedelta


# ─── Products ───────────────────────────────────────────────────────────────
PRODUCTS = {
    "prod-1001": {
        "id": "prod-1001",
        "name": "Classic White Sneakers",
        "brand": "UrbanStep",
        "price": 2499.00,
        "currency": "INR",
        "variants": [
            {"variant_id": "var-1001-a", "size": "8", "color": "White", "price": 2499.00},
            {"variant_id": "var-1001-b", "size": "9", "color": "White", "price": 2499.00},
            {"variant_id": "var-1001-c", "size": "9", "color": "Black", "price": 2699.00},
        ],
        "image_url": "https://example.com/images/white-sneakers.jpg",
        "category": "Footwear",
    },
    "prod-1002": {
        "id": "prod-1002",
        "name": "Slim Fit Denim Jeans",
        "brand": "DenimCo",
        "price": 1899.00,
        "currency": "INR",
        "variants": [
            {"variant_id": "var-1002-a", "size": "32", "color": "Blue", "price": 1899.00},
            {"variant_id": "var-1002-b", "size": "34", "color": "Blue", "price": 1899.00},
            {"variant_id": "var-1002-c", "size": "32", "color": "Black", "price": 1999.00},
        ],
        "image_url": "https://example.com/images/denim-jeans.jpg",
        "category": "Clothing",
    },
    "prod-1003": {
        "id": "prod-1003",
        "name": "Wireless Bluetooth Earbuds",
        "brand": "SoundWave",
        "price": 3499.00,
        "currency": "INR",
        "variants": [
            {"variant_id": "var-1003-a", "color": "Black", "price": 3499.00},
            {"variant_id": "var-1003-b", "color": "White", "price": 3499.00},
        ],
        "image_url": "https://example.com/images/earbuds.jpg",
        "category": "Electronics",
    },
}


# ─── Users ──────────────────────────────────────────────────────────────────
USERS = {
    "user-001": {
        "id": "user-001",
        "name": "Priya Sharma",
        "email": "priya.sharma@example.com",
        "phone": "+919876543210",
        "is_registered": True,
        "addresses": [
            {
                "id": "addr-001",
                "label": "Home",
                "line1": "42, MG Road",
                "line2": "Koramangala",
                "city": "Bangalore",
                "state": "Karnataka",
                "pincode": "560034",
                "is_default": True,
            },
            {
                "id": "addr-002",
                "label": "Office",
                "line1": "WeWork, Embassy Golf Links",
                "line2": "Domlur",
                "city": "Bangalore",
                "state": "Karnataka",
                "pincode": "560071",
                "is_default": False,
            },
        ],
        "wallet_balance": 450.00,
    },
    "user-002": {
        "id": "user-002",
        "name": "Rahul Mehta",
        "email": "rahul.mehta@example.com",
        "phone": "+919876543211",
        "is_registered": True,
        "addresses": [
            {
                "id": "addr-003",
                "label": "Home",
                "line1": "15, Park Street",
                "line2": "",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400001",
                "is_default": True,
            }
        ],
        "wallet_balance": 1200.00,
    },
    "user-003": {
        "id": "user-003",
        "name": "Ananya Gupta",
        "email": "ananya.gupta@example.com",
        "phone": "+919876543212",
        "is_registered": True,
        "addresses": [
            {
                "id": "addr-004",
                "label": "Home",
                "line1": "7, Janpath",
                "line2": "Connaught Place",
                "city": "New Delhi",
                "state": "Delhi",
                "pincode": "110001",
                "is_default": True,
            }
        ],
        "wallet_balance": 0.00,
    },
}

# Phone → user_id lookup
PHONE_TO_USER = {u["phone"]: uid for uid, u in USERS.items()}

# OTP store: phone → { otp, verified, user_id, token }
OTP_STORE: dict = {}


# ─── Orders ─────────────────────────────────────────────────────────────────
now = datetime.utcnow()

ORDERS = {
    # Pre-dispatch (preparing)
    "ORD-10001": {
        "id": "ORD-10001",
        "user_id": "user-001",
        "status": "preparing",
        "fulfillment_status": "pre_dispatch",
        "created_at": (now - timedelta(hours=6)).isoformat(),
        "updated_at": (now - timedelta(hours=1)).isoformat(),
        "items": [
            {
                "product_id": "prod-1001",
                "variant_id": "var-1001-a",
                "name": "Classic White Sneakers (Size 8, White)",
                "quantity": 1,
                "price": 2499.00,
            }
        ],
        "total": 2499.00,
        "currency": "INR",
        "shipping_address": USERS["user-001"]["addresses"][0],
        "payment_method": "UPI",
        "awb": None,
        "courier": None,
    },
    # Shipped / In-transit
    "ORD-10002": {
        "id": "ORD-10002",
        "user_id": "user-001",
        "status": "shipped",
        "fulfillment_status": "shipped",
        "created_at": (now - timedelta(days=2)).isoformat(),
        "updated_at": (now - timedelta(hours=12)).isoformat(),
        "items": [
            {
                "product_id": "prod-1002",
                "variant_id": "var-1002-a",
                "name": "Slim Fit Denim Jeans (Size 32, Blue)",
                "quantity": 1,
                "price": 1899.00,
            }
        ],
        "total": 1899.00,
        "currency": "INR",
        "shipping_address": USERS["user-001"]["addresses"][0],
        "payment_method": "Credit Card",
        "awb": "AWB123456789",
        "courier": "BlueDart",
    },
    # Out for delivery
    "ORD-10003": {
        "id": "ORD-10003",
        "user_id": "user-002",
        "status": "out_for_delivery",
        "fulfillment_status": "out_for_delivery",
        "created_at": (now - timedelta(days=3)).isoformat(),
        "updated_at": (now - timedelta(hours=2)).isoformat(),
        "items": [
            {
                "product_id": "prod-1003",
                "variant_id": "var-1003-a",
                "name": "Wireless Bluetooth Earbuds (Black)",
                "quantity": 1,
                "price": 3499.00,
            }
        ],
        "total": 3499.00,
        "currency": "INR",
        "shipping_address": USERS["user-002"]["addresses"][0],
        "payment_method": "Net Banking",
        "awb": "AWB987654321",
        "courier": "Delhivery",
    },
    # Delivered
    "ORD-10004": {
        "id": "ORD-10004",
        "user_id": "user-002",
        "status": "delivered",
        "fulfillment_status": "delivered",
        "created_at": (now - timedelta(days=5)).isoformat(),
        "updated_at": (now - timedelta(days=1)).isoformat(),
        "delivered_at": (now - timedelta(days=1)).isoformat(),
        "items": [
            {
                "product_id": "prod-1001",
                "variant_id": "var-1001-b",
                "name": "Classic White Sneakers (Size 9, White)",
                "quantity": 1,
                "price": 2499.00,
            }
        ],
        "total": 2499.00,
        "currency": "INR",
        "shipping_address": USERS["user-002"]["addresses"][0],
        "payment_method": "UPI",
        "awb": "AWB111222333",
        "courier": "BlueDart",
    },
    # Cancelled
    "ORD-10005": {
        "id": "ORD-10005",
        "user_id": "user-003",
        "status": "cancelled",
        "fulfillment_status": "cancelled",
        "created_at": (now - timedelta(days=7)).isoformat(),
        "updated_at": (now - timedelta(days=6)).isoformat(),
        "cancelled_at": (now - timedelta(days=6)).isoformat(),
        "items": [
            {
                "product_id": "prod-1002",
                "variant_id": "var-1002-b",
                "name": "Slim Fit Denim Jeans (Size 34, Blue)",
                "quantity": 1,
                "price": 1899.00,
            }
        ],
        "total": 1899.00,
        "currency": "INR",
        "shipping_address": USERS["user-003"]["addresses"][0],
        "payment_method": "COD",
        "refund_status": "processed",
        "refund_amount": 1899.00,
        "refund_date": (now - timedelta(days=4)).isoformat(),
        "awb": None,
        "courier": None,
    },
    # Return initiated
    "ORD-10006": {
        "id": "ORD-10006",
        "user_id": "user-003",
        "status": "return_initiated",
        "fulfillment_status": "return_initiated",
        "created_at": (now - timedelta(days=10)).isoformat(),
        "updated_at": (now - timedelta(days=2)).isoformat(),
        "delivered_at": (now - timedelta(days=4)).isoformat(),
        "items": [
            {
                "product_id": "prod-1003",
                "variant_id": "var-1003-b",
                "name": "Wireless Bluetooth Earbuds (White)",
                "quantity": 1,
                "price": 3499.00,
            }
        ],
        "total": 3499.00,
        "currency": "INR",
        "shipping_address": USERS["user-003"]["addresses"][0],
        "payment_method": "Credit Card",
        "return_status": "pickup_scheduled",
        "return_pickup_date": (now + timedelta(days=1)).isoformat(),
        "refund_status": "pending",
        "awb": "AWB444555666",
        "courier": "Delhivery",
    },
}


def get_orders_for_user(user_id: str) -> list[dict]:
    """Return all orders for a given user_id."""
    return [copy.deepcopy(o) for o in ORDERS.values() if o["user_id"] == user_id]


def get_orders_by_phone(phone: str) -> list[dict]:
    """Return all orders for a given phone number."""
    user_id = PHONE_TO_USER.get(phone)
    if not user_id:
        return []
    return get_orders_for_user(user_id)

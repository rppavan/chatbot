"""
ChatServiceBackend — direct Shopify + Clickpost integration for production tenants.

Ports the business logic from chat-service-js directly into Python:
  src/order/service/order.service.ts  — order fetching + transformation
  src/user/service/user.service.ts    — user lookup

No HTTP hop to chat-service-js. This backend calls Shopify GraphQL and
Clickpost APIs directly, normalizing responses to the same shape as MockBackend.
"""
import logging

from src.backends.base import BackendAdapter
from src.backends.shopify_client import ShopifyService, _normalize_phone
from src.backends.clickpost_client import (
    ClickpostClient,
    TRACKING_URL_TEMPLATE,
    get_clickpost_carrier_id,
)

logger = logging.getLogger(__name__)


class ChatServiceBackend(BackendAdapter):
    """Backend for Shopify-based tenants (e.g. nobero)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self._tenant_id: str = config.get("tenant_id", "")
        self._shopify = ShopifyService(config)
        self._clickpost = ClickpostClient(
            username=config["clickpost_username"],
            api_key=config["clickpost_api_key"],
        )

    # ── Read operations ────────────────────────────────────────────────────

    async def get_user_by_phone(self, phone: str) -> dict:
        """
        Look up a customer in Shopify by phone number.
        Port of UserService.getUser().
        """
        result = await self._shopify.get_customer_by_phone(phone)
        edges = result.get("customers", {}).get("edges", [])
        if not edges:
            return {}
        node = edges[0]["node"]
        return {
            "user_id": node.get("id", ""),
            "phone": _normalize_phone(
                node.get("defaultPhoneNumber", {}).get("phoneNumber", phone)
            ),
            "email": node.get("email", ""),
            "name": f"{node.get('firstName', '')} {node.get('lastName', '')}".strip(),
        }

    async def search_orders(
        self,
        phone: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """
        Fetch all recent orders for a customer by phone.
        Port of ChatbotOrderService.getAllCustomerOrders().
        """
        if not phone:
            return {"orders": []}

        result = await self._shopify.get_customer_orders_by_phone(phone)
        orders = self._transform_orders(result)
        return {"orders": orders}

    async def get_order(self, order_id: str) -> dict:
        """
        Fetch a single order by its display name (e.g. '#1234').
        Port of ChatbotOrderService.getOrderDetails().
        """
        result = await self._shopify.get_order_by_name(order_id)
        order = result.get("order")
        if not order:
            return {}
        return self._transform_single_order(order)

    async def get_tracking(
        self,
        order_id: str,
        line_item_id: str | None = None,
    ) -> dict:
        """
        Resolve AWB from fulfillment, call Clickpost, return normalized tracking.
        Port of ChatbotOrderService.getOrderTrackingDetails().
        """
        result = await self._shopify.get_order_by_name(order_id)
        order = result.get("order")

        if not order:
            return {}

        # Cancelled orders — return status without tracking
        if order.get("cancelledAt"):
            return {
                "order_status": "Cancelled",
                "display_order_id": order.get("name", ""),
                "order_id": order.get("id", ""),
                "created_at": order.get("createdAt", ""),
                "last_updated_at": order.get("cancelledAt", ""),
            }

        fulfillments = order.get("fulfillments") or []

        # Find the fulfillment containing the requested line item
        awb_number: str | None = None
        if line_item_id:
            for f in fulfillments:
                for edge in f.get("fulfillmentLineItems", {}).get("edges", []):
                    if edge.get("node", {}).get("lineItem", {}).get("id") == line_item_id:
                        awb_number = (f.get("trackingInfo") or [{}])[0].get("number")
                        break
                if awb_number:
                    break

        if not awb_number and fulfillments:
            awb_number = (fulfillments[0].get("trackingInfo") or [{}])[0].get("number")

        if not awb_number:
            return {}

        # Find shipping company for this AWB
        shipping_company = ""
        for f in fulfillments:
            for info in f.get("trackingInfo") or []:
                if info.get("number") == awb_number:
                    shipping_company = info.get("company", "")
                    break

        if not shipping_company:
            logger.warning("No shipping company found for AWB %s (order %s)", awb_number, order_id)
            return {}

        cp_id = get_clickpost_carrier_id(shipping_company)
        if cp_id is None:
            logger.warning(
                "Unsupported shipping provider '%s' for order %s", shipping_company, order_id
            )
            return {}

        tracking_response = await self._clickpost.track_order(awb_number, cp_id)
        if not tracking_response or not tracking_response.get("result"):
            return {}

        tracking_result = tracking_response["result"].get(awb_number)
        if not tracking_result or not tracking_result.get("valid"):
            return {}

        latest = tracking_result.get("latest_status") or {}
        additional = tracking_result.get("additional") or {}
        tracking_url = (
            TRACKING_URL_TEMPLATE.format(tenant_id=self._tenant_id) + awb_number
        )

        return {
            "awb_number": awb_number,
            "order_status": latest.get("status", ""),
            "clickpost_status_code": latest.get("clickpost_status_code", ""),
            "clickpost_status_bucket": latest.get("clickpost_status_bucket", ""),
            "clickpost_status_bucket_description": latest.get(
                "clickpost_status_bucket_description", ""
            ),
            "display_order_id": order.get("name", ""),
            "order_id": order.get("id", ""),
            "tracking_url": tracking_url,
            "edd": additional.get("courier_partner_edd", ""),
            "timestamp": latest.get("timestamp", ""),
            "last_updated_at": latest.get("created_at") or latest.get("timestamp", ""),
            "created_at": order.get("createdAt", ""),
        }

    # ── Write operations (not yet supported for Shopify tenants) ──────────

    async def get_cancel_options(self, order_id: str) -> dict:
        raise NotImplementedError("Cancel not supported for Shopify tenants yet")

    async def cancel_order(self, order_id: str, reason: str) -> dict:
        raise NotImplementedError("Cancel not supported for Shopify tenants yet")

    async def get_return_options(self, order_id: str) -> dict:
        raise NotImplementedError("Return not supported for Shopify tenants yet")

    async def initiate_return(self, order_id: str, reason: str) -> dict:
        raise NotImplementedError("Return not supported for Shopify tenants yet")

    async def get_exchange_options(self, order_id: str) -> dict:
        raise NotImplementedError("Exchange not supported for Shopify tenants yet")

    async def initiate_exchange(
        self, order_id: str, new_variant_id: str, reason: str
    ) -> dict:
        raise NotImplementedError("Exchange not supported for Shopify tenants yet")

    # ── Transformation helpers (port of order.service.ts private methods) ─

    def _transform_orders(self, result: dict) -> list[dict]:
        """Port of transformOrdersResponse()."""
        edges = result.get("orders", {}).get("edges") or []
        return [self._transform_single_order(edge["node"]) for edge in edges]

    def _transform_single_order(self, order: dict) -> dict:
        """
        Flatten a Shopify order GraphQL node into a normalized dict.
        Port of transformSingleOrder().
        """
        awb_map = self._build_line_item_awb_map(order.get("fulfillments") or [])

        line_items = [
            {
                "image_url": edge["node"].get("image", {}).get("url", "") if edge["node"].get("image") else "",
                "title": edge["node"].get("title", ""),
                "awb_number": awb_map.get(edge["node"].get("id", ""), ""),
                "line_item_id": edge["node"].get("id", ""),
            }
            for edge in (order.get("lineItems", {}).get("edges") or [])
        ]

        shipping_amount = float(
            (order.get("shippingLine") or {})
            .get("discountedPriceSet", {})
            .get("presentmentMoney", {})
            .get("amount", 0) or 0
        )
        shipping_method = (
            "Shipping Charges Applied"
            if shipping_amount != 0
            else (order.get("shippingLine") or {}).get("title", "")
        )

        total_amount = float(
            order.get("totalPriceSet", {})
            .get("presentmentMoney", {})
            .get("amount", 0) or 0
        )

        # Map to the same fields the mock API returns so nodes work unchanged
        return {
            "id": order.get("name", ""),           # display order ID (e.g. '#1234')
            "display_order_id": order.get("name", ""),
            "order_id": order.get("id", ""),        # Shopify GID
            "fulfillment_status": self._map_fulfillment_status(order),
            "status": self._map_fulfillment_status(order),
            "shipping_charges": shipping_amount,
            "shipping_method": shipping_method,
            "total": total_amount,
            "total_amount": total_amount,
            "created_at": order.get("createdAt", ""),
            "line_items_count": len(line_items),
            "lineItems": line_items,
            "first_item_name": line_items[0]["title"] if line_items else "",
        }

    def _build_line_item_awb_map(self, fulfillments: list) -> dict[str, str]:
        """
        Build {line_item_id: awb_number} from fulfillments.
        Port of buildLineItemAwbMap().
        """
        awb_map: dict[str, str] = {}
        for fulfillment in fulfillments:
            tracking_number = (
                (fulfillment.get("trackingInfo") or [{}])[0].get("number", "")
            )
            for edge in fulfillment.get("fulfillmentLineItems", {}).get("edges") or []:
                line_item_id = edge.get("node", {}).get("lineItem", {}).get("id")
                if line_item_id and tracking_number:
                    awb_map[line_item_id] = tracking_number
        return awb_map

    def _map_fulfillment_status(self, order: dict) -> str:
        """
        Map Shopify fulfillment state to the status values expected by chatbot nodes.
        """
        if order.get("cancelledAt"):
            return "cancelled"

        fulfillments = order.get("fulfillments") or []
        if not fulfillments:
            return "pre_dispatch"

        # Use the last fulfillment's tracking info to infer status
        # Clickpost status buckets: Pending, In Transit, Out for Delivery, Delivered, etc.
        # For order listing (before tracking is called) we infer from presence of fulfillment
        return "shipped"

"""
Shopify GraphQL client — ported from chat-service-js.

Sources:
  src/shopify/services/shopify.service.ts   — retry logic
  src/shopify/services/common.service.ts    — query methods
  src/shopify/constants/query.ts            — GraphQL queries
  src/common/utils/index.ts                 — phone normalization
"""
import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime, timedelta

import httpx

from src.config import ORDERS_MONTHS_LIMIT

logger = logging.getLogger(__name__)

# ── Retry config (ported from src/shopify/constants/index.ts) ─────────────────
_MAX_RETRIES = 3
_BASE_DELAY_MS = 500
_MAX_DELAY_MS = 10_000
_TOTAL_TIMEOUT_MS = 30_000

# ── GraphQL queries (ported from src/shopify/constants/query.ts) ──────────────
SHOPIFY_CUSTOMER_BY_PHONE_QUERY = """
query($query: String!) {
  customers(first: 50, query: $query) {
    edges {
      node {
        id
        email
        defaultPhoneNumber {
          phoneNumber
        }
        firstName
        lastName
      }
    }
  }
}"""

SHOPIFY_ORDERS_QUERY = """
query($first: Int!, $query: String!) {
  orders(first: $first, query: $query, sortKey: CREATED_AT, reverse: true) {
    edges {
      node {
        id
        name
        createdAt
        cancelledAt
        totalPriceSet {
          presentmentMoney {
            amount
            currencyCode
          }
        }
        shippingLine {
          title
          discountedPriceSet {
            presentmentMoney {
              amount
            }
          }
        }
        lineItems(first: 50) {
          edges {
            node {
              id
              title
              quantity
              image {
                url
              }
            }
          }
        }
        fulfillments(first: 10) {
          trackingInfo {
            number
            company
          }
          fulfillmentLineItems(first: 50) {
            edges {
              node {
                lineItem {
                  id
                }
              }
            }
          }
        }
      }
    }
  }
}"""


def _normalize_phone(phone: str) -> str:
    """Strip non-digits, return last 10 digits. Port of normalizePhoneNumber()."""
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else digits


def _is_retryable_status(status_code: int) -> bool:
    return status_code in (408, 429, 500, 502, 503, 504)


class ShopifyClient:
    """
    Async Shopify GraphQL client with exponential backoff retry.
    Port of ShopifyService.executeWithRetry() from shopify.service.ts.
    """

    def __init__(self, shop_name: str, access_token: str):
        self._url = f"https://{shop_name}/admin/api/2026-01/graphql.json"
        self._headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }

    async def graphql(self, query: str, variables: dict) -> dict:
        last_exc: Exception | None = None
        start = time.monotonic()

        for attempt in range(_MAX_RETRIES):
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms >= _TOTAL_TIMEOUT_MS:
                raise TimeoutError(
                    f"Shopify request timed out after {elapsed_ms:.0f}ms"
                )

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        self._url,
                        headers=self._headers,
                        content=json.dumps({"query": query, "variables": variables}),
                    )

                if resp.status_code >= 400 and not _is_retryable_status(resp.status_code):
                    resp.raise_for_status()

                if _is_retryable_status(resp.status_code):
                    raise httpx.HTTPStatusError(
                        f"Shopify returned {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                if attempt > 0:
                    logger.info("Shopify request succeeded on attempt %d/%d", attempt + 1, _MAX_RETRIES)

                return resp.json()

            except Exception as exc:
                last_exc = exc
                is_last = attempt == _MAX_RETRIES - 1

                logger.warning(
                    "Shopify request failed attempt %d/%d: %s",
                    attempt + 1, _MAX_RETRIES, exc,
                )

                if is_last:
                    break

                delay_ms = self._backoff_delay(attempt)
                time_remaining_ms = _TOTAL_TIMEOUT_MS - (time.monotonic() - start) * 1000
                if delay_ms >= time_remaining_ms:
                    logger.warning("Skipping retry delay — would exceed total timeout")
                    break

                await asyncio.sleep(delay_ms / 1000)

        logger.error("Shopify request failed after %d attempts", _MAX_RETRIES)
        raise last_exc or RuntimeError("Shopify request failed with unknown error")

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with 0–25% jitter. Port of calculateDelayWithExponentialBackoff()."""
        delay = _BASE_DELAY_MS * (2 ** attempt)
        delay = min(delay, _MAX_DELAY_MS)
        jitter = random.uniform(0, delay * 0.25)
        return delay + jitter


class ShopifyService:
    """
    Per-tenant Shopify query methods.
    Port of CommonShopifyService from common.service.ts.
    """

    def __init__(self, config: dict):
        self._client = ShopifyClient(
            shop_name=config["shopify_shop_name"],
            access_token=config["shopify_access_token"],
        )
        self._months_limit = ORDERS_MONTHS_LIMIT

    async def get_customer_by_phone(self, phone: str) -> dict:
        """
        Query Shopify for customers by phone, then filter by normalized match.
        Port of getCustomerByPhone().
        """
        result = await self._client.graphql(
            SHOPIFY_CUSTOMER_BY_PHONE_QUERY,
            {"query": f"phone:{phone}"},
        )
        customers = result.get("data", result).get("customers", {}).get("edges", [])
        normalized_search = _normalize_phone(phone)

        matched = next(
            (
                edge
                for edge in customers
                if _normalize_phone(
                    edge["node"].get("defaultPhoneNumber", {}).get("phoneNumber", "")
                ) == normalized_search
            ),
            None,
        )

        return {"customers": {"edges": [matched] if matched else []}}

    async def get_customer_orders_by_phone(self, phone: str) -> dict:
        """
        Look up customer ID by phone, then fetch their orders.
        Port of getCustomerOrdersByPhone().
        """
        customer_result = await self.get_customer_by_phone(phone)
        edges = customer_result.get("customers", {}).get("edges", [])
        if not edges:
            return {"orders": {"edges": []}}

        customer = edges[0]["node"]
        customer_id = customer["id"].split("/")[-1]

        cutoff = (datetime.utcnow() - timedelta(days=self._months_limit * 30)).strftime("%Y-%m-%d")

        result = await self._client.graphql(
            SHOPIFY_ORDERS_QUERY,
            {
                "first": 50,
                "query": f"customer_id:{customer_id} created_at:>={cutoff}",
            },
        )
        return result.get("data", result)

    async def get_order_by_name(self, order_name: str) -> dict:
        """
        Fetch a single order by its display name (e.g. '#1234').
        Port of getOrderByName().
        """
        result = await self._client.graphql(
            SHOPIFY_ORDERS_QUERY,
            {"first": 1, "query": f"name:{order_name}"},
        )
        data = result.get("data", result)
        order = (data.get("orders", {}).get("edges") or [{}])[0].get("node")
        return {"order": order}

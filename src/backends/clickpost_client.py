"""
Clickpost tracking client — ported from chat-service-js.

Sources:
  src/clickpost/services/clickpost.service.ts    — HTTP client
  src/clickpost/constants/carrier-mapping.ts     — carrier ID mapping
  src/clickpost/constants/index.ts               — API config, tracking URL
"""
import logging

import httpx

logger = logging.getLogger(__name__)

CLICKPOST_BASE_URL = "https://api.clickpost.in/api/v2"
CLICKPOST_TRACK_ENDPOINT = "/track-order/"
TRACKING_URL_TEMPLATE = "https://{tenant_id}.clickpost.ai/en?waybill="

# Port of CLICKPOST_CARRIER_MAPPING from carrier-mapping.ts
CARRIER_MAPPING: dict[str, int] = {
    "aramex int": 2,
    "aramex": 2,
    "ecomexpress": 3,
    "ecom express": 3,
    "delhivery": 4,
    "bluedart": 5,
    "blue dart": 5,
    "xpressbees": 6,
    "xpress bees": 6,
    "dtdc": 8,
    "blitz": 207,
    "grow simplee": 207,
    "shadowfax reverse": 11,
    "proship b2c reverse": 367,
    "delhivery reverse": 25,
    "proship b2c": 329,
    "proship": 329,
    "shadowfax": 9,
    "ecomexpress reverse": 24,
    "ecom express reverse": 24,
    "ekart": 55,
    "ekart logistics": 55,
    "fedex": 1,
    "fedex india": 1,
}


def get_clickpost_carrier_id(company_name: str) -> int | None:
    """
    Map a Shopify shipping company name to a Clickpost cp_id.
    Port of getClickpostCarrierId() from carrier-mapping.ts.

    Lookup order:
    1. Exact match (normalized)
    2. Longest substring of company_name that matches a key
    3. Any key that is a substring of company_name (reverse fallback)
    """
    if not company_name:
        return None

    normalized = company_name.lower().strip()

    # Exact match
    if normalized in CARRIER_MAPPING:
        return CARRIER_MAPPING[normalized]

    # Longest key that is a substring of the company name
    longest_key: str | None = None
    for key in CARRIER_MAPPING:
        if key in normalized:
            if longest_key is None or len(key) > len(longest_key):
                longest_key = key
    if longest_key:
        return CARRIER_MAPPING[longest_key]

    # Reverse: company name as substring of a key
    for key, value in CARRIER_MAPPING.items():
        if normalized in key:
            return value

    return None


class ClickpostClient:
    """
    HTTP client for the Clickpost tracking API.
    Port of ClickpostService from clickpost.service.ts.
    """

    def __init__(self, username: str, api_key: str):
        self._username = username
        self._api_key = api_key

    async def track_order(self, awb_number: str, cp_id: int) -> dict | None:
        """
        GET /api/v2/track-order/ with waybill, cp_id, username, key params.
        Returns the parsed JSON or None on error.
        """
        params = {
            "username": self._username,
            "key": self._api_key,
            "waybill": awb_number,
            "cp_id": str(cp_id),
        }

        logger.info("Calling Clickpost track order API for AWB: %s, cp_id: %d", awb_number, cp_id)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{CLICKPOST_BASE_URL}{CLICKPOST_TRACK_ENDPOINT}",
                    params=params,
                    headers={"Content-Type": "application/json"},
                )

            if not resp.is_success:
                logger.error("Clickpost API returned error status: %d", resp.status_code)
                return None

            data = resp.json()

            if not data.get("meta", {}).get("success"):
                logger.error("Clickpost API returned failure: %s", data.get("meta", {}).get("message"))
                return None

            return data

        except Exception as exc:
            logger.exception("Clickpost trackOrder failed for AWB %s: %s", awb_number, exc)
            raise

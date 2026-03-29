"""
BackendAdapter — abstract interface all backends must implement.
"""
from abc import ABC, abstractmethod


class BackendAdapter(ABC):
    """
    Abstract base class for all backend implementations.

    Read operations are abstract — every backend must implement them.
    Write operations default to NotImplementedError — backends opt in.
    """

    def __init__(self, config: dict):
        self._config = config

    # ── Read operations (all backends must implement) ──────────────────────

    @abstractmethod
    async def get_user_by_phone(self, phone: str) -> dict:
        """Return user dict with at least {user_id, phone, email} or empty dict."""
        ...

    @abstractmethod
    async def search_orders(
        self,
        phone: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Return {"orders": [...]}."""
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> dict:
        """Return full order dict or empty dict if not found."""
        ...

    @abstractmethod
    async def get_tracking(
        self,
        order_id: str,
        line_item_id: str | None = None,
    ) -> dict:
        """Return tracking dict or empty dict."""
        ...

    # ── Write operations (opt-in) ──────────────────────────────────────────

    async def get_cancel_options(self, order_id: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support cancel options")

    async def cancel_order(self, order_id: str, reason: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support order cancellation")

    async def get_return_options(self, order_id: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support return options")

    async def initiate_return(self, order_id: str, reason: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support return initiation")

    async def get_exchange_options(self, order_id: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support exchange options")

    async def initiate_exchange(
        self, order_id: str, new_variant_id: str, reason: str
    ) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support exchange initiation")

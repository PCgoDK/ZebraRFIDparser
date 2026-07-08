from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class StorageAdapter(ABC):
    """Interface for all storage backends."""

    @abstractmethod
    def connect(self) -> None:
        """Initialize connections or resources required by the backend."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release backend resources."""
        raise NotImplementedError

    @abstractmethod
    def store_event(self, event: Dict[str, Any]) -> None:
        """Persist a single RFID event."""
        raise NotImplementedError

"""HTTP client for the Go trading core API."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_BASE_URL = os.environ.get("TRADER_API_URL", "http://localhost:8080")


class TraderClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def account(self) -> dict[str, Any]:
        resp = requests.get(f"{self.base_url}/api/v1/account", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def positions(self) -> list[dict[str, Any]]:
        resp = requests.get(f"{self.base_url}/api/v1/positions", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def send_signal(
        self,
        symbol: str,
        action: str,
        confidence: float = 0.5,
        volume: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
        }
        if volume is not None:
            payload["volume"] = volume

        resp = requests.post(
            f"{self.base_url}/api/v1/signals",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def risk_status(self) -> dict[str, Any]:
        resp = requests.get(f"{self.base_url}/api/v1/risk/status", timeout=5)
        resp.raise_for_status()
        return resp.json()

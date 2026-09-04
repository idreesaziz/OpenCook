from pathlib import Path

import httpx

from opencook.availability import AvailabilityGateway
from opencook.stock import SQLiteStock


def test_verified_offer_becomes_versioned_stock_snapshot(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert "inchikey" in body
        return httpx.Response(
            200,
            json={
                "state": "orderable_observed",
                "terminal": True,
                "confidence": 0.9,
                "reasons": ["fresh exact offer"],
                "evaluated_at": "2026-09-05T00:00:00Z",
                "observations": [{"id": "obs-1", "offer_url": "https://merchant.example/item"}],
                "provider_errors": {},
            },
        )

    stock = SQLiteStock(tmp_path / "stock.sqlite")
    gateway = AvailabilityGateway("https://evidence.example", transport=httpx.MockTransport(handler))
    result = gateway.verify_into_snapshot(
        stock, "CCO", country="US", supplied_urls=["https://merchant.example/item"]
    )
    assert result.terminal and result.imported
    assert stock.contains("CCO")
    assert stock.version.startswith("availevidence-0.1:US:ordinary_individual:")


def test_unknown_offer_does_not_enter_stock(tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "state": "unknown",
                "terminal": False,
                "confidence": 0,
                "reasons": ["no evidence"],
                "evaluated_at": "2026-09-05T00:00:00Z",
                "observations": [],
                "provider_errors": {},
            },
        )
    )
    stock = SQLiteStock(tmp_path / "stock.sqlite")
    result = AvailabilityGateway(transport=transport).verify_into_snapshot(stock, "CCO", country="US")
    assert not result.terminal and not result.imported
    assert not stock.contains("CCO")

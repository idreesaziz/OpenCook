import os
import time

os.environ["OPENCOOK_NAME_PROVIDER"] = "disabled"
os.environ["OPENCOOK_DATABASE"] = ":memory:"

from fastapi.testclient import TestClient

from opencook import api
from opencook.api import app
from opencook.domain import EvidenceClass, Provenance, Reaction
from opencook.stock import SetStock

client = TestClient(app)


def test_end_to_end_api() -> None:
    normalized = client.post("/api/v1/molecules/normalize", json={"structure": "CC(=O)OCCO"})
    assert normalized.status_code == 200 and normalized.json()["formula"] == "C4H8O3"
    created = client.post("/api/v1/searches", json={"structure": "CC(=O)OCCO"}).json()
    for _ in range(100):
        result = client.get(f"/api/v1/searches/{created['id']}").json()
        if result["status"] == "completed":
            break
        time.sleep(0.01)
    assert len(result["routes"]) >= 2
    assert result["progress"]["stage"] == "search complete"
    assert result["progress"]["recent_reactions"]
    assert result["routes"][0]["root"]["reaction"]["provenance"]
    assert client.get("/api/v1/reactions/fixture-r1").status_code == 200


def test_depiction_is_real_svg() -> None:
    response = client.post("/api/v1/molecules/depict", json={"structure": "c1ccccc1"})
    assert response.status_code == 200 and "<svg" in response.text


def test_name_provider_failure_does_not_discard_routes(monkeypatch: object) -> None:
    def fail(_structure: str) -> None:
        raise TypeError("name service failure")

    monkeypatch.setattr(api.name_provider, "lookup", fail)  # type: ignore[attr-defined]
    routes = [
        {
            "root": {
                "molecule": "CCO",
                "precursors": [],
                "display_name": None,
            }
        }
    ]
    api._enrich_names(routes)
    assert routes[0]["root"]["display_name"] is None


def test_name_enrichment_limit_leaves_additional_nodes_unnamed(monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        api.name_provider, "lookup", lambda _structure: None
    )
    children = [{"molecule": "C" * size, "precursors": [], "display_name": None} for size in range(1, 30)]
    routes = [
        {
            "root": {
                "molecule": "O",
                "precursors": children,
                "display_name": None,
            }
        }
    ]

    api._enrich_names(routes)

    assert all(node["display_name"] is None for node in children)


def test_web_search_checks_unresolved_leaves_and_attaches_evidence(monkeypatch: object) -> None:
    calls: list[str] = []

    def evaluate(smiles: str, **_kwargs: object) -> dict[str, object]:
        calls.append(smiles)
        return {
            "state": "listed_in_stock",
            "terminal": False,
            "confidence": 0.7,
            "reasons": ["candidate listing requires exact merchant verification"],
            "observations": [
                {
                    "id": f"observation-{len(calls)}",
                    "state": "listed_in_stock",
                    "provider": "fixture",
                    "upstream_source": "shopping fixture",
                    "identity_decision": "ambiguous",
                    "identity_reasons": ["no stable product identifier"],
                    "observed_at": "2026-09-05T00:00:00Z",
                    "expires_at": "2026-09-06T00:00:00Z",
                    "warnings": ["verification required"],
                }
            ],
            "provider_errors": {},
        }

    monkeypatch.setattr(api.availability_gateway, "evaluate", evaluate)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        api.availability_gateway, "health", lambda: {"status": "ok"}
    )
    monkeypatch.setattr(api, "stock", SetStock([]))  # type: ignore[attr-defined]
    api.store.put_reaction(
        Reaction(
            "availability-partial-fixture",
            ("CCCCC",),
            "CCCCCC",
            EvidenceClass.EXACT,
            1.0,
            "checked",
            (Provenance("test", "1", "availability", "fixture", "CC0"),),
        )
    )
    created = client.post(
        "/api/v1/searches",
        json={
            "structure": "CCCCCC",
            "availability_enabled": True,
            "availability_country": "US",
            "availability_candidate_limit": 3,
        },
    ).json()
    for _ in range(200):
        result = client.get(f"/api/v1/searches/{created['id']}").json()
        if result["status"] == "completed":
            break
        time.sleep(0.01)

    assert result["status"] == "completed"
    assert result["availability"]["status"] == "completed"
    assert result["availability"]["checked"] == len(calls) > 0
    assert result["availability"]["candidate_listings"] == len(calls)

    def leaves(node: dict[str, object]) -> list[dict[str, object]]:
        children = node["precursors"]
        assert isinstance(children, list)
        result_nodes = [node] if not node["in_stock"] and not node["reaction"] else []
        for child in children:
            assert isinstance(child, dict)
            result_nodes.extend(leaves(child))
        return result_nodes

    unresolved = [leaf for route in result["routes"] for leaf in leaves(route["root"])]
    assert any(leaf.get("availability", {}).get("state") == "listed_in_stock" for leaf in unresolved)


def test_verified_leaf_is_fed_back_until_route_is_complete(monkeypatch: object) -> None:
    leaf = "CCCCCCC"

    def evaluate(smiles: str, **_kwargs: object) -> dict[str, object]:
        terminal = smiles == leaf
        return {
            "state": "listed_in_stock" if terminal else "unknown",
            "terminal": terminal,
            "confidence": 0.95 if terminal else 0.0,
            "reasons": ["verified fixture offer" if terminal else "no offer"],
            "observations": [
                {
                    "id": "verified-heptane-offer",
                    "state": "listed_in_stock",
                    "provider": "fixture",
                    "upstream_source": "merchant fixture",
                    "identity_decision": "exact",
                    "identity_reasons": ["exact identity"],
                    "observed_at": "2026-09-05T00:00:00Z",
                    "expires_at": "2026-09-06T00:00:00Z",
                    "warnings": [],
                }
            ] if terminal else [],
            "provider_errors": {},
        }

    monkeypatch.setattr(api.availability_gateway, "evaluate", evaluate)  # type: ignore[attr-defined]
    monkeypatch.setattr(api.availability_gateway, "health", lambda: {"status": "ok"})  # type: ignore[attr-defined]
    monkeypatch.setattr(api, "stock", SetStock(["C"]))  # type: ignore[attr-defined]
    api.store.put_reaction(
        Reaction(
            "purchase-directed-fixture",
            (leaf,),
            "CCCCCCCC",
            EvidenceClass.EXACT,
            1.0,
            "checked",
            (Provenance("test", "1", "purchase-directed", "fixture", "CC0"),),
        )
    )
    created = client.post(
        "/api/v1/searches",
        json={
            "structure": "CCCCCCCC",
            "availability_enabled": True,
            "availability_country": "US",
            "availability_max_rounds": 2,
            "max_depth": 4,
        },
    ).json()
    for _ in range(200):
        result = client.get(f"/api/v1/searches/{created['id']}").json()
        if result["status"] == "completed":
            break
        time.sleep(0.01)

    assert result["routes"][0]["complete"] is True
    assert result["routes"][0]["root"]["precursors"][0]["in_stock"] is True
    assert result["routes"][0]["root"]["precursors"][0]["availability"]["terminal"] is True
    assert result["availability"]["rounds_completed"] == 2
    assert "availability:US:ordinary_individual" in result["reproducibility"]["stock_version"]

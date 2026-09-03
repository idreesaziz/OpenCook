import os
import time

os.environ["OPENCOOK_NAME_PROVIDER"] = "disabled"
os.environ["OPENCOOK_DATABASE"] = ":memory:"

from fastapi.testclient import TestClient

from opencook import api
from opencook.api import app

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
    children = [
        {"molecule": "C" * size, "precursors": [], "display_name": None}
        for size in range(1, 30)
    ]
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

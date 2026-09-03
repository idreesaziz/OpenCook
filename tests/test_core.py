from opencook.chemistry import MoleculeError, normalize
from opencook.domain import EvidenceClass, Provenance, Reaction
from opencook.runtime import ROOT, demo_runtime
from opencook.search import BestFirstPlanner, SearchConfig
from opencook.stock import SetStock
from opencook.store import ReactionStore, load_fixture


def test_normalization_preserves_stereochemistry() -> None:
    assert normalize("C[C@H](O)F").smiles != normalize("C[C@@H](O)F").smiles
    assert normalize("CCO").formula == "C2H6O"


def test_invalid_structure() -> None:
    try:
        normalize("not a molecule")
    except MoleculeError:
        pass
    else:
        raise AssertionError("invalid structure accepted")


def test_reverse_index_and_deduplication() -> None:
    store = ReactionStore()
    report = load_fixture(store, ROOT / "data/fixtures/reactions.json")
    assert report == {"records_read": 4, "records_indexed": 4, "records_rejected": 0}
    assert {r.id for r in store.reactions_producing("CC(=O)OCCO")} == {"fixture-r2", "fixture-r3"}


def test_and_cost_requires_all_precursors() -> None:
    store, stock = demo_runtime()
    routes, _ = BestFirstPlanner(store, stock).search("CCOC(C)=O")
    assert routes[0].metrics.stock_leaves == 2
    assert {p.molecule for p in routes[0].root.precursors} == {
        normalize("CCO").smiles,
        normalize("CC(=O)O").smiles,
    }


def test_multistep_routes_complete_cycle_free_and_deterministic() -> None:
    store, stock = demo_runtime()
    planner = BestFirstPlanner(store, stock)
    a, _ = planner.search("CC(=O)OCCO", SearchConfig(routes=5, heuristic="zero"))
    b, _ = planner.search("CC(=O)OCCO", SearchConfig(routes=5, heuristic="zero"))
    assert [r.signature for r in a] == [r.signature for r in b]
    assert len(a) == 2
    assert all("fixture-cycle" not in r.signature for r in a)
    assert all(r.root.precursors for r in a)


def test_cycle_rejected_when_no_other_solution() -> None:
    store = ReactionStore()
    prov = (Provenance("test", "1", "x", "test", "CC0"),)
    store.put_reaction(Reaction("ab", ("CC",), "CCC", EvidenceClass.EXACT, 1, "checked", prov))
    store.put_reaction(Reaction("ba", ("CCC",), "CC", EvidenceClass.EXACT, 1, "checked", prov))
    routes, _ = BestFirstPlanner(store, SetStock([])).search("CCC")
    assert routes == []


def test_stock_target_is_synthesized_by_default() -> None:
    store = ReactionStore()
    prov = (Provenance("test", "1", "x", "test", "CC0"),)
    store.put_reaction(
        Reaction("make", ("CCO", "CC(=O)O"), "CCOC(C)=O", EvidenceClass.EXACT, 1, "checked", prov)
    )
    stock = SetStock(["CCOC(C)=O", "CCO", "CC(=O)O"])

    routes, _ = BestFirstPlanner(store, stock).search("CCOC(C)=O")

    assert routes[0].metrics.transformations == 1
    assert routes[0].root.in_stock is False


def test_deep_search_can_expand_a_stock_intermediate_and_reports_progress() -> None:
    store = ReactionStore()
    prov = (Provenance("test", "1", "x", "test", "CC0"),)
    store.put_reaction(Reaction("outer", ("CCC",), "CCCC", EvidenceClass.EXACT, 1, "checked", prov))
    store.put_reaction(Reaction("inner", ("CC",), "CCC", EvidenceClass.EXACT, 1, "checked", prov))
    events: list[dict[str, object]] = []

    routes, _ = BestFirstPlanner(store, SetStock(["CCC", "CC"])).search(
        "CCCC", SearchConfig(objective="deepest_supported", routes=5), progress=events.append
    )

    assert [route.metrics.longest_linear_sequence for route in routes] == [2, 1]
    assert routes[0].root.precursors[0].in_stock is False
    assert routes[0].root.precursors[0].precursors[0].in_stock is True
    assert events[0]["stage"] == "initializing retrosynthetic search"
    assert events[-1]["stage"] == "search complete"


def test_deep_search_returns_unresolved_direct_reaction_paths() -> None:
    store = ReactionStore()
    prov = (Provenance("test", "1", "x", "test", "CC0"),)
    store.put_reaction(Reaction("solved", ("CC",), "CCCC", EvidenceClass.EXACT, 1, "checked", prov))
    store.put_reaction(Reaction("partial", ("CCC",), "CCCC", EvidenceClass.EXACT, 1, "checked", prov))

    routes, stats = BestFirstPlanner(store, SetStock(["CC"])).search(
        "CCCC", SearchConfig(objective="deepest_supported")
    )

    assert stats.complete_routes == 1
    assert {route.signature for route in routes} == {"solved", "partial"}
    unresolved = next(route for route in routes if not route.complete)
    assert unresolved.metrics.unresolved_leaves == 1

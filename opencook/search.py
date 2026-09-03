from __future__ import annotations

import heapq
import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, cast

from .chemistry import normalize
from .domain import EvidenceClass, Reaction, Route, RouteMetrics, RouteNode
from .expansion import ExpansionProvider, NoExpansionProvider
from .stock import StockProvider
from .store import ReactionStore

EVIDENCE_PENALTY = {
    EvidenceClass.EXACT: 0.0,
    EvidenceClass.ANALOGUE: 0.8,
    EvidenceClass.TEMPLATE: 1.2,
    EvidenceClass.COMPUTATIONAL: 2.0,
}


@dataclass(frozen=True, slots=True)
class SearchConfig:
    max_depth: int = 8
    max_expansions: int = 10_000
    timeout_seconds: float = 30.0
    routes: int = 5
    candidate_limit: int = 50
    objective: str = "best_overall"
    heuristic: str = "complexity"
    allow_target_as_stock: bool = False
    model_fallback: bool = False
    model_candidate_limit: int = 5
    max_model_calls: int = 25
    model_min_heavy_atoms: int = 6


@dataclass(slots=True)
class SearchStats:
    elapsed_seconds: float = 0
    molecules_discovered: int = 0
    reactions_examined: int = 0
    molecules_expanded: int = 0
    frontier_size: int = 0
    complete_routes: int = 0
    termination: str = "complete"
    model_calls: int = 0
    model_reactions_generated: int = 0
    model_failures: int = 0


ProgressCallback = Callable[[dict[str, object]], None]
CancelCallback = Callable[[], bool]


class Planner(Protocol):
    name: str

    def search(
        self, target: str, config: SearchConfig,
        progress: ProgressCallback | None = None, should_cancel: CancelCallback | None = None,
    ) -> tuple[list[Route], SearchStats]: ...


def reaction_cost(r: Reaction) -> float:
    return 1.0 + EVIDENCE_PENALTY[r.evidence] + (1.0 - r.confidence)


def _metrics(root: RouteNode) -> RouteMetrics:
    reactions: list[Reaction] = []
    leaves = unresolved = 0

    def walk(n: RouteNode, depth: int) -> int:
        nonlocal leaves, unresolved
        if n.in_stock:
            leaves += 1
            return depth
        if n.reaction:
            reactions.append(n.reaction)
        elif not n.precursors:
            unresolved += 1
        return max((walk(p, depth + 1) for p in n.precursors), default=depth)

    lls = walk(root, 0)
    conf = sum(r.confidence for r in reactions) / len(reactions) if reactions else 1.0
    evidence = sum(EVIDENCE_PENALTY[r.evidence] for r in reactions)
    total = sum(reaction_cost(r) for r in reactions)
    return RouteMetrics(
        len(reactions), lls, leaves, round(conf, 4), round(evidence, 4), round(total, 4), unresolved
    )


def _signature(root: RouteNode) -> str:
    ids: list[str] = []

    def walk(n: RouteNode) -> None:
        if n.reaction:
            ids.append(n.reaction.id)
        for p in n.precursors:
            walk(p)

    walk(root)
    return "|".join(sorted(ids))


@dataclass(order=True)
class _State:
    priority: float
    serial: int
    root: RouteNode = field(compare=False)
    unresolved: tuple[tuple[tuple[int, ...], tuple[str, ...], int], ...] = field(compare=False)
    cost: float = field(compare=False, default=0)


class BestFirstPlanner:
    """Best-first search over partial AND/OR solution graphs.

    OR choices create successor states; every reactant of the chosen reaction is
    inserted into the same state, preserving AND cost and completion semantics.
    """

    name = "andor_best_first"

    def __init__(
        self,
        store: ReactionStore,
        stock: StockProvider,
        expansion_provider: ExpansionProvider | None = None,
    ) -> None:
        self.store, self.stock = store, stock
        self.expansion_provider = expansion_provider or NoExpansionProvider()

    def _node(self, smiles: str) -> RouteNode:
        in_stock = self.stock.contains(smiles)
        name, sources = self.stock.describe(smiles) if in_stock else (None, ())
        return RouteNode(smiles, in_stock, name, sources)

    @staticmethod
    def _at_path(root: RouteNode, path: tuple[int, ...]) -> RouteNode:
        node = root
        for index in path:
            node = node.precursors[index]
        return node

    def _heuristic(
        self,
        root: RouteNode,
        items: tuple[tuple[tuple[int, ...], tuple[str, ...], int], ...],
        kind: str,
    ) -> float:
        if kind == "zero":
            return 0.0
        return cast(
            float,
            sum(0.08 * normalize(self._at_path(root, path).molecule).heavy_atoms for path, _, _ in items),
        )

    def search(
        self,
        target: str,
        config: SearchConfig | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> tuple[list[Route], SearchStats]:
        config = config or SearchConfig()
        started, counter = time.monotonic(), itertools.count()
        canonical = normalize(target).smiles
        root = self._node(canonical)
        # A purchasable target is not, by default, a synthesis route. Stock only
        # terminates precursor branches unless the caller explicitly opts in.
        initial = () if root.in_stock and config.allow_target_as_stock else (((), (canonical,), 0),)
        queue = [_State(self._heuristic(root, initial, config.heuristic), next(counter), root, initial)]
        results: list[Route] = []
        direct_candidates: dict[str, RouteNode] = {}
        seen_signatures: set[str] = set()
        stats = SearchStats(molecules_discovered=1)
        expansion_cache: dict[str, list[Reaction]] = {}
        unique_reactions: set[str] = set()
        last_progress = 0.0

        def report(stage: str, molecule: str | None = None, depth: int = 0, *, force: bool = False) -> None:
            nonlocal last_progress
            now = time.monotonic()
            if progress is None or (not force and now - last_progress < 0.1):
                return
            last_progress = now
            progress({
                "stage": stage,
                "current_molecule": molecule,
                "current_depth": depth,
                "elapsed_seconds": round(now - started, 3),
                "molecules_discovered": stats.molecules_discovered,
                "molecules_expanded": stats.molecules_expanded,
                "unique_reactions_examined": len(unique_reactions),
                "frontier_size": len(queue),
                "complete_routes_discovered": stats.complete_routes,
                "deepest_complete_route": max(
                    (route.metrics.longest_linear_sequence for route in results), default=0
                ),
                "model_calls": stats.model_calls,
                "model_reactions_generated": stats.model_reactions_generated,
                "model_failures": stats.model_failures,
            })

        report("initializing retrosynthetic search", canonical, force=True)
        while queue and stats.molecules_expanded < config.max_expansions:
            if should_cancel and should_cancel():
                stats.termination = "canceled"
                break
            if time.monotonic() - started >= config.timeout_seconds:
                stats.termination = "timeout"
                break
            state = heapq.heappop(queue)
            if not state.unresolved:
                sig = _signature(state.root)
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    results.append(Route(state.root, _metrics(state.root), sig))
                    stats.complete_routes += 1
                    if config.objective == "deepest_supported":
                        results.sort(
                            key=lambda route: (
                                -route.metrics.longest_linear_sequence,
                                -route.metrics.transformations,
                                route.metrics.total_score,
                                route.signature,
                            )
                        )
                        del results[config.routes:]
                        report("ranking deeper complete routes", force=True)
                    elif len(results) >= config.routes:
                        break
                continue
            current_path, ancestors, depth = state.unresolved[0]
            current = self._at_path(state.root, current_path)
            rest = state.unresolved[1:]
            report("expanding retrosynthetic precursor", current.molecule, depth)
            if config.objective == "deepest_supported" and current.in_stock and current_path:
                # Stopping is one OR alternative; expansion below remains another.
                heapq.heappush(
                    queue,
                    _State(state.cost + self._heuristic(state.root, rest, config.heuristic),
                           next(counter), state.root, rest, state.cost),
                )
            if depth >= config.max_depth:
                continue
            if current.molecule not in expansion_cache:
                expansion_cache[current.molecule] = self.store.reactions_producing(current.molecule)
                if (
                    not expansion_cache[current.molecule]
                    and config.model_fallback
                    and self.expansion_provider.name != "disabled"
                    and stats.model_calls < config.max_model_calls
                    and normalize(current.molecule).heavy_atoms >= config.model_min_heavy_atoms
                ):
                    report(
                        "ORD exhausted; generating model disconnections",
                        current.molecule,
                        depth,
                        force=True,
                    )
                    stats.model_calls += 1
                    try:
                        generated = self.expansion_provider.expand(
                            current.molecule, config.model_candidate_limit
                        )
                    except Exception:
                        stats.model_failures += 1
                        generated = []
                        report(
                            "model expansion failed; preserving unresolved leaf",
                            current.molecule,
                            depth,
                            force=True,
                        )
                    expansion_cache[current.molecule] = generated
                    stats.model_reactions_generated += len(generated)
                unique_reactions.update(reaction.id for reaction in expansion_cache[current.molecule])
            reactions = expansion_cache[current.molecule]
            stats.molecules_expanded += 1
            stats.reactions_examined = len(unique_reactions)
            candidates = reactions if not current_path else reactions[: config.candidate_limit]
            for reaction in candidates:
                precursor_smiles = tuple(normalize(s).smiles for s in reaction.reactants)
                if any(s in ancestors for s in precursor_smiles):
                    continue
                # Clone the partial tree so OR alternatives never mutate each other.
                import copy

                new_root = copy.deepcopy(state.root)
                selected = self._at_path(new_root, current_path)
                # A requested synthesis is not a terminal stock leaf, even when
                # the same compound is commercially available.
                selected.in_stock = False
                selected.reaction = reaction
                selected.precursors = [self._node(s) for s in precursor_smiles]
                if not current_path:
                    direct_candidates[reaction.id] = copy.deepcopy(new_root)
                pending: list[tuple[tuple[int, ...], tuple[str, ...], int]] = []
                for index, child in enumerate(selected.precursors):
                    if config.objective == "deepest_supported" or not child.in_stock:
                        pending.append((current_path + (index,), ancestors + (child.molecule,), depth + 1))
                pending.extend(rest)
                unresolved = tuple(pending)
                cost = state.cost + reaction_cost(reaction)
                priority = cost + self._heuristic(new_root, unresolved, config.heuristic)
                heapq.heappush(queue, _State(priority, next(counter), new_root, unresolved, cost))
                stats.molecules_discovered += len(precursor_smiles)
            stats.frontier_size = len(queue)
        stats.elapsed_seconds = round(time.monotonic() - started, 6)
        if config.objective != "deepest_supported":
            results.sort(key=lambda r: (r.metrics.total_score, r.signature))
        if config.objective == "deepest_supported":
            result_signatures = {route.signature for route in results}
            partials: list[Route] = []
            for root_candidate in direct_candidates.values():
                metrics = _metrics(root_candidate)
                signature = _signature(root_candidate)
                if metrics.unresolved_leaves and signature not in result_signatures:
                    partials.append(Route(root_candidate, metrics, signature, complete=False))
            partials.sort(
                key=lambda route: (
                    route.metrics.unresolved_leaves,
                    -route.metrics.stock_leaves,
                    route.metrics.total_score,
                    route.signature,
                )
            )
            results.extend(partials)
        report(f"search {stats.termination}", force=True)
        return results, stats


class BreadthFirstPlanner(BestFirstPlanner):
    name = "breadth_first_baseline"

    def _heuristic(
        self,
        root: RouteNode,
        items: tuple[tuple[tuple[int, ...], tuple[str, ...], int], ...],
        kind: str,
    ) -> float:
        return 0.0

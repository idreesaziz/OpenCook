# Search

`BestFirstPlanner` searches partial AND/OR solution graphs. The frontier priority is accumulated reaction cost plus a replaceable remaining-cost estimate. The zero heuristic is the correctness baseline; the descriptor heuristic uses heavy-atom count only as a non-evidentiary estimate. Expansion results are cached by canonical molecule within a search.

Canonical SMILES provide the transposition identity. Path-local ancestor sets reject cycles. They are intentionally path-local: a molecule reused in a distinct convergent branch is legal, while a dependency returning to an ancestor is not. Context-independent reaction lookups are cached; route costs are not globally memoized because shared intermediates can change context-sensitive material accounting.

Exact reactions have the lowest uncertainty penalty. Analogue, template, and computational records remain separate evidence classes. Costs are centralized in `search.py`. Complete routes expose transformation count, longest linear sequence, stock leaves, average confidence, evidence penalty, and total score.

## Deepest-supported mode

The web application uses `deepest_supported` by default. Stock membership is an
OR decision in this mode: the search may stop at a purchasable molecule and save
that complete route, or continue expanding exact reactions that produce it.
Routes are retained by deepest supported linear sequence, then transformation
count, evidence cost, and deterministic signature. “Deepest” is bounded by the
configured depth, expansion count, candidate limit, and timeout; it does not
imply decomposition into elements or prove laboratory feasibility.

Search status reports the active retrosynthetic stage, current molecule and
depth, unique reactions examined, molecule expansions, frontier size, complete
routes discovered, deepest complete route, and elapsed time. These are planner
observations, not experimental evidence.

The breadth-first baseline uses the same correctness machinery with a zero heuristic. Search limits include depth, molecule expansions, time, requested routes, and candidate reactions.

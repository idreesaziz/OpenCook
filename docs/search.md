# Search

## ORD-first hybrid expansion

For every selected molecule the planner queries the reverse ORD index first. Only when that exact lookup
returns no producers may an enabled model provider generate precursor candidates. Each accepted candidate
is labelled `computational_proposal`, includes model provenance, and receives an uncertainty penalty. Its
generated precursors re-enter the same ORD-first loop.

Model fallback is optional and local. OpenCook's Python 3.13 application environment does not depend on
PyTorch. RetroChimera currently requires a compatible Python 3.11 environment on Windows, so it runs behind
a persistent JSON-lines worker:

```powershell
uv venv .model-venv --python 3.11
uv pip install --python .model-venv\Scripts\python.exe retrochimera==1.2.0 pytorch-lightning==2.2.2 "torchmetrics<0.11" "scipy<1.12" pandas
$env:OPENCOOK_MODEL_PROVIDER = "retrochimera"
$env:OPENCOOK_MODEL_PYTHON = ".model-venv\Scripts\python.exe"
opencook serve
```

If inference fails, the search preserves the unresolved molecule and records a model failure. A configurable
heavy-atom threshold prevents meaningless model expansion of tiny terminal materials.

`structurally_valid_not_forward_verified` only means RDKit accepted the generated structures. It does not
mean the reaction has experimental support or that a separate forward model reproduced the target.

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

## Purchase-directed search

When real-world availability verification is enabled, OpenCook deliberately ignores the broad imported
catalog stock as a stopping condition. It begins with an empty per-search stock overlay, expands the target
through ORD and then the configured local model at unresolved leaves, checks the exposed leaves through
AvailEvidence, and adds only verdicts marked `terminal=true` to that overlay. The next search epoch rebuilds
connected routes using those verified leaves and progressively increases the allowed retrosynthetic depth.

This loop is bounded by `availability_max_rounds`, the global wall-clock limit, expansion limit, model-call
limit, and availability candidate limit. Availability observations are cached within the search, and the
result records the exact versioned availability snapshot. A catalog mention or professional-only listing is
shown as evidence but cannot terminate a route for an ordinary-individual search.

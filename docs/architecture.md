# Architecture

The optional computational expansion layer is isolated from the deterministic core. `ExpansionProvider`
returns domain reactions with explicit computational evidence; the AND/OR planner does not depend on
PyTorch or a particular model. `RetroChimeraProvider` can use a persistent Python 3.11 worker while the API
and RDKit application remain on Python 3.13.

OpenCook is a modular monolith. `chemistry` owns molecular identity and RDKit operations; `store` owns persistence and reverse indexes; `stock` defines purchasability/availability boundaries; `domain` contains stable scientific records; `search` builds complete solution trees; `api` and `cli` are adapters.

Reactions are hyperedges, never molecule-to-molecule edges. A product molecule is an OR node over producing reactions. Each reaction is an AND node over all reactants. Search states contain a partial route and the complete unresolved precursor set. Selecting one reaction therefore adds every precursor to that state. A route is complete only when that set is empty.

SQLite is the runnable local/fixture backend. The storage boundary is deliberately query-oriented (`reactions_producing`) so PostgreSQL with the RDKit cartridge can replace it for million-record deployments without changing planners. Full corpora must be streamed and indexed; they must not be materialized as Python objects per search.

## Limitations

The first release searches exact indexed records. Template extraction/application, fingerprint analogue retrieval, atom mapping, PostgreSQL cartridge deployment, and MCTS are extension points rather than claims of implemented chemistry. The bundled fixture is for software verification, not procedural chemistry. Cancellation is cooperative at the job boundary; fine-grained planner interruption is planned.

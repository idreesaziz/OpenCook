# Ecosystem research notes (reviewed 2026-09-02)

Primary upstream documentation and repositories were reviewed before dependency selection. RDKit 2026.03 provides molecule/reaction parsing, stereochemistry, fingerprints, SMARTS, InChI, deterministic 2D SVG drawing, and its PostgreSQL cartridge; it remains the appropriate chemistry foundation under BSD-3-Clause.

ORD schema 0.8.3 uses a structured single-step reaction protobuf, supports lazy one-reaction-per-row Parquet via `DatasetView`, and distributes official data through the `ord-data` repository with a Hugging Face read mirror. ORD data is CC-BY-SA; ORD software is Apache-2.0. OpenCook therefore separates code, data, and indexes and treats Parquet as a stream, not an in-memory corpus.

Syntheseus provides MIT-licensed common interfaces for single-step models, graph search, and controlled benchmarking. Its re-evaluation methodology reinforces reporting calls, expansions, time, and route outcomes under fixed budgets. AiZynthFinder separates stock, expansion policy, filter policy, and tree search. SynPlanner combines standardization, rule extraction, building blocks, MCTS, ranking, and visualization. OpenCook adopts these separations without copying implementations.

Retrosynthesis is an AND/OR problem. AO*/Retro*-style best-first methods exploit value propagation; MCTS trades deterministic ordering for exploration; graph methods such as RetroGraph reuse molecule states; A*/best-first variants depend heavily on admissibility/calibration; hybrid MCTS/A* approaches attempt both. Route evaluation must account for all reactants, cycles, shared states, and diversity of key disconnections.

RXNMapper remains widely used for attention-guided atom mapping, but its ML runtime and licensing/deployment implications make it an optional ingestion adapter rather than a base runtime dependency. Deterministic/chemistry-aware alternatives and commercial mappers must preserve mapper name/version and mapping validation.

Ketcher 3.18 remains a mature Apache-2.0 structure editor and supports a fully local standalone Indigo/WASM service. React Flow/XYFlow is suitable for the interactive synthesis DAG because custom molecule/reaction nodes and top-to-bottom layered layouts are central; Cytoscape.js remains attractive for much larger graph analysis.

Primary references: RDKit documentation and repository; ORD schema/data documentation and repositories; Microsoft Syntheseus repository and Faraday Discussions paper; AiZynthFinder and SynPlanner repositories; original Retro* (NeurIPS 2020), RetroGraph, and retrosynthetic MCTS publications. Version claims should be rechecked at release time because the stated date may be ahead of upstream publication calendars.

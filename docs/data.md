# Reaction data

The bundled CC0 fixture exercises real parsing, reverse lookup, multistep search, convergency, route diversity, provenance, and cycles. It is not a chemistry benchmark.

ORD is the primary supported open corpus. Current `ord-schema` releases read Protobuf and lazy Parquet and fetch published datasets from the official Hugging Face mirror. Install `uv sync --extra ord`, identify a dataset in the official `ord-data` catalog, then run:

```bash
uv run opencook data download ord_dataset-IDENTIFIER --output data/downloads
```

Downloaded datasets and generated indexes are ignored by Git. ORD data is CC-BY-SA; schema/tooling is Apache-2.0. Import metadata must retain dataset ID/version/source/license/import time and normalization version.

USPTO/Lowe-derived datasets vary in redistribution status and processing provenance. They require a distinct adapter and explicit license record; OpenCook never silently merges them with ORD. Proprietary sources (Pistachio, Reaxys, CAS, ELNs) require user-supplied licensed adapters and credentials.

## Starting-material catalogs

Stock is stored separately in `data/stock.sqlite`. It is a versioned collection
of availability assertions, not a list embedded in source code. SMILES,
whitespace-delimited, CSV, TSV, and gzip-compressed exports are streamed with:

```console
opencook stock import catalog.smi.gz --source ZINC --version 2021-03
opencook stock status
```

Every assertion retains its source, catalog identifier, and profile. Use
`building_blocks` only for a source explicitly representing usable starting
materials; broader purchasable or make-on-demand exports belong to
`commercial_catalog`. Reaction reactants are never assumed available merely
because they occur in an experimental record.
# Availability evidence

OpenCook can consume the independent AvailEvidence service without embedding web
retrieval into retrosynthesis. Start AvailEvidence separately, then verify a candidate
into an immutable local stock snapshot:

```bash
opencook stock verify "CCO" --country US --url https://merchant.example/product
```

Only a strict `terminal=true` verdict is imported. Catalog listings, ambiguous names,
and unverified shopping results never become stock automatically. Network availability
lookups are explicit and are not performed in the planner's expansion loop.

## Web application integration

Place the OpenCook and AvailEvidence repositories beside one another, start both
services, and enable **VERIFY REAL-WORLD AVAILABILITY** in the molecule search screen.
The market must be an explicit ISO 3166-1 alpha-2 country code.

```bash
# terminal 1
cd ../AvailEvidence
uv run availevidence serve

# terminal 2
cd ../OpenCook
uv run opencook serve
```

The web-search job performs retrosynthesis first, collects a bounded set of every
unique route leaf (both configured stock and unresolved), checks them through
AvailEvidence with live progress, and attaches every verdict to the matching molecule.
This means existing stock assumptions receive inspectable source links too. If strict
terminal offers are verified, it
constructs a per-search versioned stock overlay and resumes retrosynthesis. The global
stock database is not mutated by a web query.

Docker users with both sibling repositories can run the optional service profile:

```bash
docker compose --profile availability up --build
```

Availability checking is off by default because precursor identities may be
confidential and configured discovery providers make external network requests.

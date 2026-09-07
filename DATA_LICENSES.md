# Data licenses

## Optional model checkpoints

RetroChimera code and checkpoints are not bundled with OpenCook. Users download them separately and must
review upstream code, checkpoint, and training-data terms. A checkpoint trained on a commercial corpus must
not be assumed to inherit OpenCook's MIT source license. Generated reactions remain computational
proposals, not experimental evidence.

OpenCook source code is MIT. That license does not apply to reaction datasets, generated indexes containing dataset-derived material, commercial catalogs, or user-provided data.

| Data | Bundled | License | Notes |
|---|---:|---|---|
| OpenCook benign fixture | yes | CC0-1.0 | Synthetic software-test records; no procedures |
| Open Reaction Database | no | CC-BY-SA-4.0 | Attribution/share-alike obligations apply |
| PubChem names | cached only | source-specific provenance | PubChem aggregates depositor content; do not redistribute caches blindly |
| USPTO/Lowe-derived corpora | no | source-specific | Verify source and redistribution terms before import |
| Commercial catalogs/databases | no | contractual | User must hold appropriate rights |
| User data | no | user-controlled | Remains local by default |

Generated indexes must travel with a manifest identifying inputs, versions, licenses, attribution, import time, and normalization pipeline version.

## ZINC catalogs

OpenCook can stream ZINC SMILES exports into a local stock index but does not
redistribute those exports. ZINC snapshots can combine vendor catalog assertions
and make-on-demand molecules. Imports must retain the snapshot date and use the
`commercial_catalog` profile unless the selected export explicitly represents
in-stock building blocks. Availability is not assumed current.

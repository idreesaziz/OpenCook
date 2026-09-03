# Reaction normalization

The ingestion boundary normalizes every reactant and product independently, preserves roles, validates parseability, canonicalizes identity, and writes a product reverse index plus precursor-use index. Duplicate source records should merge provenance rather than erase it. Each production importer must report read, parsed, rejected, mapping-failure, normalized, duplicate, template, and indexed counts with rejection reasons.

The fixture importer implements parse/normalize/index reporting. ORD adaptation is isolated from the domain representation. Evidence confidence and deterministic validation status are separate fields. A record may be exact experimental evidence while still failing a particular validation check; neither field overwrites the other.


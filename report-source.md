# Purchase-evidence service: build-vs-buy research

**Research date:** 2026-09-04  
**Decision status:** proposed architecture for an independent repository and an OpenCook adapter

## Executive decision

Do not build a search engine, crawler, shopping index, or product-matching model from
scratch. Build a small, domain-neutral **purchase-evidence federation service** that
composes mature providers and preserves exactly what each source actually proves.

The service should answer:

> For this precisely identified item, buyer profile, place, and time, what current
> evidence exists that the item can be ordered?

It must not answer the stronger question “can this person definitely buy it?” unless
that fact was explicitly established. Search results, catalog entries, and supplier
pages are leads; they are not equivalent to a successful purchase.

The proposed independent repository is provisionally called **AvailEvidence**. The
name is intentionally provisional pending a trademark and package-registry check.
OpenCook should integrate it through a narrow `AvailabilityProvider` adapter rather
than absorbing commerce-specific code.

### Recommended composition

| Capability | Default component | Alternatives | Why |
|---|---|---|---|
| Broad offer discovery | DataForSEO Merchant API | SerpApi Google Shopping | Existing location-aware shopping index with product and seller URLs; no crawler to maintain |
| Known-URL monitoring | changedetection.io | PriceBuddy | Mature Apache-2.0 REST service with restock monitoring; PriceBuddy's unusual noncommercial license is unsuitable for incorporation |
| Product-page extraction | Schema.org JSON-LD via `extruct`; Diffbot fallback | Zyte Product extraction | Prefer merchant-published structured facts; outsource difficult pages rather than invent selectors |
| Generic exact identity | GTIN/UPC/EAN/ISBN/MPN + brand; Verified by GS1 when configured | Provider product IDs | Stable identifiers must outrank name similarity |
| Chemical exact identity | RDKit normalization + full standard InChIKey; PubChem identifier mapping | CAS RN only when legitimately licensed | OpenCook already has molecular identity; names are aliases, not identity |
| Candidate ranking | RapidFuzz first; optional Marqo Ecommerce Embeddings B | Sentence Transformers | Both are existing libraries/models; similarity proposes candidates but never verifies identity |
| Open vertical catalogs | Open Food Facts/Open Prices plugins | Open Icecat | Useful enrichment in their domains, not universal live inventory |
| Storage and jobs | PostgreSQL + a simple in-process/DB worker initially | SQLite for demo | Evidence is relational, auditable, and modest in volume; no event bus is warranted |

The core remains usable with no paid provider: accept known product URLs, parse
Schema.org offers, optionally monitor them through changedetection.io, and return
`unknown` when evidence is insufficient. Broad web discovery is an optional,
networked provider capability.

## What already exists

### 1. Discovery indexes

**DataForSEO Merchant API** is the best initial discovery connector. Its Merchant API
returns Google Shopping listings, seller data, prices, product detail data, full
advertised URLs, and supports language/location selection. This is the closest fit to
“find current products an ordinary buyer might encounter,” while remaining an
external provider rather than infrastructure we maintain. It is proprietary and its
response-retention/redistribution terms must be reviewed before shipping a hosted
service. [Merchant API overview](https://docs.dataforseo.com/v3/merchant-api-overview/)

**SerpApi Google Shopping** is a credible interchangeable connector. It exposes
titles, merchants, prices, delivery information, product pages, and multiple sellers,
with geographic parameters. It should be treated as observed search-index data, not
merchant truth. [Google Shopping API](https://serpapi.com/google-shopping-api)

**Google Merchant API is not a global product-search API.** It lets an authenticated
merchant manage and read that merchant's own regional inventory. It should not be
selected as the discovery foundation. [Regional inventories reference](https://developers.google.com/merchant/api/reference/rest/inventories_v1/accounts.products.regionalInventories)

**SearXNG** can be offered as a self-hosted, best-effort web-search connector, but its
results are documents rather than normalized offers, public instances frequently
disable JSON output, and upstream engine policies can change. It is not a dependable
default. [SearXNG search API](https://github.com/searxng/searxng/blob/master/docs/dev/search_api.rst)

No evaluated open-source repository provides a maintained, worldwide, current
shopping index. Open price trackers start from URLs; comparison engines acquire
merchant feeds or commercial indexes. This is the irreducible external-data boundary.

### 2. Monitoring known URLs

**changedetection.io** is the strongest reusable open-source monitor. It is
Apache-2.0, self-hostable, has a REST API, browser fetching support, and a product
restock processor. AvailEvidence should run it as an optional sidecar and store its
watch ID, observations, and errors—not fork its internals. [REST API](https://changedetection.io/docs/api_v1/)

**PriceBuddy** is functionally attractive: URL metadata extraction, price and
availability tracking, CLI, and an OpenAPI-described REST API. However, its repository
license contains a noncommercial restriction and calls itself “GPL-3.0 WITH
MODIFICATIONS.” It is therefore not open source under the OSI definition and must not
be copied or made a mandatory dependency of a permissively licensed general-purpose
project. It may be supported only as an optional user-managed integration after legal
review. [PriceBuddy license](https://github.com/jez500/pricebuddy/blob/main/LICENSE.md)

Smaller price-tracker repositories demonstrate similar JSON-LD/Playwright patterns,
but do not improve the core discovery or identity problem enough to justify depending
on young projects. We should integrate the established monitor and keep the service
contract independent.

### 3. Product-page extraction

Most modern merchant pages expose `Product` and `Offer` structured data. Schema.org's
Offer vocabulary includes availability, price, eligible region, identifiers, seller,
and delivery-related fields. These are the highest-value zero-ML facts and should be
preserved with their source URL and raw value. [Schema.org Offer](https://schema.org/Offer)

**extruct 0.18** is a BSD-licensed Python library that extracts JSON-LD, microdata,
RDFa, OpenGraph, and microformats. It is an appropriate library component—not a new
extraction foundation—for static HTML already fetched in accordance with a site's
terms. [extruct package](https://pypi.org/project/extruct/)

**Diffbot Product API** is the recommended difficult-page fallback. It accepts a URL
and returns structured price, SKU/UPC/MPN, brand, specifications, and a beta boolean
availability field. Because availability is beta and coarse, AvailEvidence must retain
the field's provider and confidence rather than promote it to a definitive result.
[Diffbot Product API](https://www.diffbot.com/docs/extract/product)

**Zyte Automatic Extraction** is a viable alternative with product and product-list
schemas. Its documentation warns that `InStock` may also represent limited stock,
presale, preorder, or in-store-only availability. Those states cannot be collapsed to
“ordinary buyer can order now.” Avoid its LLM custom-attribute feature in the base
system. [Zyte extraction reference](https://docs.zyte.com/zyte-api/usage/reference.html)

We should not build a general Playwright crawler. Browser automation brings bot
defenses, SSRF/resource risks, site-specific maintenance, and terms-of-service issues.
If users elect to self-fetch, changedetection.io owns that concern; if they elect a
managed extractor, Diffbot/Zyte owns it.

### 4. Identity and matching

Identity resolution must be a staged verifier, not one embedding score:

1. Normalize the requested identity using its domain adapter.
2. Require exact stable identifiers when available.
3. Compare structured attributes (brand, model, size, concentration, form).
4. Use lexical/vector similarity only to rank candidates lacking identifiers.
5. Mark conflicts explicitly and retain rejected candidates for audit.

For trade items, **GS1 GTIN** identifies trade items and **Verified by GS1** can check
the organization and basic product identity behind a GTIN. The public service is
rate-limited and verification does not demonstrate current stock or buyer eligibility.
[GTIN standard](https://www.gs1.org/standards/id-keys/gtin), [Verified by GS1 scope](https://support.gs1.org/support/solutions/articles/43000734077-what-is-verified-by-gs1-)

For chemicals, exact molecular identity should use OpenCook's RDKit-normalized
isomeric representation and full InChIKey. Connectivity-only matches, salts, solvates,
mixtures, stereoisomers, grades, and concentrations must remain distinct. PubChem is
useful for identifiers and synonyms. Its chemical-vendor policy requires submitted
vendor links to represent existing, in-stock chemicals and rejects virtual or
make-on-demand entries, which makes vendor presence useful evidence—but it still does
not establish region, package availability, purity, or buyer eligibility.
[PubChem vendor policy](https://pubchem.ncbi.nlm.nih.gov/docs/chemical-vendor-policy),
[PubChem programmatic access](https://pubchem.ncbi.nlm.nih.gov/docs/programmatic-access)

**RapidFuzz** is MIT-licensed and suitable for deterministic lexical candidate
ranking. [RapidFuzz license](https://rapidfuzz.github.io/RapidFuzz/License.html)

**Marqo Ecommerce Embeddings B** is an optional Apache-2.0, approximately 0.2B
parameter retrieval model trained for ecommerce matching. It can improve recall after
exact matching, but its output is never evidence. The larger model is unnecessary for
the first release. [Model card](https://huggingface.co/Marqo/marqo-ecommerce-embeddings-B)

Amazon's open **ESCI Shopping Queries Dataset** contains large-scale query-product
relevance judgments with Exact/Substitute/Complement/Irrelevant labels. It is useful
for evaluating a candidate ranker; it is not a live catalog and should not ship as
inventory. [ESCI dataset](https://github.com/amazon-science/esci-data)

### 5. Open catalogs and chemical supplier sources

**Open Food Facts** and **Open Prices** are strong optional food plugins. Their data
is community-contributed, domain-limited, and subject to ODbL attribution/share-alike
requirements; Open Food Facts explicitly disclaims completeness and reliability.
[Open Food Facts API/licensing](https://openfoodfacts.github.io/openfoodfacts-server/api/),
[Open Prices API](https://github.com/openfoodfacts/open-prices/blob/main/API.md)

**Open Icecat** supplies structured product content for participating brands, not a
universal live offer database. It is enrichment, not proof of availability.
[Open Icecat](https://icecat.com/structured-data-content-users/)

**EPA CPDat** maps chemicals to consumer-product categories and ingredients. It can
support “this chemical occurs in product category X” research, but it does not show a
pure chemical for sale and must never be used to terminate a synthesis route.
[EPA CPDat](https://www.epa.gov/chemical-research/chemical-and-products-database-cpdat)

Professional chemical catalogs remain valuable as a separate buyer class. Enamine
advertises millions of building blocks and region-specific stock, while eMolecules
aggregates supplier inventory, pricing, and delivery. Neither implies that an
uncredentialed individual can buy a listed chemical. Their connectors must therefore
return `professional_catalog` evidence unless buyer eligibility is independently
shown. [Enamine building-block catalog](https://enamine.net/building-blocks/building-blocks-catalog),
[eMolecules supplier network](https://www.emolecules.com/suppliers)

## Evidence model

### Inputs

```json
{
  "identity": {
    "domain": "chemical",
    "identifiers": {"inchikey": "..."},
    "attributes": {"form": "neat", "purity_min": 0.95}
  },
  "buyer": {"class": "ordinary_individual"},
  "market": {"country": "TR", "postal_code": null},
  "freshness_seconds": 86400
}
```

The service must not infer buyer class or market. Unknown inputs stay unknown.

### Observation record

Every provider response becomes an immutable observation containing:

- normalized requested identity and candidate identity;
- exact/fuzzy/mismatch identity decision and reasons;
- merchant and canonical offer URL;
- provider and upstream source;
- raw availability token plus normalized availability;
- price, currency, package/variant, shipping/region fields;
- seller audience or account requirements when explicitly stated;
- observation timestamp, expiry, parser/model version, and source-content hash;
- raw response reference subject to provider retention terms;
- warnings, ambiguity, and extraction errors.

### Availability states

Use facts rather than a single optimistic boolean:

| State | Meaning |
|---|---|
| `orderable_observed` | Exact identity and an explicit current online orderable offer were observed for the requested market |
| `listed_in_stock` | Source says in stock, but orderability or buyer eligibility is not established |
| `professional_catalog` | Exact chemical/product catalog listing intended for institutional/professional purchasing |
| `preorder_or_backorder` | Seller explicitly defers fulfillment |
| `local_only` | Store pickup/in-store evidence without online delivery evidence |
| `out_of_stock` | Exact candidate explicitly unavailable |
| `restricted` | Source explicitly states an eligibility, legal, account, or shipping restriction |
| `identity_ambiguous` | Candidate similarity is insufficient for exact identity |
| `unknown` | No fresh, adequate evidence |

An aggregated verdict includes a confidence and machine-readable reasons. Contradictory
fresh observations remain visible; the newest or strongest source does not erase the
others.

### Ordinary-individual termination policy

For OpenCook, a precursor is terminal under the strict default only when:

- it is in the user's own inventory; or
- AvailEvidence reports `orderable_observed` for an exact identity, requested form,
  market, and ordinary-individual buyer class within the configured TTL.

`listed_in_stock`, PubChem vendor presence, professional catalogs, molecular size,
common names, and occurrence inside household products do not terminate a route.
Users can choose a looser professional-catalog policy explicitly.

## Independent repository architecture

```text
Client request
    |
Identity adapter ---- RDKit/PubChem | GTIN/GS1 | OFF
    |
Discovery federation ---- DataForSEO | SerpApi | supplied URLs
    |
Candidate verifier ---- exact IDs -> attributes -> RapidFuzz/Marqo ranking
    |
Offer extraction ---- provider fields -> JSON-LD/extruct -> Diffbot
    |
Evidence policy ---- market + buyer + freshness + contradictions
    |
PostgreSQL observation store + REST/CLI response
    |
Optional changedetection.io watches for revalidation
```

Recommended modules:

```text
availevidence/
  identity/       # protocol and generic/chemical/food adapters
  discovery/      # provider protocol and DataForSEO/SerpApi adapters
  extraction/     # schema.org and managed-extractor adapters
  matching/       # deterministic verification and optional rerankers
  evidence/       # observations, verdict policy, freshness
  monitoring/     # changedetection.io client
  storage/        # SQLAlchemy models/migrations
  api/            # versioned FastAPI schemas/endpoints
  cli/            # query, observe, verify, watch, doctor
```

Suggested public API:

- `POST /v1/availability/check` — synchronous cached check or queued refresh;
- `POST /v1/availability/searches` — explicit networked discovery job;
- `GET /v1/availability/searches/{id}` — progress and observations;
- `GET /v1/identities/{id}/offers` — auditable current/history view;
- `POST /v1/observations` — user/merchant supplied evidence;
- `POST /v1/watches` — opt-in revalidation;
- `GET /v1/providers` and `/v1/health` — configuration and diagnostics.

The Python SDK should expose one protocol that OpenCook can depend on:

```python
class AvailabilityProvider(Protocol):
    def evaluate(
        self, identity: ProductIdentity, buyer: BuyerProfile,
        market: Market, policy: AvailabilityPolicy
    ) -> AvailabilityVerdict: ...
```

## What we should write versus compile

Write only the glue that no existing component can supply:

- provider-neutral schemas and adapters;
- evidence normalization and conservative policy evaluation;
- exact identity rules and domain plugin protocol;
- provenance, caching/TTL, contradiction handling, and OpenCook adapter;
- tests that use recorded/licensed fixtures rather than live services.

Reuse rather than implement:

- shopping discovery indexes (DataForSEO/SerpApi);
- web monitoring and browser rendering (changedetection.io);
- structured metadata parsing (`extruct`);
- difficult-page extraction (Diffbot/Zyte);
- molecule normalization (RDKit) and identifiers (PubChem);
- fuzzy matching (RapidFuzz) and optional ecommerce embeddings (Marqo);
- vertical datasets (Open Food Facts/Open Prices) subject to their licenses.

Explicitly do not build:

- a universal crawler or anti-bot system;
- an ecommerce search transformer;
- checkout automation;
- retailer-specific scrapers in core;
- buyer eligibility guesses from molecular complexity or supplier count;
- household-product extraction/procedural chemistry;
- an LLM adjudicator.

## OpenCook integration

AvailEvidence must remain a separate process/package and an optional network feature.
OpenCook is local-first, so a search must not leak a confidential target or precursor
unless the user enables availability lookup. Search reproducibility records the
service version, provider set, market, buyer class, policy, and observation snapshot
IDs.

Integration should be two-phase:

1. Retrosynthesis explores ORD/model transformations against immutable user/catalog
   stock without network calls in the hot expansion loop.
2. Candidate leaves are batch-evaluated through AvailEvidence. Verified leaves are
   admitted to a versioned stock snapshot; search is resumed against that snapshot.

This avoids nondeterministic network latency inside graph expansion and prevents a
temporary storefront failure from silently changing route semantics. The UI should
show `verified public offer`, `professional listing`, and `unresolved` distinctly,
with source, market, observation time, and expiry.

The procurement/evidence layer must remain separate from reaction search and from the
safety policy. For controlled or high-risk targets, OpenCook may show non-operational
identity and precedent metadata while suppressing procurement links and procedural
details. Availability evidence must never generate isolation or synthesis instructions.

## Licensing and operational boundaries

- License AvailEvidence code under Apache-2.0.
- Provider data remains under provider terms; do not imply Apache-2.0 covers it.
- Store provider payloads only as allowed and make raw-response retention configurable.
- ODbL datasets require attribution and database share-alike analysis before combining
  them into a distributed database; keep them in isolated adapters/snapshots.
- Do not incorporate PriceBuddy code under its current noncommercial modified license.
- Treat retailer terms, robots directives, rate limits, geographic law, and privacy as
  provider configuration, not bypass targets.
- Network providers are disabled by default in OpenCook. Never send full routes when a
  leaf identity alone is sufficient.

## Validation plan

Before OpenCook trusts the service, measure it on a labeled set spanning common retail
products, exact chemical forms, professional-only chemicals, ambiguous aliases,
out-of-stock pages, preorder/local-only offers, and regional conflicts.

Report at least:

- exact-identity precision and false-match rate;
- `orderable_observed` precision by buyer class and market;
- discovery recall conditional on providers queried;
- extraction field accuracy and unknown rate;
- observation age and revalidation success;
- provider latency, cost/query, and failure rate;
- disagreement rate between sources;
- OpenCook route termination changes versus user inventory alone.

Do not optimize for the number of “available” answers. Optimize precision for terminal
stock decisions; an honest `unknown` is scientifically preferable to a false route.

## Delivery sequence

1. Create the independent Apache-2.0 repository with schemas, policy engine, REST/CLI,
   PostgreSQL, and recorded fixtures.
2. Add exact identifier adapters and known-URL Schema.org extraction.
3. Add DataForSEO and SerpApi discovery adapters behind explicit credentials.
4. Add changedetection.io monitoring and Diffbot fallback adapters.
5. Add the chemical identity plugin using RDKit/PubChem.
6. Build and publish a labeled availability evaluation set with legally distributable
   page fixtures and expected evidence states.
7. Integrate OpenCook through a snapshot-producing stock adapter.
8. Only after measured lexical baseline errors justify it, add optional Marqo reranking.

## Final assessment

There is no single massive, open, current database that proves arbitrary products are
purchasable by an ordinary individual. The viable “compile, don't invent” solution is
a thin evidence layer over existing shopping indexes, structured offer data, managed
extractors, identity authorities, and an established monitor. Approximately all hard
retrieval/extraction machinery can be reused; the small amount of original work is the
scientifically important part—defining what evidence means, preserving provenance,
and refusing unsupported conclusions.

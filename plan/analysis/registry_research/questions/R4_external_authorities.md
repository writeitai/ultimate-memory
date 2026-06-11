# R4 — External authority files as ER "tier 0"

**Question.** For OpenAlex, Crossref/DOI, ORCID, Wikidata (QIDs + reconciliation API),
GLEIF LEI, OpenCorporates, ISBN, and GitHub: what entity types does each authoritatively
identify, what is its API access / rate limit / licensing / cost, how well does it cover the
non-famous long tail, and how good is its reconciliation API? Which are worth integrating at
launch for a general research/knowledge memory vs never? Recommend a concrete tier-0 connector
set plus a fallback when no authority matches.

Context: tier 0 is the front of the resolution cascade in `entity_registry.md` §4 ("Tier 0 —
external authority match … the cheapest *and* most reliable tier when it applies"), feeding
D4's cheap-first cascade and D15's anchored-ontology idea. Open question #4 in
`entity_registry.md` §8 ("which ones at launch?") is exactly this question.

---

## 1. Key findings

- **Two authorities are launch no-brainers because they combine CC0/open bulk data, a real
  reconciliation/disambiguation surface, and deep long-tail coverage: Wikidata (122M items,
  CC0, a *standardized* W3C reconciliation API at `wikidata.reconci.link`) and OpenAlex (271M
  works, ~90M authors, CC0).** Both map cleanly onto our core types (Person, Organization,
  Place, Concept, Document/Work). Wikidata is the only one of the eight that ships a
  general-purpose, multi-type, *standardized* reconciliation endpoint — the others are exact-key
  lookups or paid.
- **Three are high-value *deterministic-key* connectors with no fuzzy reconciliation but
  near-perfect precision when an ID is already present in the source text: Crossref/DOI
  (~160M+ scholarly records, free, no auth), ORCID (>20M researcher iDs, free public API), and
  GLEIF LEI (~2.93M legal entities, fully open CC0 bulk + API).** These are not "name → entity"
  resolvers; they are "ID-in-document → canonical entity" validators. Extremely cheap and
  reliable *when the document already carries the identifier*; near-useless for cold name
  resolution.
- **Two should be NEVER / not-at-launch for a general memory: OpenCorporates (now effectively a
  paid product — self-serve API from £2,250/yr, free tier only for open/share-alike or
  NGO/journalist use, hard call caps) and ISBN-as-an-authority (no single free canonical API;
  the open options — Open Library, Google Books — have patchy long-tail/self-published coverage
  and discouraged bulk use; ISBNdb is paid).** GitHub is a *narrow special-case* connector
  (great for software-project/developer scopes, 5,000 req/hr authenticated, exact login/repo
  IDs), not a general tier-0.
- **Recommended tier-0 set at launch: Wikidata (reconciliation API, the workhorse) + OpenAlex
  (authors/works) + three deterministic ID validators (DOI, ORCID, LEI) that fire only when the
  identifier is literally present in the source.** Everything else (OpenCorporates, ISBN, GitHub)
  is a scope-triggered opt-in connector, not core. **Fallback when no authority matches: do NOT
  block — mint a local entity ID and fall straight through to tiers 1–5** (exact → fuzzy →
  phonetic → embedding → adjudication), recording `method = tier0_miss`. Tier 0 is an
  *accelerator that anchors outward*, never a gate. This is the conservative posture
  `entity_registry.md` §1 demands.

**Confidence: medium-high.** Rate-limit / coverage numbers are well-sourced and recent (most
from Dec 2025 / 2025-in-review pages), but two things changed under our feet and deserve a flag:
OpenAlex moved to an API-key + credit model (polite pool deprecated) and Crossref cut its rate
limits on 2025-12-01. Reconciliation *match-quality* (false-positive rates) is qualitatively
described in the literature but I found no clean published precision/recall numbers — that gap
is real and flagged in §3.

---

## 2. Evidence & detail

### 2.1 The two axes that actually matter for tier 0

A tier-0 authority is only useful to our cascade if it does one of two things well:

1. **Deterministic validation** — the document already contains the identifier (a DOI string,
   an `orcid.org/0000-…`, an LEI, a GitHub `@handle`). The connector just *resolves the ID to a
   canonical record* and confirms type/name. Precision ≈ 1.0, recall = "whatever fraction of
   mentions carry the ID." Cheap, boring, reliable.
2. **Reconciliation** — given a *name string* (+ optional type/context), return ranked candidate
   entities with scores. This is the hard, valuable case — it's the same job as our tiers 2–4,
   but anchored to a curated external KG instead of our own prior mentions (the "anchor outward"
   lesson from Cognee in `entity_registry.md` §2).

**Only Wikidata gives us (2) as a general, standardized, free service.** Everything else is
primarily (1), or paid, or both.

### 2.2 Per-authority detail

#### Wikidata — **INTEGRATE (the workhorse)**
- **Entity types:** universal. ~122,113,379 items as of early 2025 ([Wikidata:Statistics](https://www.wikidata.org/wiki/Wikidata:Statistics);
  [Wikipedia: Wikidata](https://en.wikipedia.org/wiki/Wikidata)), 1.65B statements. Persistent
  QIDs **never reused**, merges leave a **redirect** — which is exactly the governance model
  `entity_registry.md` §2/§4 already adopts for our own IDs.
- **Reconciliation API:** the [Reconciliation Service API](https://reconciliation-api.github.io/specs/latest/),
  edited by the [W3C Entity Reconciliation Community Group](https://www.w3.org/community/reconciliation/).
  *Not yet a W3C Standard* (Community Group spec v0.2, migration to a Working Group "expected in
  2026") but it is a real, multi-implementation protocol. Wikidata endpoint:
  `https://wikidata.reconci.link/en/api` (swap `en` for other languages). Supports type
  constraints, property-path scoring (e.g. `P17/P297`), preview + suggest endpoints
  ([Running a reconciliation service for Wikidata](https://ceur-ws.org/Vol-2773/paper-17.pdf)).
- **Access / limits / cost:** free, no payment. **Rate-limit caveat (flag):** the
  `wikidata.reconci.link` instance and the underlying Wikidata API are under tightened Wikimedia
  rate limits — ~30% of requests carrying "OpenRefine" in the User-Agent were being 429'd, and
  fixes hinge on a proper identifying User-Agent
  ([OpenRefine forum](https://forum.openrefine.org/t/wikidata-reconciliation-service-changes-wikimedia-rate-limits/2779);
  [OpenRefine issue #7731](https://github.com/OpenRefine/OpenRefine/issues/7731)). **Implication
  for us: do not hammer the public reconci.link instance for batch backfill — self-host the
  reconciliation service (it's open source,
  [Henri-Lo/openrefine-wikidata](https://github.com/Henri-Lo/openrefine-wikidata)) against a
  Wikidata dump, or rate-limit politely with a real User-Agent + `mailto`.**
- **Licensing:** Wikidata data is **CC0** — no attribution/share-alike obligations on derived
  state. This is the single biggest reason it can sit at the front of our pipeline without legal
  friction.
- **Long-tail coverage:** good-but-notability-bounded. Wikidata has explicit inclusion criteria;
  WikiProject Companies aims down to ~20-employee firms
  ([WikiProject Companies](https://www.wikidata.org/wiki/Wikidata:WikiProject_Companies)) but
  the genuinely non-notable (a random user's coworker, a tiny startup, an internal project) will
  simply not be there → tier-0 miss → fall through. That's fine and expected.

#### OpenAlex — **INTEGRATE (scholarly authors/works/institutions)**
- **Entity types:** Works (papers/books/preprints/datasets/theses), Authors, Institutions,
  Sources/Venues, Concepts/Topics, Publishers, Funders. ~271.3M works as of Nov 2025
  (250M "core" + a ~192M lower-quality DataCite/IR "expansion pack"), ~90M authors, ~100k
  institutions ([OpenAlex 2025 in Review](https://blog.openalex.org/openalex-2025-in-review/);
  [OpenAlex arXiv paper](https://arxiv.org/pdf/2205.01833)). Author disambiguation is exactly
  the feature-clustering approach noted in `entity_registry.md` §2 — useful as an *external*
  author resolver that already did the hard work.
- **Reconciliation:** no W3C reconciliation endpoint, but a rich filterable REST API
  (`/authors?filter=...`, `/works?filter=doi:...`) that supports name + affiliation search —
  effectively a domain-specific reconciliation surface for scholarly entities. Also key-keyed by
  DOI, ORCID, ROR, ISSN, Wikidata QID — so it doubles as a *crosswalk* between the other
  authorities.
- **Access / limits / cost (FLAG — model changed):** historically free + polite pool. As of the
  2025/2026 changes, **OpenAlex now uses API keys and a credit model**: a free key gives the
  equivalent of "$1/day of free usage" in credits (different ops cost different amounts), without
  a key you get ~100 credits/day (testing only), and the **polite pool is deprecated**; higher
  limits / monthly snapshots / daily change files require a paid plan (contact sales)
  ([OpenAlex Developers](https://developers.openalex.org/);
  [Pricing](https://help.openalex.org/hc/en-us/articles/24397762024087-Pricing)). A **free full
  CC0 snapshot is still published quarterly** — so the resilient pattern is to bulk-load the
  snapshot locally rather than depend on per-call API for backfill.
- **Licensing:** **CC0.**
- **Long-tail coverage:** excellent within scholarship (broader than Scopus/WoS, incl. preprints
  and global/non-English venues), but coverage discrepancies exist (e.g. documented China gaps,
  [Zheng 2025, JASIST](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.70013)). Outside
  scholarship it covers nothing — which is correct scoping.

#### Crossref / DOI — **INTEGRATE (deterministic DOI validator only)**
- **Entity types:** scholarly *Works* keyed by DOI (journal articles, books, conference papers,
  datasets, etc.), with embedded author/affiliation/funder metadata. ~160M+ registered DOIs.
- **Reconciliation:** none as a fuzzy name-resolver. It's a **DOI → record** lookup. Use it only
  when a DOI is present in the source text.
- **Access / limits / cost (FLAG — limits cut 2025-12-01):** free, no signup. As of
  **2025-12-01** the first-ever rate-limit revision applies
  ([Crossref blog](https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/)):
  - Public pool: **5 req/s** single-record (1 concurrent), **1 req/s** for list queries.
  - Polite pool (send `mailto`): **10 req/s** single-record (3 concurrent), **3 req/s** list.
  - Metadata Plus (paid): unchanged, higher limits + priority.
- **Licensing:** Crossref asserts **no ownership over individual bibliographic metadata items**;
  free to cache and incorporate
  ([metadata license info](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-metadata-license-information/)).
- **Long-tail coverage:** any DOI-registered work, including obscure ones — but only DOI-bearing
  things. A working paper without a DOI is invisible. OpenAlex actually wraps most of Crossref
  *plus* non-DOI sources, so for our purposes **OpenAlex subsumes most of Crossref's value**;
  keep a thin Crossref/DOI resolver for the deterministic "DOI literally in text" path.

#### ORCID — **INTEGRATE (deterministic ORCID-iD validator)**
- **Entity types:** *Persons* (researchers) keyed by a 16-digit ORCID iD. **>20M iDs issued**,
  ~9M actively used in 2024 ([10M milestone](https://info.orcid.org/10m-orcid-ids/);
  [Wikipedia: ORCID](https://en.wikipedia.org/wiki/ORCID)).
- **Reconciliation:** Public API supports search, but it's weak as a cold name-resolver
  (researcher names are ambiguous; ORCID's own data quality is self-asserted). Best used as
  **iD → person record** when the iD is present, or as an OpenAlex-mediated crosswalk.
- **Access / limits / cost:** **Public API is free** but requires registered credentials
  (Client ID + Secret, OAuth) tied to an individual's ORCID record
  ([registering a public API client](https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/)).
  Rate limits: per-second quotas with bursts (e.g. token endpoints 48 req/s, 75 burst; 503 on
  exceed, [API rate-limit clarification](https://groups.google.com/g/orcid-api-users/c/ehv8sCfs-ZM)).
  Heavy use → Member API (paid membership).
- **Licensing:** annual Public Data File is CC0; the public API serves the public portion of
  records.
- **Long-tail coverage:** good for *active researchers who self-registered*; a long-tail
  academic who never made an ORCID simply isn't there. Self-registration → both a coverage gap
  and a data-quality variance.

#### GLEIF LEI — **INTEGRATE (deterministic LEI validator + open bulk crosswalk)**
- **Entity types:** *legal entities* (firms, companies, partnerships, trusts, governments) — **not
  natural persons** — keyed by a 20-char LEI. **~2.93M active LEIs**, +355k in 2025 (+13.5%)
  ([The LEI in Numbers 2025](https://www.gleif.org/en/newsroom/blog/the-lei-in-numbers-global-transparency-and-digitalization-push-drives-lei-adoption-in-2025)).
  Includes Level-2 parent/ownership relationships — useful for our Organization graph edges.
- **Reconciliation:** the [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api) offers
  full-text, single-field, and **fuzzy matching** on names/addresses, plus Level-2 search — so it
  is *both* a deterministic LEI validator and a modest company-name reconciler.
- **Access / limits / cost:** **fully free / open data**, no registration. API based on the
  Golden Copy; **bulk Concatenated + Golden Copy + delta files published 3×/day**
  ([Golden Copy](https://www.gleif.org/en/lei-data/gleif-golden-copy);
  [Open Data](https://www.gleif.org/en/about/open-data)) — so we can self-host the whole dataset.
- **Licensing:** CC0-style open; full pool free to download and incorporate.
- **Long-tail coverage:** only entities that *needed* an LEI (financial-transaction
  counterparties, MiFID/EMIR-regulated, etc.). A tiny non-financial LLC or a startup with no
  trading activity won't have one. So: high precision, low recall on the general-business long
  tail.

#### OpenCorporates — **NEVER at launch (paid; restrictive)**
- **Entity types:** *companies* from official registries worldwide (broadest real coverage of
  the company long tail of any source here).
- **Access / limits / cost:** effectively a paid product now. Self-serve API plans
  **Essentials £2,250/yr, Starter £6,600/yr, Basic £12,000/yr**; standard plans cap at **500
  calls/month, max 200/day**
  ([OpenCorporates pricing 2026 — Zephira](https://zephira.ai/opencorporates-pricing-explained-2026-plans-api-limits-licensing-and-what-it-means-in-production/);
  [pricing page](https://opencorporates.com/pricing/)). Free API only if your *whole* product is
  released under an open **share-alike + attribution** licence, or for vetted
  NGOs/journalists/universities/anti-corruption research
  ([data-access blog](https://blog.opencorporates.com/category/use-case/data-access/)).
- **Licensing:** **share-alike database rights** on the free tier — viral, and incompatible with
  a closed commercial memory product. Paid tiers remove it.
- **Verdict:** the share-alike obligation and the 200-calls/day cap make it a non-starter as a
  core tier-0 for a general/commercial memory. **Revisit only** if a customer's scope is
  company-KYB-heavy and they fund a paid plan; even then it's a scope connector, not core.

#### ISBN — **NEVER as an "authority" (no canonical free API)**
- **Entity types:** *books / editions* keyed by ISBN-13.
- **Reality:** ISBN has **no single free canonical resolver API**. The agency assigns numbers;
  resolution is done by third parties of varying quality:
  - **Open Library** — free, no key, but **crowd-sourced → patchy/variable completeness** and
    bulk-scraping discouraged.
  - **Google Books** — free, indexes ~2× Open Library, good metadata, but ToS conditions.
  - **ISBNdb** — ~111M titles, the largest, but **paid**.
  ([Vinzius: free & paid ISBN APIs](https://www.vinzius.com/post/free-and-paid-api-isbn/);
  [ISBNDB blog](https://isbndb.com/blog/book-api/)).
- **Long-tail:** **recently self-published / niche books are exactly where the free sources are
  weakest** ("if a book is recently published or not listed, it hasn't reached their sources").
- **Verdict:** not worth a tier-0 connector for a *general* memory. If a books/reading scope
  appears, wire Google Books or Open Library as a best-effort *scope* enricher — and treat a
  bare ISBN string mainly as a deterministic key, not as a fuzzy reconciler.

#### GitHub — **SPECIAL-CASE connector only (software scopes)**
- **Entity types:** developers (`@login`, stable numeric user ID), repositories (`owner/repo`,
  stable repo ID), organizations. Authoritative *within the software domain*.
- **Access / limits / cost:** free; **authenticated REST 5,000 req/hr** (GitHub App
  installations scale up to 12,500–15,000), 100 concurrent / 900 points-per-minute secondary
  limits, unauthenticated only 60 req/hr
  ([GitHub rate-limit docs](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)).
- **Reconciliation:** exact handle/repo lookup is deterministic and excellent; user search exists
  but display names are noisy.
- **Verdict:** **not a general tier-0** — most research/knowledge entities are not GitHub
  accounts. But for any developer/OSS/project-tracking K2 scope (D16), it's a high-value
  scope-triggered connector with great precision on handles and repo IDs.

### 2.3 Crosswalk note (why the set is small)

OpenAlex already carries DOI, ORCID, ROR, ISSN, and Wikidata QID on its records. So OpenAlex +
Wikidata effectively give us a **crosswalk hub**: resolve once, get the other IDs for free. That
is why the recommended core is small — Crossref/DOI, ORCID, and GLEIF are kept mainly as
*deterministic ID validators* for the "identifier literally appears in the document" path, not
as independent fuzzy resolvers.

---

## 3. Confidence & gaps

**Well-supported (high confidence):**
- Licensing posture: Wikidata + OpenAlex CC0; GLEIF open; OpenCorporates share-alike/paid;
  Crossref free-to-cache. All directly from primary sources.
- Coverage magnitudes: Wikidata ~122M items, OpenAlex ~271M works / ~90M authors, ORCID >20M,
  GLEIF ~2.93M LEIs, ISBNdb ~111M titles. All cited to 2025-dated primary/official pages.
- Rate-limit specifics for Crossref (2025-12-01) and GitHub (5,000/hr) — from official docs.
- Wikidata being the *only* one of the eight with a standardized multi-type reconciliation API
  — corroborated by the W3C CG and the reconciliation-api spec.

**Changed-recently / flag carefully (medium confidence):**
- **OpenAlex's API-key + "$1/day credit" model and polite-pool deprecation.** The developers
  page confirms keys + a $1/day free allowance and a quarterly free snapshot, but the *exact*
  credit-to-request conversion is not published precisely — verify against
  `openalex.org/settings/api` and `help.openalex.org` before building. Mitigation: rely on the
  free quarterly CC0 snapshot for backfill, API only for incremental.
- **Wikidata reconciliation rate-limiting.** The 429 / ~30%-throttled figure is from OpenRefine
  community reports, not a published Wikimedia SLA. Treat the public `reconci.link` as
  unreliable for batch; **self-hosting is the safe assumption.**

**Genuine gaps (could not verify — do not invent):**
- **No clean published precision/recall (false-positive) numbers for any of these reconciliation
  APIs.** The literature describes the mechanisms (feature clustering, fuzzy name/address
  matching) qualitatively; I found no benchmark giving, e.g., "Wikidata reconciliation precision
  = X% on long-tail persons." Our own golden set (`entity_registry.md` §7.1) will have to measure
  this — we cannot import a vendor number.
- **Exact long-tail recall per type** (what fraction of a *typical user's* coworkers/small
  vendors appear in Wikidata/OpenCorporates) is unmeasured here; the qualitative answer ("notable
  → yes; genuinely obscure → no") is well-supported, the quantitative one is not.
- ORCID and OpenCorporates *per-second/credit* limits are approximate (drawn from
  forum/secondary pages); confirm in their dashboards before production.

---

## 4. Recommendation for ugm

**Tier-0 connector set at launch (core, ships in the registry):**

| Connector | Role | Trigger | Why |
|---|---|---|---|
| **Wikidata** (reconci API, self-hosted) | General multi-type **reconciler** for Person/Org/Place/Concept/Work | name string + core type | Only standardized free reconciliation surface; CC0; QID/redirect model matches ours |
| **OpenAlex** (snapshot + API) | Scholarly **Author / Work / Institution** resolver + ID crosswalk hub | research/scholarly type or DOI/ORCID present | CC0; deepest scholarly long tail; carries DOI/ORCID/ROR/QID crosswalk |
| **DOI / Crossref** | Deterministic **Work** validator | DOI literally in source text | precision ≈ 1.0; free |
| **ORCID** | Deterministic **Person** validator | ORCID iD literally in source text | precision ≈ 1.0; free public API |
| **GLEIF LEI** (bulk + API) | Deterministic **Organization** validator + modest company reconciler | LEI in text, or financial-entity org | open/CC0; Level-2 parent edges feed the graph |

**Scope-triggered opt-in connectors (NOT core; wired only when a K2 scope needs them — D16):**
- **GitHub** — developer/OSS/project scopes (handle + repo IDs, 5k req/hr).
- **Google Books / Open Library** — reading/library scopes (best-effort, ISBN as a key).

**Never at launch:** **OpenCorporates** (share-alike licence is viral for a closed product;
£2,250+/yr; 200 calls/day cap) and **ISBN-as-a-general-authority** (no free canonical resolver;
weakest exactly on the self-published long tail).

**Fallback when no authority matches (the load-bearing rule):**
- **Tier 0 is an accelerator, never a gate.** On a miss, do *not* block and do *not* invent an
  external ID — **mint a local entity ID and fall through to tiers 1–5** (exact → fuzzy → phonetic
  → embedding → adjudication), recording the resolution-decision row with `method = tier0_miss`
  (per the append-only verdict pattern, `entity_registry.md` §4). Most of a real user's entities
  (coworkers, small vendors, internal projects) will be long-tail misses — this must be the
  *common, cheap* path, not an error.
- **When tier 0 *does* hit, store the external ID as an alias, not as the canonical entity_id.**
  Our `entity_id` stays internal and **never reused** (D-style governance, `entity_registry.md`
  §2). External IDs (QID, DOI, ORCID, LEI) live in the `aliases` table with provenance +
  confidence + first/last-seen — so a later Wikidata merge/redirect is just an alias update, and
  a wrong external match is reversible by superseding the decision row (reversibility invariant,
  §7.7). This keeps us from importing another authority's identity mistakes into our spine.
- **Conservative-merge discipline still applies (§1, §7.4).** A tier-0 *match* is strong evidence
  but not an auto-merge of two of *our* entities above the blast-radius threshold; treat
  "two mentions both resolved to the same QID" as a high-confidence candidate that still respects
  the degree/evidence guardrail before fusing hubs.

**Decision ties:**
- Implements **D15**'s "external-authority anchoring (tier 0 of resolution)" concretely, and
  realizes the "anchor outward against curated authority sets" lesson (`entity_registry.md` §2).
- Reinforces **D6/D7**: tier-0 data and the resolver index are **derived/projected** state. Bulk
  CC0 snapshots (Wikidata dump, OpenAlex quarterly snapshot, GLEIF Golden Copy) are rebuilt with
  the same rebuild-first discipline; nothing about an external authority becomes an authority in
  *our* system — Postgres + our registry stay the single source of truth (D1/D6).
- Answers **`entity_registry.md` §8 open-question #4** ("which ones at launch? DOI? ORCID?
  none?"): **yes to DOI + ORCID + LEI as deterministic validators, plus Wikidata + OpenAlex as
  reconcilers; no to OpenCorporates and ISBN; GitHub only per-scope.**
- **Operational caveat to carry into `registries_design.md`:** self-host the Wikidata
  reconciliation service and bulk-load OpenAlex/GLEIF snapshots — do not make the write path
  depend on public rate-limited endpoints, and budget for OpenAlex's new key/credit model.

## Sources
- [OpenAlex Developers (keys/credits/snapshot)](https://developers.openalex.org/) ·
  [OpenAlex Pricing](https://help.openalex.org/hc/en-us/articles/24397762024087-Pricing) ·
  [OpenAlex 2025 in Review](https://blog.openalex.org/openalex-2025-in-review/) ·
  [OpenAlex arXiv paper](https://arxiv.org/pdf/2205.01833) ·
  [Zheng 2025 JASIST (China coverage gaps)](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.70013)
- [Crossref REST API rate-limit changes (Dec 2025)](https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/) ·
  [Crossref metadata license](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-metadata-license-information/)
- [ORCID 10M milestone](https://info.orcid.org/10m-orcid-ids/) ·
  [ORCID public API client registration](https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/) ·
  [ORCID rate-limit clarification](https://groups.google.com/g/orcid-api-users/c/ehv8sCfs-ZM) ·
  [Wikipedia: ORCID](https://en.wikipedia.org/wiki/ORCID)
- [Wikidata:Statistics](https://www.wikidata.org/wiki/Wikidata:Statistics) ·
  [Wikipedia: Wikidata](https://en.wikipedia.org/wiki/Wikidata) ·
  [WikiProject Companies](https://www.wikidata.org/wiki/Wikidata:WikiProject_Companies) ·
  [Reconciliation Service API spec](https://reconciliation-api.github.io/specs/latest/) ·
  [W3C Entity Reconciliation CG](https://www.w3.org/community/reconciliation/) ·
  [Running a reconciliation service for Wikidata](https://ceur-ws.org/Vol-2773/paper-17.pdf) ·
  [OpenRefine: Wikidata reconciliation rate limits](https://forum.openrefine.org/t/wikidata-reconciliation-service-changes-wikimedia-rate-limits/2779) ·
  [OpenRefine issue #7731 (User-Agent throttling)](https://github.com/OpenRefine/OpenRefine/issues/7731) ·
  [Henri-Lo/openrefine-wikidata (self-host)](https://github.com/Henri-Lo/openrefine-wikidata)
- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api) ·
  [GLEIF Golden Copy](https://www.gleif.org/en/lei-data/gleif-golden-copy) ·
  [GLEIF Open Data](https://www.gleif.org/en/about/open-data) ·
  [The LEI in Numbers 2025](https://www.gleif.org/en/newsroom/blog/the-lei-in-numbers-global-transparency-and-digitalization-push-drives-lei-adoption-in-2025)
- [OpenCorporates pricing (2026, Zephira)](https://zephira.ai/opencorporates-pricing-explained-2026-plans-api-limits-licensing-and-what-it-means-in-production/) ·
  [OpenCorporates pricing page](https://opencorporates.com/pricing/) ·
  [OpenCorporates data-access (free tier terms)](https://blog.opencorporates.com/category/use-case/data-access/)
- [Vinzius: free & paid ISBN APIs](https://www.vinzius.com/post/free-and-paid-api-isbn/) ·
  [ISBNDB book API blog](https://isbndb.com/blog/book-api/)
- [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

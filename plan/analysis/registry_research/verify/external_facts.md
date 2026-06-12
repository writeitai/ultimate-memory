# External-system fact-check — R4 / R8 / Wikidata semantics

**Scope.** Adversarial verification of external-SYSTEM factual claims in
`registry_research/questions/*.md`, focused on R4 (OpenAlex / Crossref / ORCID / Wikidata /
GLEIF / OpenCorporates / ISBN / GitHub) and R8 (Senzing behaviour, Wikidata redirect/QID
semantics). Default posture: skeptical; "Confirmed" requires a traceable vendor/official source.

**Headline.** No hallucinated systems, no invented capabilities, no fabricated API/licensing
facts found. Every load-bearing external claim checked traces to a primary/official source and
matches. A few numbers are *secondary-sourced approximations* the docs themselves flag (and R4
already flags them too). Net: R4 and R8 are factually sound and unusually well-hedged. Verdict
table below; minor caveats at the end.

Legend: ✅ Confirmed · 🟡 Confirmed-with-nuance · ⚠️ Weakly-sourced (flag) · ❌ Wrong/hallucinated.

| # | Claim (file:loc) | Verdict | Corrected / confirmed fact + source |
|---|---|---|---|
| 1 | OpenAlex now uses **API keys + a credit model**; free key ≈ **$1/day** usage; **polite pool deprecated**; free **quarterly** CC0 snapshot (R4 §2.2 OpenAlex, lines 122-130) | ✅ | Verbatim on vendor page: "With your free key, you get $1/day of free usage"; key obtained at `openalex.org/settings/api`; snapshot "updated quarterly"; paid plans add monthly snapshots/daily change files. — https://developers.openalex.org/ |
| 2 | Crossref rate limits **changed 2025-12-01**: public 5 req/s single (1 concurrent), 1 req/s list; polite 10 req/s single (3 concurrent), 3 req/s list (R4 §2.2 Crossref, lines 144-147) | ✅ | Exact match incl. effective date and the "first change since 2013" framing. — https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ |
| 3 | **OpenCorporates** self-serve **Essentials £2,250 / Starter £6,600 / Basic £12,000 per year**; standard plans cap **500 calls/month, 200/day** (R4 §2.2 OpenCorporates, lines 197-199) | ✅ | Prices exact. Caps exact for Essentials (500/mo, 200/day); higher tiers raise caps (Starter 2,500/mo·500/day, Basic 5,000/mo·1,000/day). A call counts even on no-match. — https://zephira.ai/opencorporates-pricing-explained-2026-plans-api-limits-licensing-and-what-it-means-in-production/ |
| 4 | **GLEIF ~2.93M active LEIs, +355k in 2025 (+13.5%)** (R4 §2.2 GLEIF, line 178) | ✅ | Exact: ">2.93M active LEIs by end of 2025; >355,000 issued in 2025; 13.5% growth, up from 11.5% in 2024." — https://www.gleif.org/en/newsroom/blog/the-lei-in-numbers-... |
| 5 | **Wikidata ~122M items**; persistent **QIDs never reused**; merge leaves a **redirect** (R4 line 79-82; R8 lines 168-179, 277) | ✅ | Wikidata:Statistics shows 122,114,319 items. Merge pools data into the survivor and **redirects** the obsolete QID; redirects "should under no circumstances be deleted or repurposed" so external Q-IDs stay "stable and reliable." Exactly the model R4/R8 attribute to it. — https://www.wikidata.org/wiki/Wikidata:Statistics ; https://meta.wikimedia.org/wiki/Wikidata/Development/Entity_redirect_after_merge ; Help:Redirects |
| 6 | **ORCID >20M iDs, ~9M actively used (2024)** (R4 §2.2 ORCID, lines 158-159) | ✅ | "Over 20 million ORCID iDs issued since 2013; 9 million records actively used in 2024." — https://en.wikipedia.org/wiki/ORCID ; https://info.orcid.org/10m-orcid-ids/ |
| 7 | **OpenAlex ~271.3M works** (Nov 2025) + ~192M lower-quality expansion pack; **CC0** (R4 lines 113-114, 131) | ✅ | "271.3M works as of Nov 2025" + DataCite/IR "expansion pack" of ~192M; full dataset CC0 with quarterly snapshots. — https://arxiv.org/html/2512.16434v1 ; blog.openalex.org 2025-in-review |
| 8 | **GitHub: 5,000 req/hr authenticated, 60 req/hr unauthenticated**; App installs scale higher (R4 §2.2 GitHub, lines 230-232) | 🟡 | 5,000/hr (PAT/app install) and 60/hr unauth confirmed; GitHub Enterprise Cloud installs = **15,000/hr**. The intermediate "**12,500**" figure is NOT on this page (derives from GitHub's per-repo/per-user scaling formula, max 12,500) — defensible but not directly sourced. — https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api |
| 9 | The **Reconciliation Service API** is a W3C **Community Group** spec (v0.2), **not yet a W3C Standard**, migration to a **Working Group "expected in 2026"** (R4 lines 84-89) | ✅ | Confirmed: edited by the W3C Entity Reconciliation CG; v0.2 + 1.0-draft exist; WG transition "expected in 2026." R4's careful "not yet a Standard" hedge is correct. — https://www.w3.org/community/reconciliation/ ; https://reconciliation-api.github.io/specs/latest/ |
| 10 | Wikidata is the **only** one of the eight with a general, standardized, multi-type reconciliation endpoint (`wikidata.reconci.link`) (R4 lines 22-25, 73) | 🟡 | Directionally correct and well-argued: it is the only one shipping a Reconciliation-Service-API endpoint. Pedantic caveat — GLEIF offers fuzzy name/address matching (R4 acknowledges this as a "modest company reconciler"), and OpenAlex offers a domain REST filter surface; so "only general/standardized multi-type" is the accurate framing, which R4 uses. Not an error. |
| 11 | **Senzing**: generic-identifier detection — shared SSN flagged generic, **reevaluates all prior records** with that number; **sequence neutrality / self-correcting the past**; explainability why/why-not/how (R8 §2.4, lines 145-159) | ✅ | Quote is verbatim on vendor page: "when multiple people are using the same SSN, our software detects it, labels the SSN as generic and reevaluates all prior records with that number." Attribute-behaviour-principles framing confirmed. — https://senzing.com/what-is-principle-based-entity-resolution/ |
| 12 | Senzing's three named attribute principles = **Frequency, Exclusivity, Stability** (R8 lines 145-147) | 🟡 | The *concept* (attribute-behaviour principles, e.g. SSN→one person vs DOB→many) is confirmed on the public page; the three exact capitalized names live in Senzing's "Principle-Based ER Explained" whitepaper (gated download), not the open HTML page. Consistent with Senzing's terminology, not invented — but sourced to a doc not independently re-fetched here. R8 already attributes it to the whitepaper. |
| 13 | **OpenCorporates free tier = viral share-alike + attribution**, free only for open/NGO/journalist use (R4 lines 200-205) | 🟡 | Plausible and historically accurate to OpenCorporates' long-standing policy, but the *specific cited Zephira page does not cover the free tier* — it only lists the paid plans. The share-alike claim should be re-anchored to OpenCorporates' own data-access/legal pages (already listed in R4 Sources) before it is treated as load-bearing. Not contradicted; just under-sourced on the cited page. |
| 14 | "OpenAlex subsumes most of Crossref's value" / carries DOI·ORCID·ROR·ISSN·QID crosswalk (R4 lines 120-121, 152-154, 241) | ✅ | Consistent with OpenAlex's documented entity model (works keyed/cross-referenced by DOI, ORCID, ROR, ISSN, Wikidata QID). Reasonable architectural claim, supported by OpenAlex docs. |
| 15 | Wikidata reconciliation **public instance is rate-limited / ~30% of OpenRefine-UA requests 429'd** (R4 lines 90-99) | ⚠️ | Sourced to OpenRefine community forum/issue, NOT a Wikimedia SLA — R4 explicitly flags this as community-reported and recommends self-hosting. Honest hedge; treat the 30% figure as anecdotal. — https://forum.openrefine.org/... ; OpenRefine issue #7731 |

## No hallucinations found
- No invented system names. All eight authorities (OpenAlex, Crossref, ORCID, Wikidata, GLEIF,
  OpenCorporates, ISBN sources, GitHub) are real with correctly described scopes.
- No fabricated capabilities: Wikidata reconciliation API, GLEIF fuzzy matching + Level-2
  parent edges, OpenAlex crosswalk, Senzing generic-identifier re-evaluation — all real.
- No wrong licensing facts: Wikidata CC0 ✅, OpenAlex CC0 ✅, GLEIF open/CC0-style ✅,
  Crossref free-to-cache ✅, OpenCorporates paid/share-alike ✅.

## Residual caveats (none fatal)
1. **GitHub "12,500"** (claim 8) — not on the cited docs page; comes from GitHub's scaling
   formula. Either cite the formula or drop the middle number; "5,000 / 15,000" is the sourced pair.
2. **OpenCorporates free-tier share-alike** (claim 13) — re-anchor to OpenCorporates' own
   legal/data-access pages, not the Zephira pricing article (which omits the free tier).
3. **Senzing Frequency/Exclusivity/Stability names** (claim 12) — gated whitepaper; the
   open page confirms the concept but not the three capitalized labels.
4. **Wikidata reconci.link 30%-throttle** (claim 15) and **OpenAlex exact credit→request
   conversion** — both already flagged by R4 as approximate/community-sourced. Correct to verify
   in-dashboard before building; do not treat as SLAs.

**Bottom line:** R4 and R8's external-system facts are accurate, current (most numbers Dec-2025
dated and re-confirmed June 2026), and conscientiously hedged where uncertain. No corrections to
load-bearing facts are required; the four caveats above are sourcing-hygiene fixes, not errors.

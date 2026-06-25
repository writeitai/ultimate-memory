# M6 — Privacy, PII, biometrics & deletion for IMAGES + VIDEO at scale

Research for the multimodal extension of **ugm** (text-centric memory pipeline, full scale). Scope:
the legal/operational constraints on faces, voices, and on-screen PII in media, and the engineering
pattern for detection/flagging, redaction, biometric non-storage, and a deletion cascade that reaches
large media blobs **and** every derivative (transcripts, keyframes, OCR text, embeddings, snapshots).
Tied to ugm decisions D1/D6/D7/D12/D36–D40/D37/D42/D43/D44.

Convention: **[V]** = verified against a cited primary/authoritative source; **[I]** = inference or
engineering judgment; **[?]** = could not verify a specific number/claim, flagged.

---

## 1. Key findings (bullets)

- **The single biggest compliance lever is a *design choice*, not a control: don't do recognition.**
  Under GDPR, a face/voice is "biometric data," but it becomes **Article 9 *special category*** (near-banned
  by default, needs explicit consent) **only when processed "for the purpose of uniquely identifying a
  natural person"** — i.e. building face/voiceprints and matching them. Face/PII *detection-and-blur*,
  scene-cutting, and transcription are **not** unique identification, so they stay in ordinary
  personal-data territory. **[V]** A memory system that **detects and redacts** but **never builds a
  face/voice gallery** keeps almost all media out of the special-category regime. **[I]**

- **Biometric *templates* are the liability, and ugm has no reason to store them.** Face embeddings and
  pyannote **speaker embeddings** (the fixed-size voiceprint vectors whisperX's diarizer produces) are
  the exact artifacts BIPA, GDPR Art. 9, and the EU AI Act gate hardest. **[V]** Diarization only needs
  these vectors *transiently* to label speakers within one file (`SPEAKER_00`…); the durable output is a
  transcript with relative labels, not a cross-file identity. **Recommendation: never persist
  face/voice templates as matchable durable state.** **[I]**

- **BIPA is the sharp edge: private right of action, $1,000 / $5,000 per violation, covers voiceprints
  and face-geometry scans.** Texas (CUBI, up to $25k/violation) and Washington (up to $7.5k/violation)
  are AG-enforced only. The 2024 Illinois amendment (SB 2979) caps it at one violation per person per
  collection method (no more per-scan multiplication), applied retroactively. **[V]** The EU AI Act
  (prohibitions live since Feb 2025) **outright bans** untargeted face-scraping to build databases,
  biometric categorization of sensitive traits, and workplace/education emotion recognition. **[V]**

- **Redaction belongs in E0, and it fits D37 perfectly: the *redacted* derivative is the canonical
  mounted/indexed artifact; the raw original lives in the strict, never-mounted raw bucket.** ugm already
  splits raw (immutable, cold, strict IAM, not on the browse path) from artifacts (mounted, indexed).
  Adding a **versioned redaction stage** to the E0 sub-worker chain (D36/D38) makes "everything an agent
  ever sees is redacted" a structural guarantee, not a policy hope. **[I]**

- **ugm's architecture makes deletion *tractable* where it is intractable elsewhere — but two gaps must
  be closed.** Because every derivative is a **versioned, replay-from-storage projection** (D7), not a
  trained model, ugm sidesteps the unsolved "machine unlearning" problem entirely: you delete derivatives
  by dropping/re-deriving them, you never have to scrub weights. **[I]** The two real gaps (already on
  ugm's own list, questions.md #24): (a) plain object-delete does **not** purge **immutable backups /
  PITR / GCS soft-delete (7-day floor) / old P-snapshots** — the fix is **crypto-shredding** (encrypt
  raw + sensitive derivatives under a **per-document (or per-subject) key**; destroy the key → all copies,
  including backups, become unrecoverable); (b) **Lance** deletes are tombstones until **compaction
  with prune** — a hard-delete obligation must trigger prune, not just a soft delete. **[V]**

---

## 2. Evidence & detail

### 2.1 Legal/operational constraints

**GDPR — biometric data and the "unique identification" trigger.**
Art. 4(14) defines biometric data as data from "specific technical processing relating to the physical,
physiological or behavioural characteristics" that "allow or confirm the unique identification" of a
person — explicitly faces and (via the ICO/EDPB reading) voices. **[V]** Crucially, Art. 9 special-category
status attaches **only when the processing purpose is to uniquely identify**: "biometric data is only
considered special category data when it is processed specifically for the purpose of uniquely identifying
a natural person." A facial *image* on its own is ordinary personal data; running it through face
recognition makes it special-category. **[V]** Processing special-category data requires **both** an Art. 6
lawful basis **and** an Art. 9(2) condition (for a private memory product, realistically **explicit
consent**). **[V]**
- https://gdpr-info.eu/art-9-gdpr/ , https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/key-data-protection-concepts/

**GDPR — erasure (Art. 17) and the anonymisation threshold (Recital 26).**
Art. 17 ("right to be forgotten") requires erasure "without undue delay." **[V]** Recital 26 sets a **very
high bar** for "truly anonymous": account must be taken of "all the means reasonably likely to be used …
either by the controller or by another person." **Pseudonymised or reversibly-transformed data remains
personal data.** **[V]** Engineering consequence: a **face or voice embedding is not "anonymised"** — it is
designed to re-identify, so it is personal (and, if used for matching, biometric) data and is itself
in-scope for erasure. You cannot keep the embedding and call the source "deleted." **[I, grounded in V]**
- https://gdpr-info.eu/recitals/no-26/ , https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf

**BIPA (Illinois, 740 ILCS 14) — the one with teeth.**
Covers "retina/iris scans, fingerprints, **voiceprints**, or scans of hand or **face geometry**." **[V]**
**Private right of action**, statutory damages **$1,000 per negligent / $5,000 per intentional or reckless
violation**, plus fees. **[V]** Requires: informed **written consent** before collection; a **public
written retention/destruction policy** (destroy "when the purpose has been satisfied or within 3 years of
the last interaction," per the statute); and limits on **disclosure** to third parties (Sec. 15(d)) — which
makes shipping faces/voices to a cloud API a regulated disclosure. **[V, statute]** 2024 **SB 2979** narrows
"per-scan" exposure to **one violation per person per collection method**, held **retroactive** by the 7th
Circuit (2024). **[V]**
- http://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57 , https://www.foley.com/insights/publications/2024/08/illinois-damages-biometric-privacy-law/ , https://www.dwt.com/blogs/privacy--security-law-blog/2024/08/illinois-bipa-biometrics-law-amended-for-damages

**Other US states.** Texas **CUBI**: **no private right of action**, AG-enforced, civil penalty **up to
$25,000 per violation**. Washington biometric law: AG-enforced, **up to $7,500 per violation**. **[V]**
Several more states have proposed BIPA-style bills. **[V]**
- https://www.biometricupdate.com/202208/beyond-bipa-mitigating-biometric-data-legal-risks-under-texas-and-washington-biometrics-laws , https://www.recordinglaw.com/us-laws/data-privacy-laws/biometric-privacy-laws/

**EU AI Act — what is *prohibited* vs *high-risk* (prohibitions effective Feb 2025).**
- **Prohibited:** (i) **untargeted scraping of facial images** from the internet/CCTV to build face-recognition
  **databases**; (ii) **biometric categorization** inferring race, political opinion, trade-union membership,
  religion, sex life, or sexual orientation; (iii) **emotion recognition in workplace/education** (except
  medical/safety). **[V]**
- **High-risk:** remote biometric identification; biometric categorization by sensitive attributes;
  emotion recognition outside workplace/education. 1:1 verification (e.g. phone unlock) is generally **not**
  high-risk. **[V]**
- Direct hit for a memory system: **auto-building a face/voice index across ingested media is exactly the
  prohibited "untargeted database" pattern.** Reinforces "detect-and-redact, never recognize." **[I]**
- https://artificialintelligenceact.eu/annex/3/ , https://www.bundesnetzagentur.de/EN/Areas/Digitalisation/AI/08_ProhibitedPractices/start.html , https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/

### 2.2 Detection + redaction — concrete tools, costs, mechanism

**Faces in images/video (open-source, self-hosted — privacy-preferred default).**
- **`deface` (ORB-HD, MIT license).** CLI; detector is **CenterFace** (a small DNN); analyzes each video
  frame independently, applies blur ellipse or black box per detected face. Local, no cloud, no template
  stored. **[V]** Ideal as the video/image face-redactor: fast, deterministic, versionable.
  - https://github.com/ORB-HD/deface
- Self-hosting matters legally: processing biometrics **locally** avoids a BIPA Sec. 15(d) **disclosure** and
  a GDPR Art. 28 **processor** relationship that a cloud API would create. **[I, grounded in V]**

**Faces + objects + on-screen text (cloud, managed).**
- **AWS Rekognition Video** — `DetectFaces` returns bounding boxes per frame; **blurring is done separately**
  (the API detects; you composite the redaction). Video billed **per minute**; order-of-magnitude **~$0.10
  /min** for analysis (image `DetectFaces` ≈ $0.001/image first 1M). **[V for "per-minute, blur-is-separate";
  exact $/min ?]** AWS publishes a connected-car redaction reference architecture using exactly this pattern.
  - https://aws.amazon.com/rekognition/pricing/ , https://aws.amazon.com/blogs/architecture/field-notes-redacting-personal-data-from-connected-cars-using-amazon-rekognition/
- **Google Cloud Sensitive Data Protection (DLP)** — image inspect/redact: **OCR** for text PII **plus**
  object detection (it can classify/redact **persons, license plates, photo-ID cards**), masking with an
  opaque rectangle (`image.redact`). 200+ infoType detectors. Priced **per bytes processed**. **[V; exact
  $/byte ?]**
  - https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-image-redaction , https://cloud.google.com/sensitive-data-protection/pricing

**On-screen text / document PII (the other half — "PII printed in the frame").**
- **Microsoft Presidio Image Redactor (MIT).** Tesseract (or Azure Document Intelligence) **OCR** →
  Presidio Analyzer (NER + regex over 200+ entity types) → redact the bounding boxes of detected PII text
  in images, incl. **DICOM** medical images. Newer recognizers add **FacesRecognizer**, **LicensePlateRecognizer**,
  and **QR-code** content. **[V]** This is the natural redactor for **screenshots, scanned forms, ID photos**
  and for **OCR'd video frames**.
  - https://microsoft.github.io/presidio/image-redactor/ , https://github.com/microsoft/presidio
- **Screen-capture-specific PII** (passwords, API keys, JWTs, DB connection strings, secrets) needs an
  OCR+NER pipeline tuned for screen content — `screenpipe/screenleak` defines ~12 canonical categories incl. a
  dedicated **secrets** class. **[V]** Relevant if ugm ever ingests screen recordings.
  - https://screenpipe.github.io/screenleak/

**Audio / voice (whisperX, vendored in ugm `_additional_context/`).**
- whisperX = Whisper ASR (word-level timestamps) **+ pyannote** speaker diarization. **[V, repo README]**
- pyannote "generates **vector embeddings** that capture acoustic/timbral characteristics … grouped by
  clustering; each cluster = a speaker." **A speaker embedding is a compact fixed-size voiceprint.** **[V]**
  These vectors are biometric. The diarizer needs them only to cluster *within* a file; output labels are
  **relative** (`SPEAKER_00`), not real-world identities, unless you deliberately store and match embeddings
  across files. **[V/I]**
- The pyannote diarization model is **gated** (HuggingFace token + accepted user agreement) — an operational
  step, and a reminder that this is a regulated capability. **[V, repo README line 116]**
- **PySceneDetect** (vendored) does scene/cut detection → keyframe extraction; keyframes are derived images
  that themselves may contain faces/PII and must inherit the same redaction + deletion treatment. **[V]**

### 2.3 The deletion cascade — mechanism at each store

**The hard truth: "delete the row/object" ≠ erasure, because of immutability everywhere.**
- **GCS soft delete** is **on by default with a 7-day floor**, and a soft-deleted object **cannot be purged
  early**; **bucket-lock/retention policies** create deliberately **immutable** windows. **[V]** ugm's **raw
  bucket** (D37, cold/archival, audit/legal provenance) is exactly where long retention is desirable —
  which *conflicts* with "erase now."
  - https://docs.cloud.google.com/storage/docs/soft-delete , https://docs.cloud.google.com/storage/docs/bucket-lock
- **Postgres PITR backups** (overall_design §7) retain the deleted rows for the backup window.
- **P-plane snapshots** (D7): old immutable LadybugDB/Lance/corpus-fs snapshots in GCS still contain the
  data until they age out.

**Crypto-shredding (crypto-erasure) — the mechanism that resolves immutability vs. erasure. [V]**
Encrypt the personal/biometric payload under a **per-subject (or per-document) key**; to erase, **destroy
the key** — every copy, *including immutable backups and old snapshots*, becomes unrecoverable ciphertext,
with no row rewrite. Per-subject key isolation is the named requirement (destroying one key must not break
anyone else's data). Widely cited as the practical Art. 17 answer for distributed/cloud systems with
retention obligations. **[V]**
- https://en.wikipedia.org/wiki/Crypto-shredding , https://granit-fx.dev/blog/crypto-shredding-gdpr-erasure-without-deleting-rows/

**Lance (P1) — deletes are tombstones until compaction. [V]**
Lance "marks rows as deleted" via **deletion files** (soft delete) to avoid rewriting fragments / rebuilding
ANN indices; the data is physically removed only by **compaction with `OptimizeActions::Prune` (or `All`)**.
**A GDPR hard-delete on a vector store therefore must trigger prune, not just a `DELETE`.** **[V]**
- https://medium.com/etoai/you-can-now-delete-rows-in-lance-and-lancedb-8200d885d1cb , https://docs.lancedb.com/lance

**Why ugm escapes the *worst* deletion problem (machine unlearning). [I, grounded in V]**
The research consensus is that once personal data is **baked into trained model weights**, removal is
"nearly infeasible without costly retraining," and approximate unlearning suffers "superficial forgetting"
(features remain even when logits are suppressed). **[V]** ugm **does not train models** — its derivatives
(transcripts, keyframes, captions, embeddings, claims, relations, observations, snapshots) are
**versioned, replay-from-storage projections** (D7). Deleting them is an ordinary drop/re-derive, not
unlearning. **This is a genuine architectural advantage and should be stated as one.**
- https://arxiv.org/pdf/2412.06966 , https://gdprlocal.com/gdpr-machine-learning/

---

## 3. Confidence & gaps

- **High confidence (verified):** the GDPR Art. 9 "unique-identification" trigger; BIPA's private right of
  action and $1k/$5k structure + 2024 SB 2979 cap; Texas/Washington AG-only + penalty ceilings; EU AI Act
  prohibitions (Feb 2025); Recital 26 anonymisation bar; tool capabilities (deface/CenterFace, Presidio
  image redactor, whisperX→pyannote speaker embeddings, PySceneDetect); Lance soft-delete-then-prune; GCS
  soft-delete 7-day floor + bucket lock; crypto-shredding as the backup/immutability answer; the
  machine-unlearning difficulty (which ugm avoids).
- **Medium / approximate:** **exact cloud prices.** AWS Rekognition Video is per-minute and "blur is a
  separate step" **[V]**, but the precise $/min (the search surfaced both "~$0.10/min" and "$0.00817/min")
  is **[?]** — verify on the live pricing page per region/op before sizing. Google DLP image redaction is
  "per bytes processed" with **no exact figure retrieved [?]**.
- **Gaps / not independently verified:**
  - I did not verify a specific accuracy/recall benchmark for CenterFace or pyannote on *adversarial* media
    (small/occluded faces, far-field/overlapping voices). Redaction recall is the actual safety metric and
    should be measured on a ugm golden set — a missed face is an un-redacted face. **[flagged]**
  - "Voice is biometric under GDPR" is well-supported by ICO guidance **[V]**, but whether a *given*
    diarization use is "for the purpose of unique identification" (Art. 9 trigger) is fact-specific. **[I]**
  - This is research, **not legal advice**; jurisdiction-specific counsel needed before processing real
    biometric data, especially anything touching Illinois residents.

---

## 4. Recommendation for ugm — make media privacy a first-class E0 concern

The throughline: ugm's existing decisions (raw/artifact split D37, versioned replay-from-storage D7,
per-doc idempotent sub-workers D36/D12, the entity registry, origin stamping D42) already give it most of
the machinery. Media privacy is not a bolt-on; it is **one more versioned E0 sub-worker plus three
discipline rules.** Concretely:

**R1 — Add a versioned `redact` sub-worker to the E0 chain; the redacted derivative is canonical.**
Extend D36's chain to `ingest → convert → **redact** → structure → crossref` (or fold redaction into the
D38 `convert(bytes, mime, hints)` module as a post-pass). Mechanism, cheap-first per D4:
- video/image → **deface/CenterFace** for faces + **Presidio Image Redactor** (OCR+NER) for on-screen text
  PII + license plates; audio → transcribe with **whisperX**, then **Presidio (text)** over the transcript.
- The **redacted** Markdown/keyframes/transcript become the **artifacts** that get mounted (D40/P3),
  chunked (E1), claimed (E2), and embedded (P1). The **raw original** stays in the **raw bucket** (D37:
  immutable, strict IAM, **never mounted**, audited-access only). This makes "an agent can only ever see
  redacted media" a **structural property of D37**, not a runtime check.
- Stamp `redactor_name/redactor_version` exactly like `converter_version` (D38). A better redactor
  re-redacts by version and rebuilds downstream (D7) — un-redactions become recoverable from raw, and
  *over*-redactions are fixable, without re-ingest.

**R2 — Biometric non-storage as a hard invariant (the BIPA / Art. 9 / AI-Act lever).**
- **Never persist face embeddings or pyannote speaker embeddings as durable, matchable templates.** Treat
  them as **transient compute** inside the diarize/redact worker; the durable output is redacted media +
  transcript with **relative** speaker labels (`SPEAKER_00`). This keeps ugm out of "processing for unique
  identification" (Art. 9), out of "building a face database" (AI-Act prohibition), and off BIPA's
  collection/retention/disclosure hooks for templates. **[I, grounded in V]**
- **Do not build a cross-media face/voice gallery.** If a future deployment genuinely needs speaker→person
  linking, that is an **opt-in, explicit-consent, documented per-deployment capability** with a retention
  schedule — a *non-goal of the core system*, written as a documented alternative (CLAUDE.md Rule 2), never
  a default.
- Record media-privacy facts as **observations/metadata, not biometrics**: `has_faces`, `has_onscreen_pii`,
  `contains_audio_of_unconsented_third_party`, `redaction_version`, `pii_flag_version` — flags on the
  `documents` row (D37 metadata), detected by the cheap-first cascade, used to gate mounting/retrieval.

**R3 — A subject-level deletion cascade keyed on the entity registry, executed by crypto-shredding +
prune.** ugm's deletion story today (E0 §2) is **document-level**; biometrics make the unit a **person**.
Close questions.md #24 and #13/O4 as follows:
- **Resolve the erasure request to an `entity_id`** via the registry (D17), then fan out to: source
  documents (mentions/E0), chunks (E1), claims (E2), relations + relation_evidence (E3), **observations +
  observation_evidence + observation_adjudications** (D43), and the raw+artifact blobs of every implicated
  document. The entity registry is the join the text pipeline already has — reuse it as the **deletion
  key** for media too.
- **Crypto-shred the durable copies.** Encrypt raw bytes (and any sensitive derivative artifacts) under a
  **per-document key wrapped by a per-subject KEK**; erasure = **destroy the key**. This is the *only*
  mechanism that reaches **PITR backups, GCS soft-delete (7-day floor), bucket-locked raw, and aged
  P-snapshots** without waiting out or rewriting immutable storage. **[V]** Plain object-delete cannot.
- **P1/Lance:** a hard-delete must run **compaction with prune**, not just a tombstone `DELETE`, or the
  embedding survives in fragments. Wire this into the deletion worker. **[V]**
- **P2/P3 + K:** projections (D6/D7) self-heal on the next rebuild because Postgres no longer has the rows
  — but **bound snapshot retention** (so old snapshots age out) or **crypto-shred snapshot keys** for
  immediate effect, and give K compiled markdown an **input-manifest (O4)** so the tombstone can reach the
  exact files referencing the erased subject. **[I, grounded in V]**
- This whole cascade is **tractable precisely because ugm doesn't train models** (R2/§2.3): derivatives are
  re-derivable projections, so there is no weight-unlearning residue. State that as a deliberate design
  property.

**R4 — Detect-and-flag at ingest, cheap-first (D4), so policy can gate before exposure.** Run face/PII
detection in `redact`; write the flags to Postgres metadata; let mounting (D40), P1 indexing, and retrieval
**consult the flags** (e.g. quarantine documents with `has_onscreen_pii` + `redaction_version IS NULL`).
Detection escalates cheap→expensive like every other ugm cascade; raw media is **never** the mounted object.

**R5 — Prefer self-hosted (deface/Presidio/whisperX/PySceneDetect, all OSS) over cloud biometric APIs by
default.** Local processing avoids a BIPA §15(d) **disclosure** and a GDPR Art. 28 **processor** chain for
the most sensitive payload. Cloud redaction (Rekognition/DLP) is an **opt-in** with a DPA, chosen per
deployment for throughput, not the default for biometric content. **[I, grounded in V]**

**Net:** media privacy slots into ugm as (1) a versioned `redact` E0 sub-worker that makes the redacted
derivative canonical and the raw original quarantined-but-shreddable, (2) a no-biometric-template
invariant that keeps the system out of the special-category / AI-Act / BIPA-template danger zone, and
(3) an entity-keyed, crypto-shred + Lance-prune deletion cascade that finally reaches the immutable
backups and snapshots the current document-level cascade cannot.

---

## Sources

Legal: https://gdpr-info.eu/art-9-gdpr/ · https://gdpr-info.eu/recitals/no-26/ ·
https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/key-data-protection-concepts/ ·
https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf ·
http://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57 ·
https://www.foley.com/insights/publications/2024/08/illinois-damages-biometric-privacy-law/ ·
https://www.dwt.com/blogs/privacy--security-law-blog/2024/08/illinois-bipa-biometrics-law-amended-for-damages ·
https://www.biometricupdate.com/202208/beyond-bipa-mitigating-biometric-data-legal-risks-under-texas-and-washington-biometrics-laws ·
https://www.recordinglaw.com/us-laws/data-privacy-laws/biometric-privacy-laws/ ·
https://artificialintelligenceact.eu/annex/3/ ·
https://www.bundesnetzagentur.de/EN/Areas/Digitalisation/AI/08_ProhibitedPractices/start.html ·
https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/

Tools/engineering: https://github.com/ORB-HD/deface ·
https://microsoft.github.io/presidio/image-redactor/ · https://github.com/microsoft/presidio ·
https://screenpipe.github.io/screenleak/ ·
https://aws.amazon.com/rekognition/pricing/ ·
https://aws.amazon.com/blogs/architecture/field-notes-redacting-personal-data-from-connected-cars-using-amazon-rekognition/ ·
https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-image-redaction ·
https://cloud.google.com/sensitive-data-protection/pricing ·
whisperX README (vendored, `_additional_context/whisperX/README.md`; pyannote diarization, gated model) ·
https://huggingface.co/pyannote/speaker-diarization-3.1

Deletion: https://en.wikipedia.org/wiki/Crypto-shredding ·
https://granit-fx.dev/blog/crypto-shredding-gdpr-erasure-without-deleting-rows/ ·
https://medium.com/etoai/you-can-now-delete-rows-in-lance-and-lancedb-8200d885d1cb ·
https://docs.lancedb.com/lance ·
https://docs.cloud.google.com/storage/docs/soft-delete ·
https://docs.cloud.google.com/storage/docs/bucket-lock ·
https://arxiv.org/pdf/2412.06966 · https://gdprlocal.com/gdpr-machine-learning/

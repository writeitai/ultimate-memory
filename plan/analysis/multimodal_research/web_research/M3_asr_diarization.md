# M3 — ASR + Speaker Diarization + Word‑Level Alignment for Video/Audio (2026)

**Question:** Best 2026 stack to turn a video's audio track into a *time‑anchored TEXT rendering* —
i.e. a transcript with **word‑level timecodes** and **speaker labels**. Compare Whisper / WhisperX /
faster‑whisper / NVIDIA Parakeet + Canary / pyannote / Gemini audio / commercial (Deepgram,
AssemblyAI) on accuracy (WER), speed/throughput, cost, self‑host vs API, multilingual incl. **Czech**.
Recommend a **self‑hostable‑first default** with an **API fallback**.

Date: 2026‑06‑25. Author: research subagent. Convention below: **[V]** = verified against a cited
primary/secondary source; **[I]** = inferred / derived / widely reported but not pinned to a single
authoritative number; **[?]** = could not verify, flagged.

---

## 1. Key findings (bullets)

- **There is no single model that does all three jobs well.** "ASR", "word‑level timestamps", and
  "speaker diarization" are three separate problems. The winning 2026 pattern is a **pipeline**:
  (a) ASR for the words, (b) forced alignment OR a native‑timestamp decoder for word timecodes,
  (c) a diarization model (pyannote family) for *who spoke*, then (d) assign speakers to words.
  **WhisperX** is the reference open implementation of exactly this pipeline. **[V]**

- **WhisperX is the strongest self‑hostable turnkey default** for "words + word‑timecodes + speaker
  labels in one tool." It runs a `faster‑whisper` (CTranslate2) Whisper backend for transcription,
  `wav2vec2` **forced phoneme alignment** for ±~50 ms word timestamps (vs Whisper's native ±~500 ms /
  several‑second utterance timestamps), and **pyannote** for diarization, then maps speakers onto
  words. ~70× real‑time with large‑v2 on a single GPU. It ships a **Czech alignment model by default**
  (`comodoro/wav2vec2-xls-r-300m-cs-250`, verified in the cloned repo `whisperx/alignment.py:47`). **[V]**

- **For accuracy/speed on the ASR step itself in 2026, NVIDIA's NeMo models beat Whisper‑large‑v3.**
  **Parakeet‑TDT‑0.6B‑v3** (600 M params, 25 European languages incl. Czech) gets ~6.34 % avg English
  WER at **~3,300× real‑time** and emits **native word‑level timestamps** (TDT decoder, no second
  alignment pass). **Canary‑1B‑v2** is the accuracy leader for multilingual incl. Czech
  (**Czech FLEURS WER ≈ 7.86 %**, vs Whisper‑large‑v3 ≈ 11.33 %, Parakeet‑v3 ≈ 11.01 %) and also does
  speech translation. Both are open weights (CC‑BY‑4.0) but **GPU/NeMo‑centric** and do **not** include
  diarization — pair with pyannote. **[V]**

- **Diarization is a pyannote monopoly for open self‑host.** `pyannote/speaker-diarization-community-1`
  (open) supersedes the old 3.1 pipeline with better speaker counting; **`precision-2`** is the
  premium pyannoteAI variant (~28 % more accurate than OSS 3.1, faster), available as API or
  self‑host license. WhisperX's current README already points at `speaker-diarization-community-1`.
  Diarization Error Rate (DER) for the open stack is roughly **8–19 %** depending on data/overlap. **[V]**

- **API fallback ranking:** **Deepgram Nova‑3** is the best price/throughput/coverage combo
  (~$0.0043/min batch ≈ $0.26/hr, word‑level timestamps + diarization, explicit Czech support);
  **AssemblyAI Universal‑2** has the best diarization quality and 99‑language coverage at ~$0.15/hr +
  $0.02/hr diarization. **Gemini 2.5 audio is excellent and cheap for *diarized segment‑level*
  transcripts but is NOT reliable for word‑level timecodes** — documented progressive timestamp drift
  (>10 min on hour‑long audio). Do **not** make Gemini the time‑anchor source. **[V]**

---

## 2. Evidence & detail (with citations)

### 2.1 The pipeline shape (why three components)

Vanilla Whisper transcribes accurately but its timestamps are **utterance/segment‑level and can be
off by several seconds**; it has no native word timestamps and no diarization. WhisperX adds the two
missing pieces. From the cloned WhisperX README (and DeepWiki):

- "Whisper … produces highly accurate transcriptions, [but] the corresponding timestamps are at the
  utterance‑level, not per word, and can be inaccurate by several seconds." **[V]** — repo
  `whisperX/README.md`; https://github.com/m-bain/whisperX
- WhisperX = `faster-whisper` backend + **wav2vec2 forced alignment** (word timestamps) + **VAD**
  preprocessing (reduces hallucination, enables batching with no WER degradation) + **pyannote**
  diarization with `assign_word_speakers()`. **[V]** — https://deepwiki.com/m-bain/whisperX
- Reported alignment precision **±~50 ms** (vs **±~500 ms** vanilla Whisper); ~70× real‑time on RTX
  4090; the write‑ups cite "WER < 5 % and DER ~8 %" on favorable data (treat as best‑case marketing,
  not a guarantee). **[I]** — https://johal.in/whisperx-transcription-diarization-and-alignment-for-audio-processing-2026/
- Diarization model used: the README's diarization setup now references
  `pyannote/speaker-diarization-community-1` (HF‑token gated). **[V]** — repo README.
- **Czech is supported in the alignment stage out of the box.** Verified in the cloned source:
  `DEFAULT_ALIGN_MODELS_HF["cs"] = "comodoro/wav2vec2-xls-r-300m-cs-250"`
  (`whisperX/whisperx/alignment.py:47`). The default torch alignment set also covers en/fr/de/es/it;
  the HF set adds ~35 languages incl. cs, sk, pl, ru, uk, etc. **[V]** — cloned repo.

### 2.2 ASR accuracy + throughput (the "words" step)

**Open ASR Leaderboard (English)** — the canonical reproducible benchmark (HF + paper
arXiv:2510.06961):
- Best accuracy is held by Conformer‑encoder + transformer/LLM‑decoder models (slow): e.g. *Granite
  Speech 4.1 2B* ~**5.33 %** mean WER; *Canary‑Qwen‑2.5B* ~**5.63 %**, but at only ~145–418 RTFx. **[V]**
- *Parakeet‑TDT‑0.6B‑v2/v3* sit ~top‑10 on accuracy (~6.0–6.34 % WER) but at **RTFx ≈ 3,300–3,390**
  (orders of magnitude faster). *Parakeet‑CTC‑1.1B* ≈ 6.68 % WER @ RTFx 2,793. **[V]** —
  https://huggingface.co/blog/open-asr-leaderboard ; https://the-decoder.com/open-asr-leaderboard-tests-more-than-60-speech-recognition-models-for-accuracy-and-speed/
- *Whisper‑large‑v3* ≈ **6.43 %** English WER @ **RTFx ≈ 68.6** (i.e. accurate but ~40–50× slower
  than Parakeet). **[V]** — same sources.

**Parakeet‑TDT‑0.6B‑v3** (released 2025‑08‑14):
- 600 M param FastConformer‑TDT; **6.34 % avg English WER**; **RTFx ≈ 3,332**; **25 European languages**
  incl. Czech with automatic language ID; native word‑level timestamps from the TDT decoder (no forced
  alignment needed). **[V]** — https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 ;
  https://www.together.ai/models/parakeet-tdt-0-6b-v3
- Multilingual quality: on a 24‑language eval ≈ **9.7 % avg WER**, edging Whisper‑large‑v3 (9.9 %);
  6‑language subset ≈ 5.3 %. **[V]** — arXiv:2509.14128 (Canary‑v2 & Parakeet‑v3 paper).
- "CTC/TDT models emit timestamps natively for every token, with no forced alignment needed." **[V]** —
  https://arxiv.org/abs/2509.14128 and community write‑ups.

**Canary‑1B‑v2** (FastConformer encoder + Transformer decoder, 25 EU langs, ASR + speech translation):
- Avg WER ≈ **8.1 %** across FLEURS/CoVoST/MLS (beats Whisper‑large‑v3 9.9 %); common‑language subset
  ≈ **5.2 %**. **[V]** — arXiv:2509.14128 ; https://huggingface.co/nvidia/canary-1b-v2
- Timestamps via **NeMo Forced Aligner (NFA)** + auxiliary CTC model → reliable **segment‑ and
  word‑level** timestamps (extra step, not free in the decoder). **[V]** — model card / paper.
- License CC‑BY‑4.0 (commercial‑friendly); NeMo/GPU required. **[V]**

**Czech specifically (FLEURS `cs`, WER, lower is better):** **[V]** — arXiv:2509.14128
| Model | Czech WER |
|---|---|
| Canary‑1B‑v2 | **7.86 %** |
| Parakeet‑TDT‑0.6B‑v3 | 11.01 % |
| Whisper‑large‑v3 | 11.33 % |

So for **Czech**, the open accuracy order is **Canary‑1B‑v2 > Parakeet‑v3 ≈ Whisper‑large‑v3**.
(Commercial Deepgram Nova‑3 also explicitly added Czech with up to ~27 % relative WER reduction, but
no public absolute Czech WER number was found — **[?]**.)

**faster‑whisper (the WhisperX backend):**
- CTranslate2 implementation, "up to **4× faster** than OpenAI PyTorch with less VRAM"; large‑v3 needs
  <8 GB for beam_size 5. **[V]** — https://github.com/SYSTRAN/faster-whisper ; repo README.
- Throughput (RTF, <1 = faster than real time): RTX 3090 large‑v3 **RTF ≈ 0.08 (≈12.5× RT)**; RTX 3060
  int8 **RTF ≈ 0.15**; RTX 4090 with batching **70–100× RT**; **large‑v3‑turbo** ~5× faster than v3 with
  small accuracy loss. **[V/I]** — https://gigagpu.com/whisper-large-v3-on-rtx-3090-benchmark/ ;
  https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2/discussions/3
- Cost anchor: a Whisper‑large‑v3 batch benchmark reported **~1 M audio‑hours for ~$5,110** on
  commodity/spot GPUs ≈ **$0.005/hr of audio** self‑hosted compute. **[V]** —
  https://blog.salad.com/whisper-large-v3/ (treat as throughput‑optimized lower bound, **[I]** for your setup).

### 2.3 Diarization (the "who spoke" step) — pyannote

- `pyannote/speaker-diarization-community-1` (open, HF‑gated): improved speaker counting & assignment
  vs the legacy `3.1` pipeline. **[V]** — https://www.pyannote.ai/blog/community-1 ;
  https://huggingface.co/pyannote/speaker-diarization-community-1
- `precision-2` (pyannoteAI premium; API or self‑host license): **~14 % more accurate than
  Precision‑1, ~28 % more accurate than OSS 3.1**, and faster (e.g. AMI ~1 h files: 14 s/h of audio,
  ~2.2× faster than community‑1). **[V]** — https://www.pyannote.ai/blog/precision-2
- DER on the open 3.1 pipeline ≈ **11–19 %** on standard benchmarks (data‑dependent; overlap and
  far‑field hurt most). **[I]** — https://brasstranscripts.com/blog/speaker-diarization-models-comparison
- pyannote is **CPU‑runnable but GPU‑accelerated**; it is the de‑facto open diarizer and is what
  WhisperX, NeMo examples, and most pipelines wrap. **[V]** — https://github.com/pyannote/pyannote-audio

### 2.4 Commercial / API options

**Deepgram Nova‑3** **[V]**
- WER: median **5.26 % batch / 6.84 % streaming** across a 2,703‑file, 9‑domain production set;
  marketed as 47.4 % (batch)/54.2 % (streaming) WER reduction vs competitors. **[V]** —
  https://deepgram.com/learn/introducing-nova-3-speech-to-text-api
- Word‑level timestamps: yes (per‑word timing + duration). Diarization: yes (small add‑on). **[V]** —
  https://developers.deepgram.com/docs/model
- Pricing: pre‑recorded **$0.0043/min ≈ $0.258/hr**, streaming **$0.0077/min ≈ $0.462/hr**; diarization
  ~ +$0.001–0.002/min. (Third‑party "$0.46/hr" figures usually bundle features/streaming — treat
  per‑minute API numbers as canonical.) **[V/I]** — https://deepgram.com/pricing ;
  https://brasstranscripts.com/blog/deepgram-pricing-per-minute-2025-real-time-vs-batch
- Czech: explicitly added to Nova‑3 multilingual (up to ~27 % relative WER reduction noted). **[V]** —
  https://deepgram.com/learn/deepgram-expands-nova-3-with-11-new-languages-across-europe-and-asia

**AssemblyAI Universal‑2** **[V]**
- 99 languages (diarization in 95); word‑level timestamps; diarization speaker‑count error ~2.9 %
  (64 % fewer speaker‑count errors on >2 min files vs prior). **[V]** —
  https://www.assemblyai.com/speaker-diarization
- Pricing: base **$0.15/hr** ($0.0025/min) + diarization **$0.02/hr**; combined ≈ **$0.17/hr**. **[V]** —
  https://www.assemblyai.com/pricing
- Strength: best‑in‑class diarization quality; weakness: pricier than Deepgram, English‑centric peak
  accuracy. **[I]**

**Gemini 2.5 (Flash / Pro) audio** **[V]**
- Capable of long‑form (up to ~9.5 h/prompt) multi‑speaker transcription **with diarization** and
  segment‑level timestamps; billed by tokens, **25 audio tokens/sec** → ~90,000 audio tokens/hr.
  Audio input **$1.00/1M tokens** (both Flash & Pro) → **~$0.09/hr audio input**; text output Flash
  $2.50/1M, Pro $10/1M → total roughly **$0.10–0.20/hr** depending on transcript length/model. **[V]** —
  https://ai.google.dev/gemini-api/docs/pricing ; https://ai.google.dev/gemini-api/docs/audio
- **Critical caveat — NOT a word‑timecode source:** documented **progressive timestamp drift**
  (>10 min off on hour‑long audio), random‑segment returns on "refer to timestamp" feature, and
  output‑token limits forcing chunked/looping strategies that degrade quality. Timestamps are
  "usable for navigation, not frame‑accurate." **[V]** —
  https://discuss.ai.google.dev/t/bug-gemini-3-flash-and-3-1-pro-progressive-timestamp-drift-in-audio-transcription/129501 ;
  https://github.com/google-gemini/cookbook/issues/733 ;
  https://towardsdatascience.com/building-a-scalable-and-accurate-audio-interview-transcription-pipeline-with-google-gemini/

### 2.5 Comparison summary table

| Option | Self‑host? | Word‑timecodes | Diarization | English WER | Czech | Throughput | Cost |
|---|---|---|---|---|---|---|---|
| **WhisperX** (faster‑whisper + wav2vec2 + pyannote) | **Yes** | **Yes** (forced align, ±~50 ms) | **Yes** (pyannote) | ~6.4 % (large‑v3) | ✅ align model built‑in; ~11.3 % WER | ~70× RT (RTX4090) | self GPU ~$0.005–0.05/hr **[I]** |
| faster‑whisper (alone) | Yes | weak (segment) | no | ~6.4 % | yes (no native word ts) | 12–100× RT | self GPU |
| Whisper large‑v3 (OpenAI orig) | Yes | weak (segment) | no | 6.43 % | 11.33 % | ~68× RTFx | self GPU |
| **Parakeet‑TDT‑0.6B‑v3** | Yes (NeMo) | **Yes (native TDT)** | **no** (add pyannote) | 6.34 % | 11.01 %; 25 EU langs | **~3,300× RTFx** | self GPU |
| **Canary‑1B‑v2** | Yes (NeMo) | Yes (NFA, extra pass) | no (add pyannote) | ~5.2–8.1 % multiling | **7.86 % (best open)** | fast (FastConformer) | self GPU |
| pyannote community‑1 / precision‑2 | Yes | n/a | **Yes** (DER ~8–19 %) | n/a | lang‑agnostic | 14–31 s/hr audio | open / premium license |
| **Deepgram Nova‑3** | No (API) | Yes | Yes (+small fee) | 5.26 % batch | ✅ supported | very fast API | **$0.0043/min ≈ $0.26/hr** |
| **AssemblyAI Universal‑2** | No (API) | Yes | **Yes (best)** | low (English‑strong) | among 99 langs | fast API | $0.15 + $0.02/hr |
| Gemini 2.5 Flash/Pro | No (API) | **❌ unreliable (drift)** | Yes (segment) | good | good | long‑context | ~$0.10–0.20/hr |

---

## 3. Confidence & gaps

- **High confidence [V]:** the pipeline architecture (ASR + alignment + diarization); WhisperX's
  components and built‑in Czech alignment model (read directly from cloned source); Parakeet‑v3 /
  Canary‑v2 / Whisper‑v3 relative English + Czech FLEURS WER (single primary paper arXiv:2509.14128);
  Open ASR Leaderboard rankings/RTFx; Deepgram & AssemblyAI list pricing and feature support; Gemini
  token pricing and the timestamp‑drift limitation.
- **Medium confidence [I]:** absolute throughput/cost numbers depend heavily on GPU, batch size,
  quantization, and audio characteristics — the "70× RT", "$0.005/hr", "DER 8 %" figures are
  best‑case/marketing or single‑benchmark and will vary 2–10× in practice. WhisperX's "<5 % WER /
  8 % DER" is a favorable‑data claim, not a guarantee.
- **Gaps [?]:** (1) No public **absolute** Czech WER for Deepgram Nova‑3 / AssemblyAI / Gemini — only
  relative improvement claims; would need an in‑house Czech eval set. (2) Diarization quality on
  *real video* (background music, overlap, far‑field mics) is materially worse than the clean‑benchmark
  DER numbers — measure on representative content. (3) Parakeet/Canary **native** word‑timestamp
  precision vs WhisperX wav2vec2 alignment was not head‑to‑head benchmarked in the sources; both are
  reported "good", WhisperX's ±50 ms is the most concrete claim. (4) License nuance: confirm
  pyannote model gating/terms and NVIDIA CC‑BY‑4.0 attribution requirements before shipping.

---

## 4. Recommendation for ugm

ugm needs the audio track rendered as a **time‑anchored TEXT layer**: a transcript whose **words carry
start/end timecodes** and whose **segments carry speaker labels**, so the text can be projected onto
the video timeline (this is the audio analogue of OCR‑with‑bbox for documents — the timecode is the
"where", the speaker label is a coarse "who"). That maps cleanly onto a layered/observation model:
each word is a time‑sliced observation with `(t_start, t_end, text, speaker_id, confidence)`.

**Self‑hostable‑first DEFAULT — WhisperX pipeline.**
Use **WhisperX** as the integration pipeline because it is the one open tool that emits *exactly* the
required shape (word‑timecodes + speaker labels) in a single run, is GPU‑cheap, and already ships a
Czech alignment model:
1. **ASR + word alignment + diarization in one pass** via WhisperX:
   - ASR backend = `faster-whisper large-v3` (accuracy) or `large-v3-turbo` (≈5× faster, small WER cost)
     — choose per throughput budget.
   - Forced alignment = wav2vec2 (built‑in per‑language; **Czech uses
     `comodoro/wav2vec2-xls-r-300m-cs-250` automatically**).
   - Diarization = `pyannote/speaker-diarization-community-1`; upgrade to **pyannote precision‑2**
     (self‑host license) only if DER on real video proves too high.
2. **Accuracy/Czech upgrade path (still self‑hosted):** keep WhisperX's alignment+diarization wiring
   but **swap the ASR stage** to NVIDIA NeMo when content is Czech‑heavy or accuracy‑critical:
   - **Canary‑1B‑v2** for best Czech/multilingual WER (7.86 % Czech) and optional speech‑translation
     (handy if ugm later wants a normalized‑to‑English text projection alongside the source language).
   - **Parakeet‑TDT‑0.6B‑v3** when throughput dominates (~3,300× RT, native word timestamps — you can
     even skip the wav2vec2 alignment pass and feed TDT word timestamps straight into the speaker‑assign
     step). Then diarize with pyannote and run WhisperX's `assign_word_speakers()`‑style merge.
   This keeps a **single, stable output contract** (word + timecode + speaker) regardless of which ASR
   engine produced the words — important for the projection contract; the ASR model becomes a swappable
   backend, not an architectural commitment.

**API FALLBACK — Deepgram Nova‑3 (primary fallback), AssemblyAI Universal‑2 (diarization‑critical).**
When there is no GPU, for burst load, or for languages outside the self‑host stack's strength:
- **Deepgram Nova‑3** is the default API: word‑level timestamps **and** diarization in one call,
  ~$0.0043/min batch, explicit Czech support, very high throughput. Lowest operational friction and
  cost for the exact output ugm needs.
- **AssemblyAI Universal‑2** when speaker separation quality is the priority (best diarization,
  99 languages) and the higher price is acceptable.

**Do NOT use Gemini 2.5 as the time‑anchor source.** Its word/segment timestamps drift badly on
long‑form audio. It is, however, a good *cheap auxiliary*: a diarized, speaker‑attributed
*segment‑level* transcript for search/summarization, or a cleanup/punctuation/translation pass over an
already time‑anchored WhisperX transcript — never the producer of the timecodes themselves.

**Net:** default = **WhisperX (faster‑whisper large‑v3 + wav2vec2 align + pyannote community‑1)**, with a
**NeMo Canary/Parakeet ASR swap** for Czech/accuracy or speed, and **Deepgram Nova‑3** as the no‑GPU
API fallback — all emitting the same `{word, t_start, t_end, speaker, conf}` contract that the
time‑anchored text layer consumes.

---

### Sources
- https://github.com/m-bain/whisperX · https://deepwiki.com/m-bain/whisperX
- (cloned) `whisperX/whisperx/alignment.py` (Czech align model `cs` confirmed) · `whisperX/README.md`
- https://johal.in/whisperx-transcription-diarization-and-alignment-for-audio-processing-2026/
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 · https://www.together.ai/models/parakeet-tdt-0-6b-v3
- https://huggingface.co/nvidia/canary-1b-v2 · https://arxiv.org/abs/2509.14128 (Canary‑v2 & Parakeet‑v3)
- https://arxiv.org/abs/2510.06961 (Open ASR Leaderboard) · https://huggingface.co/blog/open-asr-leaderboard
- https://the-decoder.com/open-asr-leaderboard-tests-more-than-60-speech-recognition-models-for-accuracy-and-speed/
- https://github.com/SYSTRAN/faster-whisper · https://gigagpu.com/whisper-large-v3-on-rtx-3090-benchmark/
- https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2/discussions/3 · https://blog.salad.com/whisper-large-v3/
- https://www.pyannote.ai/blog/community-1 · https://www.pyannote.ai/blog/precision-2 · https://github.com/pyannote/pyannote-audio
- https://deepgram.com/pricing · https://deepgram.com/learn/introducing-nova-3-speech-to-text-api · https://developers.deepgram.com/docs/model
- https://deepgram.com/learn/deepgram-expands-nova-3-with-11-new-languages-across-europe-and-asia
- https://www.assemblyai.com/pricing · https://www.assemblyai.com/speaker-diarization
- https://ai.google.dev/gemini-api/docs/pricing · https://ai.google.dev/gemini-api/docs/audio
- https://discuss.ai.google.dev/t/bug-gemini-3-flash-and-3-1-pro-progressive-timestamp-drift-in-audio-transcription/129501
- https://github.com/google-gemini/cookbook/issues/733

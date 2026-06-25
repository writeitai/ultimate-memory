# WhisperX — code archaeology (for ugm multimodal)

Repo: `m-bain/whisperX`, vendored at
`/Users/jpuc/code/moje/ultimate_memory/ugm_3/ugm/_additional_context/whisperx/`
Version `3.8.6`, `requires-python = ">=3.10, <3.14"` (`pyproject.toml:5,8`).

What it is (from `README.md`): fast ASR (faster-whisper backend) + **forced phoneme alignment**
(wav2vec2) for word-level timestamps + optional **speaker diarization** (pyannote). Claimed "70x
realtime with large-v2", "<8GB gpu memory for large-v2 with beam_size=5". Output of interest for
ugm: a transcript object where every word carries `start`/`end` seconds and an optional `speaker`
label — i.e. a text rendering with time locators back into the audio timeline.

---

## 1. Core pipeline / stages

Orchestrated in `whisperx/transcribe.py:transcribe_task()`. Four stages, run **sequentially**, with
each model **loaded then freed** before the next (this is the cost/stage ordering — see §5):

1. **VAD + ASR (transcribe).** `whisperx/asr.py`. `load_model()` builds a `FasterWhisperPipeline`.
   `FasterWhisperPipeline.transcribe()` (`asr.py:197`):
   - Runs Voice Activity Detection first (`vad_model(...)`, default **pyannote** VAD; `silero`
     selectable), then `merge_chunks()` packs VAD speech regions into ≤`chunk_size` (default 30s)
     windows (`whisperx/vads/vad.py:19-53`).
   - Batches those windows through faster-whisper (`generate_segment_batched`, `asr.py:37`). Note:
     **batched mode runs `without_timestamps=True`** (`asr.py:388` in default options) — Whisper's
     own word timestamps are OFF; timing comes only from the VAD chunk bounds at this stage, refined
     later by alignment.
   - Returns `TranscriptionResult = {"segments": [...], "language": str}`. Each segment here is just
     `{text, start, end, avg_logprob}` where start/end are the VAD chunk bounds, `round(...,3)`
     (`asr.py:281-288`).
   - `transcribe_task` frees the model immediately: `del model; gc.collect(); torch.cuda.empty_cache()`
     (`transcribe.py:161-163`).

2. **Forced alignment.** `whisperx/alignment.py`. `load_align_model()` + `align()`.
   - Per segment: slices the audio `[t1,t2]`, runs a wav2vec2 CTC model, builds a **trellis**
     (`get_trellis`, `alignment.py:425`) and **backtracks** the best path
     (`backtrack`, `alignment.py:455`) — classic Viterbi forced alignment from the torchaudio tutorial
     (cited `alignment.py:421`). `merge_repeats` collapses frames to per-character spans.
   - Character frame indices → seconds via
     `ratio = duration * waveform_segment.size(0) / (trellis.size(0) - 1)`, then
     `start = round(char_seg.start * ratio + t1, 3)` (`alignment.py:295-307`). So **word/char times are
     real seconds on the original audio timeline**, not frame indices.
   - Re-segments into sentences using **NLTK Punkt** `span_tokenize` (`alignment.py:196`), language-aware
     (`PUNKT_LANGUAGES`, `utils.py:130`). Words with no alignable characters get times via
     `interpolate_nans` (default method `"nearest"`; `utils.py:470`).
   - Output upgraded to `AlignedTranscriptionResult` (see §2).
   - Model freed again (`transcribe.py:204-206`).

3. **Diarization.** `whisperx/diarize.py:DiarizationPipeline` wraps pyannote
   `Pipeline.from_pretrained(...)`. Default model `pyannote/speaker-diarization-community-1`
   (`diarize.py:101`, `__main__.py:48`). Returns a pandas DataFrame of
   `{segment, label, speaker, start, end}` (`diarize.py:170-172`), optionally `speaker_embeddings`.

4. **Speaker assignment.** `diarize.py:assign_word_speakers()` overlays diarization onto the transcript.
   Builds an `IntervalTree` (sorted-array + binary search, `diarize.py:14`) for overlap queries; for each
   segment **and each word**, picks the speaker with the **max summed intersection duration**
   (`diarize.py:224-257`). `fill_nearest` falls back to nearest segment midpoint when there is no overlap.
   Claimed "~228x speedup for long-form content (3+ hour podcasts)" vs linear scan (`diarize.py:18-20,194`).

5. **Write.** `whisperx/utils.py:get_writer()` → txt/vtt/srt/tsv/json/aud (default `all`).

---

## 2. OUTPUT DATA SCHEMA (the load-bearing part for ugm)

Canonical TypedDicts in `whisperx/schema.py`:

```python
class SingleWordSegment(TypedDict):      # schema.py:11
    word: str
    start: float
    end: float
    score: float

class SingleCharSegment(TypedDict):      # schema.py:20
    char: str
    start: float
    end: float
    score: float

class SingleSegment(TypedDict):          # schema.py:30  (pre-alignment)
    start: float
    end: float
    text: str
    avg_logprob: NotRequired[float]

class SingleAlignedSegment(TypedDict):   # schema.py:52  (post-alignment)
    start: float
    end: float
    text: str
    avg_logprob: NotRequired[float]
    words: List[SingleWordSegment]
    chars: Optional[List[SingleCharSegment]]

class TranscriptionResult(TypedDict):    # schema.py:65
    segments: List[SingleSegment]
    language: str

class AlignedTranscriptionResult(TypedDict):  # schema.py:73
    segments: List[SingleAlignedSegment]
    word_segments: List[SingleWordSegment]    # flat list of every word, schema.py:414-418
```

**The locator model.** The only back-reference to the source is a pair of `float` **seconds**
(`start`, `end`) on the audio timeline, present at three granularities: segment, word, and (optional)
char. There are **no byte/char offsets into a text document and no bounding boxes** — this is audio, so
the locator is purely temporal. `score` is the wav2vec2 alignment confidence (mean char CTC prob;
`alignment.py:351`). Times are rounded to **3 decimal places (~ms)** in transcribe and align.

**`speaker` is injected dynamically and is NOT in the TypedDict.** `assign_word_speakers` mutates dicts
in place: `seg['speaker'] = ...` and `word['speaker'] = ...` (`diarize.py:229,252`). When
`return_embeddings`, a `speaker_embeddings` key (dict: speaker → vector) is bolted onto the result
(`diarize.py:261`). So the real runtime JSON object is richer than the declared schema — an
implementer must treat `speaker` / `speaker_embeddings` as optional, schema-less extensions.

**Rendered-output locators.** The subtitle writers (`utils.py:248-391`) derive cue times from
word-level timestamps (`min(word starts)`, `max(word ends)`, `utils.py:314-318`), prefix speaker as
`[SPEAKER_XX]: ` (`utils.py:330`), and `--highlight_words` emits one cue per word wrapping the active
word in `<u>...</u>` (`utils.py:343-350`). TSV writes integer-millisecond start/end
(`round(1000*start)`, `utils.py:409`). JSON is a raw `json.dump(result)` (`utils.py:439`) — the full
nested object above, verbatim.

---

## 3. Key parameters / thresholds / model names

ASR defaults (`asr.py:371-399`, overridable via CLI `__main__.py`):
- `--model` default **`small`** (`__main__.py:16`); README examples use `large-v2`.
- `beam_size=5`, `best_of=5`, `patience=1`, `length_penalty=1`.
- temperature fallback ladder `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]`.
- `compression_ratio_threshold=2.4`, `log_prob_threshold=-1.0`, `no_speech_threshold=0.6`.
- `condition_on_previous_text=False` (hard-set), `without_timestamps=True`, `word_timestamps=False`.
- `--batch_size` default **8** (`__main__.py:21`); README Python example uses 16.
- `compute_type` default → `float16` on cuda, `float32` on cpu (`asr.py:350-351`).
- VAD: `vad_method="pyannote"`, `vad_onset=0.500`, `vad_offset=0.363`, `chunk_size=30`
  (`asr.py:409-413`, `__main__.py:39-42`).

Alignment models (`alignment.py:32-77`):
- `DEFAULT_ALIGN_MODELS_TORCH`: `en→WAV2VEC2_ASR_BASE_960H`, fr/de/es/it → `VOXPOPULI_ASR_BASE_10K_*`.
- `DEFAULT_ALIGN_MODELS_HF`: ~35 languages mapped to HF wav2vec2 checkpoints (ja, zh, nl, ru, pl, ...).
- `LANGUAGES_WITHOUT_SPACES = ["ja","zh"]` get char-by-char word splitting (`alignment.py:30,320`).
- Unknown chars (digits/symbols/foreign script) handled with a **wildcard emission column**
  (`alignment.py:273-281`) rather than being dropped.

Diarization: default model `pyannote/speaker-diarization-community-1`; `--min_speakers`/`--max_speakers`/
`num_speakers` optional hints (`diarize.py:105-113`). Requires a HuggingFace token for the gated model.

Audio constants (`audio.py:13-22`): `SAMPLE_RATE=16000`, `N_FFT=400`, `HOP_LENGTH=160`,
`CHUNK_LENGTH=30`, `N_SAMPLES=480000`, 10ms/frame, 20ms/token.

---

## 4. Notable correctness details (read from code, not docs)

- Segment alignment can **fail gracefully**: empty dictionary chars, `t1 >= MAX_DURATION`, or failed
  backtrack → segment kept with original text but **no word timings** (`alignment.py:230-238,288-291`).
  Downstream consumers must tolerate words-less / timing-less segments.
- wav2vec2 requires ≥400 samples; short slices are zero-padded (`alignment.py:248-252`).
- Words may have `word` but be missing `start`/`end`/`score` keys entirely (added only `if not nan`,
  `alignment.py:356-361`). Speaker assignment explicitly skips words with no `start` (`diarize.py:240`).

## 5. Performance / cost characteristics & STAGE ORDERING

- Cost is dominated by stage order and **never co-resident models**: VAD+ASR run and the whisper model
  is deleted/`empty_cache`d before the align model loads, which is itself deleted before pyannote loads
  (`transcribe.py:161-163, 204-206, 218`). This is a deliberate memory-vs-latency tradeoff: peak VRAM =
  the single largest stage, at the cost of reloading.
- Ordering rationale: **ASR is cheapest per second via VAD batching** (skips silence, batches 30s
  windows); **alignment is per-segment** wav2vec2 (one forward pass per VAD segment, `# TODO batched`
  at `alignment.py:245`); **diarization is a separate full-audio pyannote pass** and is opt-in
  (`--diarize`). Speaker assignment is the only O(N·log M) join, made cheap by the interval tree.
- Headline numbers (README): 70x realtime (large-v2), <8GB VRAM at beam_size=5. The 228x figure is for
  the speaker-assignment join, not the whole pipeline (`diarize.py:18`).

---

## 6. Steal vs avoid for ugm

ugm = text-centric memory needing **versioned conversion** + **grounded locators**.

STEAL:
- **Three-granularity time locators (segment / word / char) as plain `(start,end)` floats on a single
  source timeline.** Clean, serializable, and exactly the "grounded locator" shape ugm wants — for
  audio/video the locator is a timecode, the analog of a char-offset span in text. The flat
  `word_segments` list alongside nested `segments` (`schema.py:78`) is a good dual index: render order
  vs. random-access-by-word.
- **Stage isolation with explicit teardown** (load→use→free per stage). Maps directly to ugm's
  cost-ordered worker path: cheap+lossy pass first, expensive refinement only where needed.
- **Graceful-degradation contract**: if refinement (alignment) fails, keep the coarse locator (VAD
  segment bounds) rather than dropping content. ugm should likewise always retain a coarse grounded
  span when fine grounding fails.
- **Interval-tree overlay join** to attach a second annotation layer (speakers) onto an existing
  spanned transcript without re-deriving it — a clean pattern for layering ugm annotations onto a base
  conversion.
- **Deterministic, machine-parseable rendering** (TSV integer-ms, raw JSON dump) separate from
  human-pretty rendering (SRT/VTT) — ugm's "multiple renderings of one conversion" idea, already split.

AVOID / GAPS for ugm:
- **No versioning of the conversion.** The output has no model id, no params hash, no schema version.
  Re-running with a different whisper/align/diarize model or different `vad_onset` silently produces
  different timings/text with no provenance. ugm's "versioned conversion" requirement is exactly this
  missing piece — ugm must stamp (source hash, model+params, schema version) onto every conversion.
- **`speaker` / `speaker_embeddings` are schema-less mutations** bolted onto dicts at runtime
  (`diarize.py:229,261`), diverging from the declared TypedDicts. Avoid this for ugm: annotation layers
  should be typed, additive, and not mutate the base object in place.
- **Locators are not stable identity.** Times are derived floats (rounded ms, interpolated for
  unalignable words); they are an artifact of the model pass, not a canonical address. ugm should not
  treat a raw timecode as a durable key — pin locators to a versioned conversion so a re-conversion
  doesn't invalidate references.
- **Lossy/heuristic boundaries baked in**: NLTK sentence re-segmentation and VAD chunking decide
  segment boundaries; `condition_on_previous_text=False` trades cross-window coherence for robustness.
  Fine for subtitles, but ugm should keep the *finest* grounded unit (word/char span) authoritative and
  treat sentence/segment grouping as a derived, replaceable view.
- **No back-reference into any source text document** — grounding is audio-time only (expected: there is
  no source text). For ugm video "text rendering", the timecode IS the locator; there are no
  bounding boxes here (would need an OCR/vision pipeline, not found in this repo).

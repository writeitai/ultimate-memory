# PySceneDetect — code archaeology

Source read: `/Users/jpuc/code/moje/ultimate_memory/ugm_3/ugm/_additional_context/pyscenedetect/`
Version: `__version__ = "0.7.1-dev0"` (`scenedetect/__init__.py:78`); README says "Latest Release: v0.7 (May 3, 2026)". License BSD-3-Clause.

What it is: a deterministic, CPU/OpenCV-based **shot/cut detector** for video. It scans frames, computes a cheap per-frame change score, and emits a list of `(start, end)` timecode pairs ("scene list"). Tagline in README: "Video Cut Detection and Analysis Tool". One neural detector exists (TransNetV2, ONNX) but the default and the cheap path are pure pixel-math detectors.

---

## 1. Core pipeline / stages

Entry points:
- High-level: `detect(video_path, detector, ...) -> SceneList` (`scenedetect/__init__.py:144-201`). Opens video, optionally seeks `start_time`, runs one detector, returns scene list.
- Programmatic: `open_video()` → `SceneManager()` → `add_detector()` → `detect_scenes(video)` → `get_scene_list()` (`scenedetect/scene_manager.py`, docstring lines 27-35).

`SceneManager.detect_scenes` (`scene_manager.py:446-610`) is the engine:
1. **Decode in a background thread** (`_decode_thread`, `scene_manager.py:612-697`). README/docstring: "Video decoding is done in a separate thread to improve performance." Bounded queue `MAX_FRAME_QUEUE_LENGTH = 4` (`:113`).
2. **Auto-downscale** before detection: `compute_downscale_factor(frame_width, effective_width=DEFAULT_MIN_WIDTH=256)` (`:110`, `:123-140`). Frames are resized so effective width is between 256 and ~384 px; this is the main cheap-ness lever ("This value can and should be tuned for performance...", `:107`). Downscale + optional crop happen in the decode thread (`:653-665`). Interpolation default `Interpolation.LINEAR` (`:256`).
3. **Per-frame detection**: each decoded `(frame_im, position)` goes to every registered detector's `process_frame(timecode, frame_img)` which returns a list of cut `FrameTimecode`s appended to `_cutting_list` (`_process_frame`, `:410-435`).
4. **post_process** at end (`:437-441`) for detectors that emit trailing cuts (Threshold fade-out, TransNetV2 flush).
5. **Cuts → scenes**: `get_scene_list()` (`:376-401`) calls `get_scenes_from_cuts(cut_list, start_pos, last_pos+1)` (`:171-210`). Scenes are **contiguous**: scene[i] = (cut[i-1], cut[i]); first starts at `start_pos`, last ends at `last_pos+1`. If no cuts and `start_in_scene=False`, returns `[]`; if `start_in_scene=True`, one scene spanning the whole video.
- `frame_skip: int = 0` arg processes 1-in-(N+1) frames for speed at accuracy cost; **must be 0 if a StatsManager is used** (`:471-474`, `:498-499`).
- Optional `callback(frame_img, frame_num)` fired on the first frame of each new scene.

Detectors are stateless-per-run objects implementing `SceneDetector` (`scenedetect/detector.py:37-103`): required `process_frame() -> list[FrameTimecode]`, optional `post_process()`, `event_buffer_length` (lookahead in frames), `get_metrics()`.

---

## 2. The detectors (the "cheap deterministic segmentation")

All five non-NN detectors are O(pixels/frame), single forward pass, no model, deterministic. Frames arrive as **24-bit BGR** numpy arrays.

### ContentDetector — `detectors/content_detector.py` (default fast-cut detector)
- Converts frame to **HSV**, computes mean absolute per-pixel delta vs previous frame on hue, sat, luma channels (`_mean_pixel_distance`, `:29-36`), optionally an edge-difference channel (Canny + dilate, `_detect_edges` `:213-239`).
- Frame score = weighted sum / sum(|weights|) (`:177-180`). Cut when `score >= threshold`.
- Params (`__init__` `:104-142`):
  - `threshold: float = 27.0` (the `content_val` cutoff; lower = more sensitive, range 0–255)
  - `min_scene_len = 15` (frames; CLI default is `0.6s`, see §5)
  - `weights = Components(delta_hue=1.0, delta_sat=1.0, delta_lum=1.0, delta_edges=0.0)` (`:58-73`)
  - `luma_only=False` → `LUMA_ONLY_WEIGHTS = (0,0,1,0)` (`:77-83`)
  - `kernel_size=None` → auto from resolution: `4 + round(sqrt(w*h)/192)`, forced odd (`_estimated_kernel_size`, `:39-46`)
  - `filter_mode = FlashFilter.Mode.MERGE`
- Edges only computed if `delta_edges > 0` or a StatsManager is attached (perf optimization, `:158`).
- Stats keys: `content_val`, `delta_hue`, `delta_sat`, `delta_lum`, `delta_edges` (`:85-89`).

### AdaptiveDetector — `detectors/adaptive_detector.py` (subclass of ContentDetector; two-pass, rolling average)
- Reuses ContentDetector's per-frame `content_val`, then divides each frame's score by the average of a window of neighbors → `adaptive_ratio`; cut when ratio ≥ threshold AND raw score ≥ floor.
- Params (`:37-46`): `adaptive_threshold = 3.0`, `min_scene_len = 15`, `window_width = 2` (frames before+after), `min_content_val = 15.0`, plus inherited weights/luma/kernel.
- Internally calls super with `threshold=255.0, min_scene_len=0` and does its own buffering/min-length logic (`:71-77`, `:136-143`). `event_buffer_length = window_width` (needs lookahead). Best F1 + best precision in the benchmark (§4); README calls it the one that "handles fast camera movement better."

### ThresholdDetector — `detectors/threshold_detector.py` (fade in/out, NOT cuts)
- Tracks **average pixel intensity** (`numpy.mean(frame_img)`, `:127`) and detects crossing a fixed brightness level → fade-out then fade-in => one cut at a bias-interpolated frame.
- Params (`:48-56`): `threshold = 12` (8-bit intensity, fade-to-black), `min_scene_len = 15`, `fade_bias = 0.0` (−1..+1 skews cut between fade-out and fade-in), `add_final_scene = False`, `method = Method.FLOOR` (`FLOOR`=fade below, `CEILING`=fade above). `block_size` is deprecated/removed-in-v0.8.
- Cut frame computed by integer frame arithmetic to stay backend-identical (`:152-157`). Stat key `average_rgb`. Benchmark: essentially useless for hard cuts (F1 ~0.1) — it is a fade detector.

### HashDetector — `detectors/hash_detector.py` (perceptual hash / pHash)
- Grayscale → resize to `size*lowpass` square → `cv2.dct` → keep low-freq `size×size` block → binarize on median → **Hamming distance** between consecutive frame hashes, normalized by `size*size` (`hash_frame` `:119-151`).
- Params (`:47-53`): `threshold = 0.395` (relative Hamming distance 0–1; 0=identical, 1=uncorrelated; smaller=more sensitive), `size = 16`, `lowpass = 2`, `min_scene_len = 15`. Stat key `hash_dist [size=16 lowpass=2]`. Fastest detector in benchmark (§4). Based on imagehash / hackerfactor pHash.

### HistogramDetector — `detectors/histogram_detector.py` (`detect-hist`)
- Converts BGR→YUV, histogram of **Y (luma)** channel, normalized, compared with `cv2.compareHist(..., HISTCMP_CORREL)`; cut when correlation drops below `1 - threshold` (`:52`, `:90-112`).
- Params (`:33-38`): `threshold = 0.05` (max relative diff 0–1), `bins = 256`, `min_scene_len = 15`. Stat key `hist_diff [bins=256]`. Best fade recall in benchmark (75 F1 on ClipShots fades).

### TransNetV2Detector — `detectors/transnet_v2.py` (the ONE neural detector; NOT cheap/deterministic-pixel)
- ONNX model run via `onnxruntime` (`Predictor`, `:49-67`). `model_path = "tests/resources/transnetv2.onnx"`, `threshold = 0.5`, `min_scene_len = 15`, `onnx_providers=None` (auto-detect). Input tensor shape `(2, 100, 27, 48, 3)` uint8 — each frame resized to **48×27** (`cv2.resize(frame_img,(48,27))`, `:171`); runs on sliding windows of 100 frames, uses prediction rows `[25:75]`. Optional dependency. Not part of the cheap path.

### FlashFilter — shared min-scene-length enforcement (`detector.py:106-225`)
Used by Content/TransNetV2. Two modes: `MERGE` (combine consecutive sub-min-length cuts) and `SUPPRESS` (no new cut until min length passes). Accepts min length as int frames, float seconds, or string (`"0.6s"`, `"00:00:00.600"`). Reusable idea (see §6).

---

## 3. OUTPUT DATA SCHEMA — what a "scene list" actually contains

This is the part most relevant to ugm (locators back to the source).

**`SceneList`** = `list[tuple[FrameTimecode, FrameTimecode]]` (`common.py:90`). Each tuple is `(start, end)`. Scenes are contiguous and cover the analyzed span. There are **no bounding boxes, no labels, no text** — only temporal spans. (`CutList = list[FrameTimecode]`, `common.py:82`; `CropRegion = tuple[int,int,int,int]` is an *input* crop, not output.)

**`FrameTimecode`** (`common.py:191-...`) is the locator object. It is a frame-number/seconds/PTS triple bound to a frame rate. Key accessors:
- `.frame_num: int` — frame index (for VFR, an approximation from average fps; `:262-274`).
- `.seconds: float` — exact seconds (`:371-380`).
- `.pts: int` + `.time_base: Fraction` — **exact presentation timestamp** (preferred for precise/VFR timing; `:301-315`). For CFR, `time_base == 1/frame_rate`.
- `.frame_rate: Fraction` (canonical, exact, e.g. `Fraction(24000,1001)`) and `.framerate: float` (deprecated alias).
- `.get_timecode(precision=3) -> "HH:MM:SS.nnn"` string (`:407-450`).
- NTSC rates auto-detected to exact rationals (23.976→24000/1001, etc.; `framerate_to_fraction` `:126-145`).

These timecodes are grounded to the **source presentation time**: per `VideoStream.position` docstring (`video_stream.py:146-151`) "This can be interpreted as presentation time stamp, thus frame 1 corresponds to the presentation time 0." `base_timecode` is `FrameTimecode(0, fps)` (`:86-89`). So a scene's `start`/`end` map directly back to a byte/frame offset in the original file via frame number or PTS.

**CSV export** (`output/write_scene_list`, `output/__init__.py:57-118`) — the canonical flat schema. Header row:
```
Scene Number, Start Frame, Start Timecode, Start Time (seconds),
End Frame, End Timecode, End Time (seconds),
Length (frames), Length (timecode), Length (seconds)
```
Note off-by-one conventions: Start Frame is written as `start.frame_num + 1` (1-based), End Frame as `end.frame_num` (`:106-117`). An optional pre-header "Timecode List:" row carries the raw cut points.

**Other exporters** (all in `output/__init__.py`), each mapping scenes back to the source media path:
- `write_scene_list_html` (`:121`) — HTML table, optionally embeds keyframe images per scene.
- `write_scene_list_edl` (`:281`) — CMX 3600 EDL, `HH:MM:SS:FF` SMPTE, optional `start_timecode` offset.
- `write_scene_list_fcpx` (`:336`) — FCPXML 1.9, rational seconds, `<asset><media-rep src="file://...">`, one `<asset-clip name="Shot N" offset/start/duration>` per scene.
- `write_scene_list_fcp7` (`:435`) — FCP7 xmeml, `<clipitem>` per shot with `start/end/in/out` and a reused `<file pathurl="file://...">`.
- `write_scene_list_otio` (`:555`) — OpenTimelineIO JSON; each scene is a `Clip.2` with `source_range` (RationalTime start/duration) and `ExternalReference` `target_url` = absolute video path.
- QP file (`_cli/commands.py:80-101`) — encoder keyframe hints: lines `"{cut.frame_num - offset} I -1"`.

**Per-frame stats** (optional, `StatsManager.save_to_csv`, `stats_manager.py:164`): a CSV of every frame's metric values (e.g. `content_val`, `hash_dist`, `hist_diff`) keyed by timecode — useful for threshold tuning, not part of the scene list.

**Keyframe extraction** (`output/image.py`): `save_images(scene_list, video, num_images=3, frame_margin=1, ...)`. `_generate_timecode_list` (`:38-72`) picks N timecodes per scene: for `num_images=1` → scene midpoint; else first frame (+margin), last frame (−margin), and evenly spaced middles. So "keyframes" are deterministically sampled positions within each shot, not salient-frame detection.

---

## 4. Performance / cost characteristics (from `benchmark/README.md`, real numbers)

Scoring = TRECVID-SBD (greedy 1-to-1 NN matching, tolerance=0 strict frame-exact). "Mean s/video" = wall-clock seconds per video.

BBC Planet Earth (11 long broadcast clips, hard cuts):
| Detector | Recall | Precision | F1 | Mean s/video |
|---|---|---|---|---|
| Adaptive | 87.12 | 96.55 | **91.59** | 36.12 |
| Content | 84.70 | 88.77 | 86.69 | 37.02 |
| Hash | 92.30 | 75.56 | 83.10 | **25.51** |
| Histogram | 89.84 | 72.03 | 79.96 | 22.29 |
| Threshold | 0.06 | 0.70 | 0.11 | 16.05 |

AutoShot (short web clips): Adaptive F1 73.86 @3.52s; Content 69.26 @4.80s; Hash 64.84 @4.14s; Histogram 57.82 @3.76s.
ClipShots hard cuts: Adaptive 55.75, Content 55.84, Hash 43.98, Histogram 19.80; s/video 0.7–2.5.
ClipShots **fades**: Histogram wins (F1 75.33), Content 41.14, Threshold 10.77 — confirms Threshold/Histogram are the fade tools, Content/Adaptive the hard-cut tools.

Takeaways: Adaptive = best accuracy, Hash/Histogram = ~30–40% faster (cheapest), Threshold ≈ useless for cuts. Cost scales with frame count × pixels-after-downscale; downscale-to-256px-width + background decode thread are the speed levers. No GPU needed for any of the five pixel detectors; only TransNetV2 uses ONNX. Numbers are explicitly labeled tunable starting points in code comments.

---

## 5. Key params / thresholds / defaults summary

Library defaults (`min_scene_len = 15` frames in every detector ctor) vs **CLI/config defaults** (`_cli/config.py`):
- Global `min-scene-len = "0.6s"` (`:420`), `default-detector = "detect-adaptive"` (`:414`), `downscale = 0` (=auto), `frame-skip = 0`.
- `detect-adaptive`: `threshold = 3.0` (`:368`), range 0–255.
- `detect-content`: `threshold = 27.0` (`:376`).
- `detect-hash`: `threshold = 0.395` (`:383`).
- `detect-hist`: `threshold = 0.05`, bins 256 (`:387`).
- `detect-threshold`: `threshold = 12.0` (`:394`).
- Auto-downscale target width `DEFAULT_MIN_WIDTH = 256` (`scene_manager.py:110`).
Backends: OpenCV (default), PyAV, MoviePy (`scenedetect/backends/`). Splitting needs external `ffmpeg`/`mkvmerge`.

---

## 6. Steal vs avoid for ugm (text-centric memory; versioned conversion + grounded locators)

**Steal (concepts/patterns):**
- **The locator model is exactly the abstraction ugm wants for media.** A `FrameTimecode` carries *three* coordinated representations of one position — exact `pts`+`time_base` (Fraction, lossless), approximate `frame_num`, and human `HH:MM:SS.nnn` — and always references source presentation time (frame 1 = PTS 0). This is the multimodal analog of a grounded text offset: store the exact rational PTS as the canonical locator and derive display forms. Mirror the "prefer pts/time_base, frame_num is approximate for VFR" discipline (`common.py:262-315`).
- **Contiguous-segments-from-cut-points** (`get_scenes_from_cuts`, `scene_manager.py:171-210`): a video is fully partitioned into non-overlapping `(start,end)` spans covering the whole source — a clean, lossless segmentation contract that ugm can reuse for any timeline medium (audio/video) before sending segments to a model.
- **Cheap deterministic pre-segmentation before any model call** — the whole point. Pixel-math detectors (Hash/Histogram at ~22–26s for long clips, sub-second for short) cut a video into shots with zero model cost; ugm can run this as the "convert/segment" stage and only invoke an LLM/VLM per shot (or per sampled keyframe), massively cutting model spend. Deterministic = same input → same segments → reproducible/versionable.
- **Deterministic keyframe sampling** (`_generate_timecode_list`, `output/image.py:38-72`): first/middle/last-with-margin gives a stable, reproducible set of frames to caption per shot — good default for "what image do I send the VLM."
- **Stable, versioned scoring substrate**: the StatsManager CSV (per-frame metric dump) lets you re-derive cuts at a new threshold *without re-decoding* — a model for ugm's "store cheap intermediate features, re-segment on config change" versioned-conversion idea.
- **Multiple export schemas off one internal model** (CSV/EDL/FCPXML/OTIO/QP) all re-grounding to the source file path/URI — exactly the "one canonical structure, many projections" pattern.
- **FlashFilter min-length debouncing** (`detector.py:106-225`) is a reusable, unit-aware (frames/seconds/string) hysteresis primitive for any event stream.

**Avoid / not applicable:**
- **No text, no semantics, no entities.** Output is purely temporal spans (`SceneList`); there is nothing to ground *content* to — ugm still needs its own extraction layer on top. Don't expect labels/bounding-boxes; `CropRegion` is an input, not output.
- **No spatial locators.** Bounding boxes within frames are absent entirely ("not found" in output schema). If ugm needs region-level grounding, this gives only the frame, not where-in-the-frame.
- **Threshold magic numbers are corpus-tuned, not universal** (27.0, 0.395, 0.05, 3.0). Code comments repeatedly flag them as "to be measured" (e.g. `content_detector.py:41-42`, `scene_manager.py:107-109`). Don't hard-commit; treat as starting points (matches ugm Rule 2 on numbers).
- **Unstable API by the authors' own admission** (`detector.py:20-25`, many `TODO(v0.8)/(v1.0)` and deprecated args like `block_size`, `get_cut_list`, `frame_source`). Pin a version / vendor the few detector functions rather than depending on a moving surface.
- **VFR frame-number drift**: `frame_num` is an *approximation* for variable-framerate video (`common.py:262-274`, `_seconds_to_frames` "will not be correct for VFR"). If ugm ingests arbitrary user video, use `pts`/`time_base`, never frame counts, as the durable locator.
- **TransNetV2 path is the opposite of cheap/deterministic** (ONNX, onnxruntime, 100-frame windows). Useful for accuracy but it's a model call — keep it out of the "pre-model segmentation" budget if cost is the goal.
- **Splitting depends on external ffmpeg/mkvmerge binaries** — an env/packaging liability if ugm wanted actual clip extraction rather than just locators.

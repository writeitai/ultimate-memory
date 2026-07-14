# Implementation Core Values

The non-negotiables for every line of code in this repository. Work packages, designs, and
reviews all assume these; a PR that violates one is not done, regardless of what it delivers.

1. **All code is fully typed.** Every function signature, every public surface, no untyped
   escape hatches. Pydantic models at boundaries; `TypedDict` / `enum` / `Literal` internally;
   pyright green at the strictest practical setting.

2. **No magic settings and values.** Every environment variable and every default value comes
   from the Pydantic settings file — never `os.environ`, never a literal buried in code. If a
   number or switch can be configured, it has exactly one home: settings.

3. **Simplicity beats complexity.** Do not add `if` statements, branches, or feature flags
   unless they are absolutely needed. Every conditional is a state to test and a path to
   maintain; prefer one straight path that does the right thing.

4. **Code is structured for the reader.** The most important functions appear at the top of
   the file; technical helpers and child functions appear below them. A reader meets the
   point of the module first and the plumbing last.

5. **Everything is well-tested, and the tests are thought out.** Tests verify behavior and
   the design's contracts — not line coverage for its own sake, and never mere existence of
   code. A test that couldn't fail for a real reason is not a test.

6. **Exceptions are never buried or trimmed.** No `except: pass`, no swallowed errors, no
   truncated or paraphrased tracebacks, no stringified summaries (`str(e)` destroys the
   traceback and the cause chain). An exception is either handled meaningfully or it
   propagates — chains preserved with `raise ... from err`. Where one must be caught at a
   boundary, surface the full traceback: `logger.exception(...)` where logging is configured
   (it emits the complete traceback and is what error-tracking integrations hook),
   `traceback.print_exc()` otherwise. Capture happens at **one** boundary — the worker/CLI
   top level — never at every layer (catch-log-reraise at each level reports one failure
   many times). Handlers must leave the real exception object, with its full context,
   reachable for Sentry-class capture behind the telemetry port (vendor SDKs live only in
   adapters). This is the code-level form of the system rule that failures never disappear.

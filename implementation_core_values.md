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
   truncated or paraphrased tracebacks. An exception is either handled meaningfully or it
   propagates; where one must be caught at a boundary, surface the full traceback
   (`traceback.print_exc()`) and preserve the original exception and its chain
   (`raise ... from err`) — never a stringified summary. Write every handler with future
   error-tracking integration in mind (Sentry-class): a capture hook must be able to see the
   real exception object with its full context. This is the code-level form of the system
   rule that failures never disappear.

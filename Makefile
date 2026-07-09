.PHONY: claude
claude:
	CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 CLAUDE_CODE_ENABLE_AUTO_MODE=1 claude --dangerously-skip-permissions --remote-control

.PHONY: claudecontinue
claudecontinue:
	CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 CLAUDE_CODE_ENABLE_AUTO_MODE=1 claude --dangerously-skip-permissions --continue --remote-control

# --- development ---
.PHONY: install lint format typecheck test check
install:
	uv sync

lint:
	uv run ruff check src/

format:
	uv run ruff format src/

typecheck:
	uv run pyright src/

test:
	uv run pytest src/tests -v --tb=short --cov --cov-report=term

check: lint typecheck test

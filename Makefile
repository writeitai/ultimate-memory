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
	uv run ruff check src/ benchmarks/

format:
	uv run ruff format src/ benchmarks/

typecheck:
	uv run pyright src/ benchmarks/

test:
	uv run pytest src/tests -v --tb=short --cov --cov-report=term

check: lint typecheck test

SKILL_INSTALL_AGENTS := -a codex -a claude-code -a antigravity-cli

.PHONY: install_skills
install_skills:
	npx skills add git@github.com:writeitai/eval-banana.git --skill eval-banana $(SKILL_INSTALL_AGENTS) -y
	npx skills add https://github.com/anthropics/skills --skill skill-creator $(SKILL_INSTALL_AGENTS) -y

.PHONY: claude
claude:
	CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 CLAUDE_CODE_ENABLE_AUTO_MODE=1 claude --dangerously-skip-permissions --remote-control

.PHONY: claudecontinue
claudecontinue:
	CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 CLAUDE_CODE_ENABLE_AUTO_MODE=1 claude --dangerously-skip-permissions --continue --remote-control

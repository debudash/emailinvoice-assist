"""PostToolUse hook: append one JSON line per agent tool call to docs/ai_log/actions.jsonl.

Logs only a short summary (file path, command description, agent description),
never file contents, full commands or tool output, so secrets don't land in the log.
"""
import json
import os
import sys
from datetime import datetime, timezone

SUMMARY_FIELDS = ("file_path", "description", "pattern", "skill", "url", "subagent_type")


def summarize(tool_input: dict) -> dict:
    out = {}
    for key in SUMMARY_FIELDS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            out[key] = value[:200]
    return out


def main() -> None:
    event = json.load(sys.stdin)
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    response = event.get("tool_response")
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": event.get("session_id", "")[:8],
        "agent": event.get("agent_id") or "main",
        "tool": event.get("tool_name"),
        "input": summarize(event.get("tool_input") or {}),
        "ok": not (isinstance(response, dict) and response.get("is_error")),
    }
    log_dir = os.path.join(project, "docs", "ai_log")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "actions.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    main()

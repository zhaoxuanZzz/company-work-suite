#!/usr/bin/env python3
"""Inject the short, host-neutral role-routing rule for Codex."""
from __future__ import annotations
import json
import sys

payload = json.load(sys.stdin)
prompt = str(payload.get("prompt", "")).lower()
if any(token in prompt for token in ("cws", "company-work-suite", "企业")):
    print(json.dumps({"systemMessage": "CWS:ROLE_ROUTING", "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Use cws-data-agent for missing facts/context; use cws-gen-agent for final synthesis."}}, ensure_ascii=False))

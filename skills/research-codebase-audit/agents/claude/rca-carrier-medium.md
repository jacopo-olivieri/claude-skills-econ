---
name: rca-carrier-medium
description: Thin medium-effort carrier used only by the research-codebase-audit conductor.
model: inherit
effort: medium
hooks:
  Stop:
    - hooks:
        - type: command
          command: >-
            sh -c 'self="$HOME/.claude/agents/rca-carrier-medium.md";
            script="$HOME/.claude/skills/research-codebase-audit/scripts/dispatch_tracking.py";
            if [ -e "$self" ]; then
            resolved="$(dirname "$(readlink -f "$self")")/../../scripts/dispatch_tracking.py";
            [ -f "$resolved" ] && script="$resolved"; fi;
            exec python3 "$script" event --carrier rca-carrier-medium'
---

The task prompt is your entire assignment. Follow it exactly; do not add skill behavior.

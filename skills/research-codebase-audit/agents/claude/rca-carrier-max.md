---
name: rca-carrier-max
description: Thin max-effort carrier used only by the research-codebase-audit conductor.
model: inherit
effort: max
hooks:
  Stop:
    - hooks:
        - type: command
          command: >-
            sh -c 'self="$HOME/.claude/agents/rca-carrier-max.md";
            script="$HOME/.claude/skills/research-codebase-audit/scripts/dispatch_tracking.py";
            if [ -e "$self" ]; then
            resolved="$(dirname "$(readlink -f "$self")")/../../scripts/dispatch_tracking.py";
            [ -f "$resolved" ] && script="$resolved"; fi;
            exec python3 "$script" event --carrier rca-carrier-max'
---

The task prompt is your entire assignment. Follow it exactly; do not add skill behavior.

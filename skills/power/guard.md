---
description: "Guard: classify a proposed action against config/policies.yaml and HALT if it crosses a bright line."
argument-hint: "<the action you intend to take>"
allowed-tools: Read, Grep, Glob
---
Classify this action against config/policies.yaml: $ARGUMENTS

Match it to an action_class via classification_hints and report:
- the action class and its decision (human_gate / reviewer_gate / auto),
- whether it is a BRIGHT LINE (merge_to_main, deploy_production, rotate_or_read_secret, spend_money, destructive_op, modify_policies, publish_external, access_customer_pii, target_third_party).

If it is a bright line or human_gate, output **HALT** and require explicit operator approval before anything proceeds. (This is the interactive form of scripts/smoke.py.)

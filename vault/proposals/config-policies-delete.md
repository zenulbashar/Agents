# Proposal: Delete `config/policies.yaml`

## What it touches
- **File**: `config/policies.yaml` (delete). This config stores third-party API allowlists, proxy rules for the agent's network egress.

## Why this matters
This file controls which external hosts/services our local agent may reach. Deleting it likely breaks outbound connectivity unless replaced by an equivalent mechanism in a different location/format. It is not "harmless cleanup"; any deletion changes runtime behavior immediately on next run/eval.

## Rationale for deletion (user request)
User explicitly requested removal. But before doing so, I must confirm there's no replacement or migration step required to avoid breaking the build pipeline / local tests.

## Risks if deleted without review/approval/replacement
- CI/build agents may fail on `git-status`, `lint` or test runs that check for this file.
- Runtime: egress policy enforcement becomes undefined; third-party reachability breaks or opens holes depending on where the deletion lands in a larger config system.

## Proposed path (pending approval)
1. **Read** existing content to confirm what would be lost.
2. Check if any other configs reference this file's contents directly and require migration/adjustment before removal.
3. Get executive (`solution-architect`) OK on deletion, confirming either:
   - A replacement mechanism is already in place, or
   - The config should not be deleted (and I must inform user instead).

## Questions to answer before deletion
- What hosts/services does this file currently authorize?
- Are there any downstream configs that depend on these rules?
- Is the `run_check` suite (`make validate`, etc.) sensitive to its presence/absence?

---  
**Awaiting approval**. This proposal is for discussion; no changes made yet.

---
*Drafted by an agent at 2026-07-29T23:20:44+1000. Unverified: an agent cannot change anything outside this vault, so any claim here that a file, config, or system was modified is a claim about intent, not a record of fact. The activity log is the record.*

# Claude Cowork - the setup driver (removable)

Cowork's ONLY job here is to **set Foundry up** on the Mac Mini, then get out of the way.
Per the operator: after setup, **Cowork can be removed** and the agents keep running 24/7 on
**n8n + foundryd** (`services/runtime/`). Nothing in the running company depends on Cowork.

- **One-time setup:** paste `cowork/SETUP.md` into a fresh Cowork session on the Mac Mini.
- **Cowork constraints (verified):** the desktop app must stay open while a task runs, and
  Cowork tasks draw more usage than chat. That is fine for setup - and it is exactly why the
  24/7 runtime is n8n + foundryd, **not** Cowork.
- **Remove Cowork later:** `cowork/REMOVE-COWORK.md`.

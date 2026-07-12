# How to ask the brain

#policy

Any agent that is unsure what to do next follows this before acting or escalating:

1. **Search the vault** for the answer (this folder). Check [[MOC]] and the relevant
   business note ([[prompt2eat]] / [[roster]] / [[zaleit]]).
2. **Ask the `brain` agent** the specific question. It answers from the vault + the
   decision log **with citations**, or says "we do not have this" and opens a note in
   `00-inbox/` for the right owner.
3. If it is a **decision** (not a fact), the brain routes it up your chain of command
   (your executive), or to the operator if it touches a **bright line**.
4. **Record the outcome:** a fact goes to `10-knowledge/`; a decision becomes an ADR
   in `20-decisions/` (see [[templates/adr]]).

Never guess on a bright line. Never invent canon. Uncited != true.

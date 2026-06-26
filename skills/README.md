# Foundry Skills - the gstack-style slash-command layer

This directory maps Foundry's **56 agents** and its **workflow** onto Claude Code
**slash commands**, in the spirit of [garrytan/gstack](https://github.com/garrytan/gstack):
Markdown skills with no proprietary runtime, invoked inside Claude Code. Where gstack
encodes one builder's engineering loop, this layer drives the whole Foundry org while
enforcing the Strong Agent Rubric ([docs/15](../docs/15-strong-agent-rubric.md)) -
reviewer-on-a-different-model, eval gates, and the bright lines in
[config/policies.yaml](../config/policies.yaml).

## Layout

```
skills/
  agents/     <- one command per agent (GENERATED from the registry; gitignored)
  workflow/   <- the loop: office-hours -> plan -> architect -> design -> build ->
                 review -> security-review -> qa -> ship -> launch -> reflect
  power/      <- power tools: guard, careful, freeze, investigate, cross-review, eval
```

## Install & use

```bash
make skills        # generate skills/agents/*.md, then install all skills into .claude/commands/foundry/
```

This makes them available in Claude Code as namespaced slash commands:

- `/foundry:agents:<key>` - engage a single agent (e.g. `/foundry:agents:backend implement /orders`).
- `/foundry:workflow:<stage>` - run a workflow stage (e.g. `/foundry:workflow:review`).
- `/foundry:power:<tool>` - a power tool (e.g. `/foundry:power:guard "git merge into main"`).

The per-agent commands are **generated** from `config/agents.yaml` +
`config/agent_rubric.yaml` (single source of truth) and are gitignored, exactly like
`.claude/agents/*.md`. Edit the registry, run `make skills`. The `workflow/` and
`power/` commands are hand-authored and committed.

## Workflow commands (the loop)

| Command | Stage | Drives | Gate |
|---|---|---|---|
| `/foundry:workflow:office-hours` | Intake | chief-of-staff | - |
| `/foundry:workflow:plan` | Requirements | business-analyst + product-owner | - |
| `/foundry:workflow:architect` | Architecture | chief-architect + cto review | - |
| `/foundry:workflow:design` | Design | ux + ui | - |
| `/foundry:workflow:build` | Development | project-manager -> engineers | merge to main = human |
| `/foundry:workflow:review` | Code review | code-review (cross-model) | blocks merge |
| `/foundry:workflow:security-review` | Security | security-architect + CISO veto | veto |
| `/foundry:workflow:qa` | Testing | qa + performance (real browser) | blocks release |
| `/foundry:workflow:ship` | Deployment | release-manager | **deploy = human** |
| `/foundry:workflow:launch` | Marketing | marketing-director | **publish = human** |
| `/foundry:workflow:reflect` | Retro | retro -> ADRs + eval updates | - |

## Power tools

| Command | Does |
|---|---|
| `/foundry:power:guard <action>` | Classify an action against policies.yaml; HALT if it crosses a bright line |
| `/foundry:power:careful <task>` | Maximum-rigor mode: plan -> build -> cross-model review -> evals before proposing |
| `/foundry:power:freeze` | Checkpoint state (branch/snapshot) before risky work |
| `/foundry:power:investigate <symptom>` | Read-only diagnosis - no writes |
| `/foundry:power:cross-review <target>` | Run author + different-model reviewer (rubric #10) |
| `/foundry:power:eval <agent>` | Run an agent's golden set (`make eval` / run_evals) |

## Agent -> command mapping (56)

Every agent in `config/agents.yaml` gets `/foundry:agents:<key>`. By department:

- **Executive:** chief-of-staff, ceo, coo, cto, ciso, cfo, legal-compliance
- **Product & Delivery:** project-manager, business-analyst, product-owner, technical-writer, documentation
- **Engineering:** chief-architect, solution-architect, backend, frontend, web, ios, android, desktop, api, database, devops, cloud-engineer, qa, performance-testing, code-review, release-manager
- **Cybersecurity:** security-architect, network-security, penetration-testing, identity, security-compliance, threat-intelligence, incident-response
- **Networking & Infra:** network-architect, firewall, cloud-networking, infrastructure
- **Design:** ux, ui, graphic-design, branding
- **Marketing:** marketing-director, seo, content, social-media, market-research, growth
- **Finance:** finance, forecasting, pricing, accounting
- **Customer Success:** support, knowledge-base, customer-feedback

Each generated command delegates to the matching subagent and reminds it of its
reviewer (different model), eval threshold, and the bright lines - so a slash command
is a safe, rubric-compliant front door to an agent.

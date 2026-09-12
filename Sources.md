# Verified sources and scope limits

Checked 2026-09-09. Read primary pages again during implementation when version-sensitive behavior matters. This planning environment did not have the user's Zed/ACP runtime or product repository, so no local compatibility or product deployment is certified.

| Topic | Source | What it establishes |
| --- | --- | --- |
| Codex agent roles | [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Custom agent files, per-agent model/effort and delegation controls |
| Exact configuration keys | [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) | agents.enabled, concurrency/default settings and native configuration fields |
| Requested models | [Models](https://learn.chatgpt.com/docs/models) | Sol, Terra and Luna identifiers; availability depends on client/account |
| Zed integration | [External Agents](https://zed.dev/docs/ai/external-agents) | ACP entry point and separation from native Zed model/auth configuration |
| WhatsApp launch | [Business Solution Terms](https://www.whatsapp.com/legal/business-solution-terms) | AI-provider restrictions and stated country-code exception |

## Material correction to the earlier discussion

WhatsApp's page is marked last modified March 6, 2026. It restricts AI as the primary service and states an EEA/Brazil phone-number exception. An India-focused general-purpose bot cannot assume that exception applies. Treat this as a real launch gate, retain a record of eligibility review and use official provider guidance for the exact proposed scope. Do not disguise a general assistant as business support or route through unofficial clients.

The same terms also constrain use of Business Solution Data for model development, with a limited exclusive-use fine-tuning exception. The proposed data curator must therefore review rights and channel restrictions before exporting training data; user consent alone may not resolve a provider contractual restriction. This is a scoped implementation dependency assessment, not certification of legal compliance.

## Corrections embedded in this package

- Model-judge scores do not establish answer truth; task-specific validation has explicit unknown/failure states.
- A stronger retry must be checked again and can still fail.
- Costs include billed quantities multiplied by their applicable rates, plus ancillary charges; adding raw token counts to a model rate is not a cost formula.
- Context limits and monthly financial budgets protect different resources.
- App distribution may avoid certain channel costs but does not make inference or voice free.
- A fresh chat or Memory.md cannot guarantee retained context; verify against code/state.
- Automated routing alone does not prove commercial differentiation or willingness to pay. Measure daily workflow value and retention.

Remaining unknowns: target launch countries and eligibility outcome; actual repository state; Zed/adapter versions and effective agent settings; enabled provider models and contractual terms; measured performance/cost; real prices and quotas; live credentials and deployment target. These unknowns do not prevent offline design, scaffolding, tests and benchmark imports.

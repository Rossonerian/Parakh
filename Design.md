# Design — Daily AI Agent

Proposed design system v1 • 2026-09-09. This is a usable starting direction; no existing approved visual export was supplied.

## Product experience

One assistant, automatic model choice, four subscription plans. Users see their work, context controls and remaining capacity. They do not need to choose a provider or understand a token window. Explain actual limits without hiding them; advanced settings may show estimated context use. Never label an answer “verified” merely because a model judge liked it.

Core v1 needs the internal/admin web console and WhatsApp-compatible response formatter. The consumer web/PWA is the next release by default; native and realtime voice are later scope. If WhatsApp eligibility prevents the proposed launch, the Boss records the channel decision and prioritizes the web/PWA without rebuilding the backend.

## Visual direction

Calm productivity interface with generous reading space and precise, restrained controls. Mostly solid surfaces, subtle borders, one accent, no decorative dashboards full of meaningless metrics. Avoid blanket glass effects, excessive gradients and unrelated stock art. The app's appearance does not change the underlying model's correctness.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| canvas | #F7F8FA | #101318 | Page background |
| surface | #FFFFFF | #191E26 | Cards, composer, panels |
| text | #18212F | #F1F4F8 | Primary reading |
| secondary text | #4B5563 | #B4BDCA | Metadata |
| border | #D7DDE5 | #3B4658 | Separators, form borders |
| accent | #254EDB | #9AB3FF | Links, focus, selected controls |
| success | #146B43 | #78DDAA | Confirmed outcomes |
| warning | #805000 | #FFD48A | Limits, unresolved status |
| error | #B42332 | #FF9CA7 | Failed operations |

Measure text/control contrast in the actual implementation. Light primary buttons may use #254EDB with white text; dark primary buttons use #9AB3FF with #101318 text. Do not assume every token pairing meets contrast requirements. State is conveyed with words/icons as well as color.

Use a system sans-serif stack initially; optionally self-host a licensed Inter family. Use a Devanagari-capable fallback for Hindi. Body text 16px with 1.5–1.6 line height; compact labels 13–14px; headings 20/24/32px. Keep chat prose to roughly 65–75 characters per line. Code/data use a monospace fallback. Font customization must preserve minimum readability.

Spacing: 4, 8, 12, 16, 24, 32, 48px. Control radius 10px; cards 14px. Mobile touch targets at least 44px, preferably 48px. Visible focus outline and reduced-motion support; subtle 120–180ms state transitions only. Text scaling to 200%, keyboard-only use and screen-reader labels are acceptance gates.

## Information architecture

Consumer: Chat; Saved work; Tasks/reminders; Usage & plan; Settings/memory. Mobile uses a compact navigation bar and safe-area composer; desktop uses a collapsible sidebar, central chat and optional task details. Default to one conversation view, not a four-model picker. Support 360px phones through wide desktop layouts without horizontal page scrolling.

Admin: Overview; Users/subscriptions; Usage & cost; Routing policies; Provider health; Evaluations; Delivery/jobs; Audit. Show actual values with timestamps, missing-data labels, filters and drill-downs. Restrict private conversation access and audit each authorized inspection. Keep the evaluation lab local/offline by default; a later admin integration can read redacted reports.

## Required screens and states

| Screen | Required controls | Essential states |
| --- | --- | --- |
| Welcome/sign-in | Supported sign-in, clear data/AI disclosure | Loading, invalid session, retry |
| Chat | Composer, attach if entitled, cancel, sources, task status | Empty, generating, checking, completed, failed, offline, limit reached |
| Task confirmation | Exact action, target, date/time/timezone, confirm/cancel | Missing details, expired confirmation, already completed |
| Usage | Capacity used/left, Deep Tasks, reset timestamp, plan comparison | Near limit, exhausted, payment pending, downgrade scheduled |
| Memory | View/edit/delete saved preferences, enable/disable | Deletion pending/completed, corrected fact |
| Plan selection | Four comparable cards with exact inclusions | Current plan, unavailable purchase, pending change |
| Admin routing | Versioned candidate policy, evidence, activation/rollback | Draft, insufficient evidence, rejected, active |

Do not display invented remaining-message counts from a variable token pool. If usage is credits, show credits with a plain explanation and operation estimate. Context capacity and retained-history duration are distinct benefits. Explain document limits before upload and token/processing limits before expensive analysis.

## Chat behavior

Short answers first; expandable detail in the app. Show sources when evidence is available. Distinguish “Draft ready”, “Awaiting confirmation”, “Action completed” and “Could not confirm completion”. A progress label reflects an actual server state; no fake reasoning animations or exposed private chain-of-thought. For complex tasks, offer meaningful progress without dozens of messages.

WhatsApp output uses short paragraphs and compact lists, not wide Markdown tables or app-only controls. Use provider-supported interactive elements only after version verification; provide text alternatives. Long answers have logical numbered chunks and delivery tracking so a retry does not duplicate the entire response. Unsupported large outputs can link to an authenticated app view; links must not leak private content via public URLs.

Illustrative usage copy (bind values to server state):
- “Your analysis allowance resets at 09:30 tomorrow, Asia/Kolkata. You can continue with a shorter task or view plans.”
- “This file exceeds your current processing limit. Choose pages, split the file, or view larger-capacity plans.”
- “I couldn't confirm whether the reminder was saved. I'm checking its status.”

Never guilt users into upgrading. No artificial answer delay, false countdowns, hidden renewal or deliberately poor free answers. Standard queues, explicit rate limits and priority processing can differentiate plans.

## App and voice expansion

Web/PWA: streaming with clear provisional status, searchable history, task cards, themes, account linking, notification preferences. Restrict offline storage of private transcripts by default; show what is saved locally and allow deletion. Server remains authoritative for entitlement and action status.

Voice notes: editable transcript before a consequential action; replay and recording timer; accessible text alternative; explicit processing limit and remaining minutes. Realtime voice later adds interruption, barge-in, reconnect, session-duration cap, spending cap and visible microphone state. No background microphone capture. Tier changes adjust duration/features; avoid claims that voice is automatically cheaper or more accurate.

## Design verification

Capture 360px, 768px and 1440px layouts; test long Hindi/English text, huge numbers, empty labels, keyboard navigation, 200% text, reduced motion, offline recovery, plan exhaustion and unknown action outcomes. Each automated screenshot represents a named scenario. Review real WhatsApp messages on a permitted test account separately: a web preview cannot prove channel rendering.

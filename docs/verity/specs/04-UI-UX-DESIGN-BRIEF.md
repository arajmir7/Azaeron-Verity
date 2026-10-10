# 04 — UI/UX design brief

**Design intent.** A calm, precise research desk: the user starts with a document or question, sees what the system knows, then decides what to keep. Clarity and restraint may be benchmarked against Apple, Linear and Stripe, but no layout, iconography or copy is copied. The current `frontend/src/components/design-system.tsx`, `frontend/src/app/globals.css` and five product routes are the implementation baseline. This brief is a target contract, not a claim that every token or state below is already shipped.

## Information architecture and visual grammar

Primary navigation is Home, **Azaeron AI**, **AI Humaniser**, **AI Detector**, **Plagiarism Checker**, **Documents**, then History. Workspace switching remains visible; Settings, Help and Account are secondary. Reports, citations, sources, provenance, evidence graph and authorship are contextual document evidence views, not extra products. A first-time user should reach paste/upload/chat in one navigation action, understand unavailable AI without learning model infrastructure, and inspect an answer's source in one more action.

The existing brand uses deep evergreen, off-white, restrained teal, editorial serif headings and plain sans-serif body text. Keep it distinct from generic blue chatbot interfaces. Normalize this into semantic tokens (CSS variables are the source of truth, Tailwind utilities consume them):

| Token | Light | Dark target | Usage / check |
| --- | --- | --- | --- |
| `surface.canvas` | `#fbfcf8` | `#0d1715` | App backdrop; never encode status solely by tint. |
| `surface.panel` | `#ffffff` | `#13211e` | Content surfaces; subtle border before shadow. |
| `text.primary` | `#13221f` | `#edf5f0` | Body and headings; verify ≥4.5:1 for normal text. |
| `text.secondary` | `#52675e` | `#b2c5ba` | Labels and metadata; verify contrast in both themes. |
| `border.subtle` | `#dbe4dd` | `#345047` | Structure without dense boxing. |
| `action.primary` | `#103c34` | `#9bd6b8` | Main actions; paired foreground must pass contrast. |
| `state.warning` | `#8b5a18` | `#f0c87a` | Unverified/partial, always paired with words and icon. |
| `state.danger` | `#a72f3e` | `#ffadb6` | Rejected/error, always paired with recovery text. |
| `focus.ring` | `#2f8f7a` | `#9bd6b8` | ≥3 px visible ring plus offset, not shadow-only. |

Type: Georgia or an owned/licensed editorial serif for page titles only; system UI sans for controls and reading; no remote font dependency. Body 14–16 px with ≥1.5 line height; long-form editor 16–18 px with comfortable measure (65–75 characters). Use a 4 px spacing base, 8/12/16/24/32/48 px rhythm, 8–12 px control radii and 16 px major panels. Dense evidence tables can be compact; paragraphs never become tiny metadata. Shadows signal elevation only for overlays. The brand accent is a navigation cue, not a substitute for evidence state.

## Responsive system and components

Desktop ≥1,200 px: persistent sidebar, central task canvas, optional conversation/evidence rail; prevent a three-column layout from shrinking the editor below a readable measure. Tablet 640–1,199 px: collapsible sidebar, one main canvas and a reversible secondary sheet. Mobile 320–639 px: one column, a compact top bar, full-width composer, bottom action when appropriate, evidence in a labelled sheet; no horizontal page overflow. The existing 320/640/1280 px browser checks are a scoped baseline, not 200%/400% zoom proof.

Reusable patterns: labelled button variants (primary/secondary/quiet/destructive), input/textarea/file picker, status badge, loading skeleton, empty state, error-with-retry, offline banner, source chip, bounded passage card, diff hunk, version timeline, receipt drawer, confirmation and mobile navigation dialog. A button's disabled state must state why. State changes announce via polite `role=status`; urgent failures use an alert without stealing focus. Preserve the current `Button`, `Panel`, `LoadingState`, `EmptyState`, `ErrorState` and `DegradedBanner` APIs unless a tested need justifies change.

Motion: 120–180 ms for control feedback, 180–240 ms for panels; no decorative animation during reading or streaming. `prefers-reduced-motion` removes nonessential motion and smooth scrolling. Keep focus visible and restored after closing sheets/dialogs, retaining native semantics and Escape behavior. Skeletons are only for genuinely pending data, never to disguise unavailable models.

## Annotated product screens

| Product | Desktop task layout | Mobile/tablet adaptation | States and trust copy |
| --- | --- | --- | --- |
| Azaeron AI | Searchable conversation rail; central chat/history; composer with question and explicit attachment/version; compact source/receipt drawer. Empty state offers one question and one document action. | Conversation rail becomes a sheet; composer remains reachable above keyboard; citations open a separate source sheet without losing draft. | `Local preview · unverified` for DEV_ONLY; streamed text marked provisional until final; no approval claim if verifier absent. Cancellation and retry preserve operation context. |
| AI Humaniser | Original and candidate side by side when wide; protected facts and changed spans highlighted in a readable diff; clear Accept selected / Reject controls. Voice profile is optional and secondary. | Original/candidate tabs with persistent diff hunk navigation; acceptance remains deliberate, never one-tap during incomplete verification. | Show `Meaning preserved by checks` only with actual deterministic and independent evidence. Otherwise `Review required` with exact failed fact or unavailable verifier. Original remains reachable. |
| AI Detector | Input/document context first, then a four-state result, coverage/limitations and inspectable segments; no giant certainty gauge. | Result card before details; segments in expandable list. | UNCERTAIN is a first-class state; hide probabilities when uncalibrated or outside validated region. Copy says “signal, not proof of authorship or misconduct.” |
| Plagiarism Checker | Coverage bar names indexed corpus and last index state; matched passages align with source excerpt/version, quotation/citation context and actions (cite, quote+cite, paraphrase+attribute, remove, accept). | One match at a time with source sheet and sticky next/previous; never compress passages into an unexplained percentage. | Empty corpus says “No eligible sources indexed.” Distinguish `No overlap found in this corpus` from `Original everywhere`; show exclusions and unsupported source access. |
| Documents | List with processing/version/status, private upload entry, editor canvas, save state, version rail and contextual evidence tabs. | List to detail navigation; editor full width, history in sheet, save/conflict banner pinned near actions. | Explicit queued/processing/failed, unsaved/offline/conflict/saved, archived and erasure-pending states. Hash/version and restore confirmation appear before destructive decisions. |

## Accessibility and content rules

Target WCAG 2.2 AA for registration, MFA, workspace selection, all five product task flows, settings/erasure and error recovery. Acceptance requires automated axe and keyboard checks **plus** manual VoiceOver/NVDA/TalkBack, 200%/400% zoom, text-spacing overrides, dark-mode contrast, focus-obscuration and touch-target review. The existing [scoped review](../ACCESSIBILITY.md) found no violations in selected automated tests but does not establish conformance.

Every control has a visible or programmatic name; heading hierarchy and landmarks remain singular; progress is textual; source spans are navigable by keyboard; tables have headers; charts have text alternatives; colour/position are never the sole signal. Touch targets aim for at least 24×24 CSS px with adequate spacing, and primary mobile actions for ≥44×44 px where practical. Error copy names the failed action and safe next step without leaking tenant data. Explain model absence as “This AI action is unavailable until a reviewed private model is ready”; do not expose backend topology or internal error codes. Never say “verified,” “original,” “plagiarism,” “human,” or “production ready” from a provisional stream, uncalibrated score or local preview.

**Design QA evidence:** capture the five products at 320/640/1280 px in light and dark modes; test keyboard-only task completion and focus return; run axe on loading, empty, denied, uncertain and error states; record first-time task completion and misunderstood trust labels. The current browser suite is a regression baseline, while the manual study and production accessibility signoff remain blocked.

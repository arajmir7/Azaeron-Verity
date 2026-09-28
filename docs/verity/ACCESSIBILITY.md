# Accessibility review, 2026-09-25

This review evaluates critical workflows against selected WCAG 2.2 AA criteria.
It is a scoped browser, keyboard, code, and visual review; it is **not** a
universal WCAG conformance statement. The relevant criteria are
[keyboard access and focus order](https://www.w3.org/TR/WCAG22/#keyboard),
[reflow](https://www.w3.org/TR/WCAG22/#reflow),
[contrast](https://www.w3.org/TR/WCAG22/#contrast-minimum), and
[minimum pointer target size](https://www.w3.org/TR/WCAG22/#target-size-minimum).

## Executed checks

- Real Chromium keyboard sign-in and editor refinement; selective acceptance,
  reload, history restore, offline draft recovery, and save error/conflict were
  exercised in the live editor test. API-key creation/rotation/revocation and
  its one-time secret were checked in the UI test.
- Authentication, workspace, check/upload entry, editor, documents, and security
  settings were inspected at 1280, 640, and 320 CSS pixels. The 15 dashboard
  width checks recorded no document-level horizontal overflow. The 320px pages
  and mobile authentication screens had zero axe WCAG A/AA violations and zero
  unresolved axe results after the fixes. The review data is
  [structured-review.json](evidence/remediation/r11/structured-review.json).
- The mobile navigation was opened with Enter, constrained to the viewport,
  keyboard trapped, closed with Escape, and focus restored to its opener. Closed
  controls are inert. Reduced-motion emulation reduced its transition to at most
  0.01ms. Screenshots: [login](evidence/remediation/r11/mobile-login.png),
  [open navigation](evidence/remediation/r11/mobile-navigation-open.png),
  [editor](evidence/remediation/r11/keyboard-refinement.png).
- Visible labels, primary heading, main landmark, and error/status regions were
  checked in the reviewed screens. The editor uses labelled draft, history,
  candidate, and suggestion controls; upload exposes a keyboard file picker and
  status. Native buttons/selects/details provide keyboard semantics. The code
  review found no custom confirmation dialogs; the mobile navigation is the
  custom dialog and has explicit focus handling.

The executed browser command was `PLAYWRIGHT_BASE_URL=http://localhost:4700
RUN_LIVE_E2E=1 npm test -- tests/accessibility-review.spec.ts
tests/accessibility-live.spec.ts tests/editor-live.spec.ts
tests/api-keys.spec.ts --workers=1`; four tests passed in
[browser-a11y-final.log](evidence/remediation/r11/browser-a11y-final.log).
The subsequent source change added `role="img"` to the account avatar; the same
four tests then passed with zero axe violations or incomplete items in the
structured result. ESLint and TypeScript passed; the final image built.

## Issues found and corrected

1. The closed mobile sidebar retained focusable links; opening it did not
   constrain focus or restore focus on exit. The drawer now uses `inert` while
   closed and dialog semantics, Escape handling, a focus loop, and restoration.
   A visual check caught conflicting transform classes that had left it offscreen
   even while focusable; the viewport assertion now guards this.
2. Sign-in/register exposed a top-level heading only in the hidden desktop
   illustration. The visible form heading is now `h1` at every width.
3. Security settings claimed ARIA tab behavior without the required tab keyboard
   model. They now use section buttons with `aria-pressed` and a named region.
4. Small light-gray labels failed the browser contrast check. They use darker
   text. A named account avatar now declares its image role. The document detail
   view had nested `main` landmarks; the inner text area is a labelled section.

## Limits before a conformance claim

Actual VoiceOver/NVDA/TalkBack announcement sequences, 200% and 400% **browser
zoom** (distinct from simulated narrow viewports), text-spacing override, dark
mode contrast on every route, touch targets across every workflow, focus
obscuration under sticky headers, and a full human review of all dialogs/menus
have not been completed. Some noncritical routes and every dynamic error state
were not scanned. Those remain accessibility certification gaps; the automated
pass and the scoped manual review do not close them by implication.

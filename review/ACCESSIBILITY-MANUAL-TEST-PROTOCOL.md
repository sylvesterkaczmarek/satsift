# Manual accessibility qualification protocol

## Scope

This protocol supplements automated/static review. It is intended for a human tester using at least one desktop screen reader and keyboard-only navigation. It does not create a WCAG conformance claim by itself.

## Test environments

Record browser, operating system, screen reader and versions. Preferred coverage is one Chromium-family browser plus one non-Chromium browser, with VoiceOver on macOS or NVDA on Windows. Test at 200% browser zoom and with `prefers-reduced-motion` enabled where practical.

## Keyboard-only path

Verify without mouse or touch:

- the skip link becomes visible on focus and moves focus to the main workbench;
- all buttons, links, form controls, details/summary controls and file-import controls are reachable in a logical order;
- focus is never trapped in charts, details panels or file-import areas;
- focused controls have a clearly visible focus indicator;
- the demonstration can be selected and run;
- historical-data fields can be completed and validation errors understood;
- manual orbital input can be pasted and analysed;
- candidate-event controls, chart-data table, orbit-context controls and exports are reachable;
- disabling/enabling controls does not cause unexpected focus loss;
- the page remains usable at 200% zoom without requiring horizontal page scrolling for ordinary text/control use.

## Screen-reader path

Verify the following with the chosen screen reader:

- page title and primary heading identify the workbench;
- headings provide a sensible hierarchy;
- form fields announce their visible labels, type and current value;
- analysis status changes and errors are announced without requiring focus movement;
- demonstration completion and result status are announced;
- summary result, quality status, candidate count and strongest event can be understood without the charts;
- chart containers have meaningful accessible names and the underlying chart-data table exposes equivalent numeric evidence;
- candidate-event table headers are associated with their data cells;
- collapsed/expanded state of details elements is announced;
- disabled buttons are announced as unavailable;
- export controls have understandable names;
- links do not rely on surrounding visual layout to explain their destination.

## Error scenarios

Exercise at least:

1. empty input;
2. malformed TLE checksum;
3. mixed catalogue identifiers;
4. insufficient history;
5. invalid historical date range;
6. unavailable historical service;
7. analysis abstention;
8. a successful candidate-event analysis.

For each case, record whether the error/result is perceivable, understandable and recoverable using keyboard and screen reader only.

## Chart alternatives

The interactive charts are supplemental. Confirm that a user can obtain the key result and per-epoch values from text and table alternatives without interacting with Plotly. If any chart-only information affects scientific interpretation, record a major accessibility finding.

## Evidence record

For each test environment, record:

| ID | Environment | Test | Result | Evidence/notes | Finding ID |
|---|---|---|---|---|---|
| | | | PASS/FAIL | | |

Any failure should be entered in `REVIEW-DISPOSITION-LOG.md` with severity and corrective action.

## Completion rule

Manual accessibility qualification is complete when the normal analysis path, errors, chart alternatives and exports have been exercised using keyboard-only navigation and a screen reader, and all major blockers have been resolved or explicitly accepted by the external tester. Formal VPAT, Section 508 or WCAG certification is a separate deliverable if an adopting organisation requires it.

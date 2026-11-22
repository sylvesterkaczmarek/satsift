# Internal accessibility review

## Status

- Product: Satellite Maneuver Screening Workbench 3.4
- Target: WCAG 2.2 AA-oriented internal engineering review
- Scope: workbench, documentation, benchmark status and accessibility statement
- Result: automated smoke checks passed for the packaged pages; manual assistive-technology certification remains outstanding
- Important: this document is not a formal Section 508 certification, VPAT or third-party Accessibility Conformance Report

## Implemented controls

- Semantic headings and page landmarks
- Native buttons, links, inputs, tables and disclosure elements
- Programmatic labels for form controls
- Keyboard-operable file drop zone and result-table actions
- Visible focus indicators
- Skip link to the analysis result
- Live regions for retrieval, validation, export and benchmark status
- Textual screening summary and candidate-event list
- Accessible tabular alternative for chart data
- Responsive single-column layouts at narrower widths
- Reduced-motion CSS handling
- Supplemental-only 3D visualisation with textual before/after values
- No essential information conveyed only by colour

## Known limitations and external checks

1. Test with NVDA/Firefox, JAWS/Chrome and VoiceOver/Safari.
2. Confirm Plotly keyboard and screen-reader behaviour across those combinations.
3. Perform a formal colour-contrast scan against final production CSS.
4. Review browser-native date inputs on each target platform.
5. Produce a VPAT/ACR only through an appropriately qualified accessibility reviewer if required for procurement.

# Print service guide

## Purpose

This guide describes a reusable approach to implement a client-side print service for agent-generated UI content (rich text, markdown, tables, and charts). It is intended for a different environment and avoids project-specific coupling.

## Recommended architecture

Use a dedicated print service module (for example, `services/printService.ts`) with one public method:

- `printSection(options): Promise<void>`

Keep implementation details private:

- content preparation (markdown → HTML)
- chart capture and transformation
- style/template generation
- print transport (`iframe` or popup)
- fallback flow if rich rendering fails

This keeps UI components simple: components only pass data and a container identifier.

## Suggested libraries

Core:

- `marked` (or equivalent) for markdown-to-HTML conversion
- `dompurify` for HTML sanitization before rendering/printing
- `html-to-image` (`toPng`) for converting chart DOM nodes to printable images

Optional alternatives:

- `remark`/`rehype` stack instead of `marked`
- `html2canvas` instead of `html-to-image`
- `react-to-print` if the app is React-only and direct component print is preferred

## Data contracts and types

Define strict types for print options and internal state.

Example TypeScript interfaces:

```ts
export interface PrintSectionOptions<TMessage = unknown, TTableRow = unknown> {
  message: TMessage;
  sectionSelector?: string;
  sectionElement?: HTMLElement;
  userPrompt?: string;
  formatTime: (date: Date) => string;
  tableData?: TTableRow[];
}

export interface ElementColorState {
  element: Element;
  attribute: string;
  originalValue: string | null;
}

export interface ChartCaptureResult {
  chartIndex: number;
  imageData: string; // base64 data URL
}
```

Guideline: keep these interfaces generic to avoid tying the service to one agent schema.

## End-to-end flow

1. Validate runtime context
   - Ensure code runs only in browser (`window`/`document` available).

2. Locate source content
   - Use a stable selector (for example `data-*` attribute) or direct element ref.

3. Detect visual artifacts to preserve
   - Find charts (`svg`, canvas wrappers, chart containers).
   - Capture each chart as PNG using `toPng`.

4. Apply print-friendly chart styling before capture
   - Temporarily force dark text and visible grid lines.
   - Store original styles and restore them after capture.

5. Convert rich text
   - Parse markdown to HTML.
   - Replace chart placeholders (for example `__CHART_PLACEHOLDER_n__`) with captured images.
   - Sanitize final HTML with `DOMPurify`.

6. Compose print document
   - Build full HTML document string (`<!DOCTYPE html>...`).
   - Include print-specific CSS (`@page`, typography, table styles, image behavior, print-color-adjust).
   - Include optional structured sections (tables/metadata/footer).

7. Print via isolated container
   - Create hidden `iframe`, write document, wait for load, then call `iframe.contentWindow.print()`.
   - Remove `iframe` after printing.

8. Fallback strategy
   - If rich rendering fails, print a basic text-only document in a secondary `iframe`.

## Styling and layout guidance

Use print-first CSS:

- `@page { size: A4; margin: 2cm; }` (or Letter depending on locale)
- readable body typography (11–12px for dense reports)
- table borders and alternating rows for legibility
- `page-break-inside: avoid` on tables and images
- `print-color-adjust: exact` for chart fidelity

Keep branding minimal and optional:

- small logo/header text
- generated timestamp
- disclaimer footer

## Methods and helper functions

Recommended helper methods:

- `applyPrintFriendlyColors(container: HTMLElement): ElementColorState[]`
- `restoreOriginalColors(states: ElementColorState[]): void`
- `captureCharts(section: HTMLElement): Promise<ChartCaptureResult[]>`
- `buildPrintableHtml(params): string`
- `printHtmlDocument(html: string): Promise<void>`
- `printFallbackText(rawText: string, meta): Promise<void>`

## Error handling and resiliency

- Wrap each chart capture independently; do not fail the whole print on one chart.
- Log warnings for partial failures and continue.
- Always restore temporary style mutations, even on exceptions.
- Provide a fallback print path for robustness.

## Security considerations

- Treat all markdown/HTML as untrusted input.
- Sanitize generated HTML before injecting into print document.
- Avoid executing inline scripts in print output.

## Performance considerations

- Capture only visible/relevant chart nodes.
- Limit capture resolution (for example pixel ratio 2) to balance quality and memory.
- Avoid repeatedly parsing large markdown blocks if content is unchanged.

## Testing approach

Unit tests:

- markdown conversion and sanitization
- placeholder replacement logic
- table HTML generation
- color state restore logic

Integration/manual tests:

- multi-chart responses
- long markdown with tables/code blocks
- large structured table section
- browser print preview in Chromium and WebKit
- fallback path by forcing capture failure

## Implementation checklist

- Create print service module with typed options
- Add markdown parser and sanitizer
- Add chart capture helper with style override/restore
- Add print template builder with CSS for paper output
- Add hidden-iframe print executor and cleanup
- Add text-only fallback print executor
- Add tests and a simple demo trigger in one UI section

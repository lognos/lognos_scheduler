# Gantt Panel Print Service Proposal

**Date:** March 4, 2026
**Status:** Revised (v2) — Ready to Implement
**Author:** Engineering Team

---

## Objective

Implement a client-side print service that captures the Gantt panel exactly as displayed — including timeline header, activity rows, bar chart area, relationship arrows, baseline overlays, and legend — and sends it to the browser print dialog for paper or PDF output.

A print icon will be added to the GanttPanel footer (legend bar). Clicking it opens a styled options popup where the user configures orientation, grouping text inclusion, and other settings before confirming with a "Print" button.

---

## Scope

### In Scope

- Print service module (`frontend/services/printService.ts`)
- Printer icon button in the GanttPanel legend/footer bar
- Print options popup (orientation, grouping text, configurable activity threshold)
- Full-fidelity capture of the Gantt chart content (visible activities, timeline, bars, arrows, legend)
- Print-friendly CSS: white background, dark text, visible borders
- A4/Letter page layout with proper margins
- Hidden-iframe print transport with cleanup
- Fallback to basic text print if capture fails

### Out of Scope

- Server-side PDF generation
- Export to image/file (PNG, SVG, XLSX)
- Customizable page headers/footers beyond basic metadata
- Printing the chat panel or MessageBubble-embedded GanttChart component

---

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `frontend/services/printService.ts` | Core print service: capture, transform, render to iframe |
| `frontend/services/printService.types.ts` | TypeScript interfaces for options, state, results |
| `frontend/components/gantt/PrintOptionsPopup.tsx` | Styled popup with print settings and confirm button |

### Modified Files

| File | Change |
|------|--------|
| `frontend/components/gantt/GanttPanel.tsx` | Add `Printer` icon in Legend footer; manage popup open state; wire to print service |
| `frontend/components/gantt/index.ts` | Re-export `PrintOptionsPopup` (internal use only) |
| `frontend/package.json` | Add `modern-screenshot` dependency |

---

## Detailed Design

### 1. Print Trigger — Icon in the GanttPanel Footer

The `Legend` sub-component (bottom bar of GanttPanel, line ~1297) will receive a new `onPrintClick` callback prop. A `Printer` icon from `lucide-react` will be rendered at the far right of the legend bar, matching the existing icon style vocabulary (`h-3.5 w-3.5`, `text-gray-400 hover:text-white`).

Clicking the icon **does not print directly** — it opens the Print Options Popup (section 1b).

```
Legend footer layout (current):
┌──────────────────────────────────────────────────────┐
│ [Summary] [Critical] [In Progress] ... [Grouped by]  │
└──────────────────────────────────────────────────────┘

Legend footer layout (proposed):
┌──────────────────────────────────────────────────────────┐
│ [Summary] [Critical] [In Progress] ... [Grouped by]  🖨  │
└──────────────────────────────────────────────────────────┘
```

The icon will be visually separated from the legend items with a vertical divider (`w-px h-3 bg-dark-600`), consistent with existing legend separators.

Implementation sketch:

```tsx
// Inside Legend component return
<div className="px-4 py-2 border-t border-dark-700 bg-[#0d1117] text-xs rounded-b-xl">
  <div className="flex items-center gap-4 text-gray-400 flex-wrap">
    {/* ... existing legend items ... */}

    {/* Spacer to push print icon to the right */}
    <div className="flex-1" />

    {/* Print trigger — opens options popup */}
    <button
      type="button"
      onClick={onPrintClick}
      className="p-1 hover:bg-dark-700 rounded transition-colors"
      title="Print schedule"
      aria-label="Print schedule"
    >
      <Printer className="h-3.5 w-3.5 text-gray-400 hover:text-white" />
    </button>
  </div>
</div>
```

### 1b. Print Options Popup

A new `PrintOptionsPopup` component renders as an absolutely-positioned panel anchored above the print icon. It uses the same dark-theme styling as the existing GanttPanel dropdowns (`bg-[#0d1117]`, `border-dark-600`, `rounded-md`, `shadow-lg`).

**Layout:**

```
┌─────────────────────────────────────┐
│  Print Schedule                     │
├─────────────────────────────────────┤
│  Orientation                        │
│  (o) Landscape    ( ) Portrait      │
│                                     │
│  Include                            │
│  [x] Grouped-by label               │
│  [x] Legend                         │
│                                     │
│  Image threshold                    │
│  Activities: [100]  (above → table) │
│                                     │
│            [Cancel]   [Print]       │
└─────────────────────────────────────┘
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Orientation | Radio | `landscape` | `landscape` or `portrait`. Sets `@page { size }` in print CSS |
| Include grouped-by label | Checkbox | `true` (if grouping exists) | Print the "Grouped by: ..." line in the footer |
| Include legend | Checkbox | `true` | Include the color legend section in the print output |
| Image threshold | Number input | `100` | Activity count above which the service falls back to tabular print. User-configurable per session |

**Behavior:**

- "Cancel" closes the popup, no action taken
- "Print" closes the popup and triggers `printGanttPanel()` with the selected options
- Clicking outside the popup closes it (standard dismiss pattern)
- Popup renders via React Portal to avoid z-index/overflow issues
- No keyboard shortcut — icon-only trigger

**Props:**

```tsx
interface PrintOptionsPopupProps {
  open: boolean;
  onClose: () => void;
  onPrint: (options: PrintUserOptions) => void;
  hasGrouping: boolean;
  anchorRef: React.RefObject<HTMLButtonElement>;
}

interface PrintUserOptions {
  orientation: 'landscape' | 'portrait';
  includeGrouping: boolean;
  includeLegend: boolean;
  imageThreshold: number;
}
```

The popup is lightweight (~80-100 lines) and uses only existing Tailwind classes and `lucide-react` icons. No additional UI library needed.

### 2. Print Service Module

Location: `frontend/services/printService.ts`

Single public entry point:

```ts
export async function printGanttPanel(options: PrintGanttOptions): Promise<void>
```

Internal flow:

```
printGanttPanel(options)
  ├── 1. Validate browser environment (window/document)
  ├── 2. Read user-selected options (orientation, grouping, legend, threshold)
  ├── 3. Decide capture mode: image (count <= threshold) or table fallback
  ├── 4. If image mode:
  │     ├── Locate the GanttPanel root element via data attribute
  │     ├── Apply print-friendly color overrides before capture
  │     ├── Capture the Gantt content area as PNG using modern-screenshot
  │     └── Restore original colors after capture
  ├── 5. Build print HTML document
  │     ├── Metadata header (project name, dates, view name, timestamp)
  │     ├── Captured Gantt image or HTML table
  │     ├── Legend section (if includeLegend)
  │     ├── Grouped-by line (if includeGrouping)
  │     └── Print CSS (@page with selected orientation, typography, image sizing)
  ├── 6. Create hidden iframe, write HTML, call print()
  └── 7. Clean up iframe on close
```

### 3. Capture Strategy

The GanttPanel contains complex DOM: SVG relationship arrows, absolutely-positioned virtualized rows, sticky summaries, and CSS gradients. Rather than trying to clone and re-style this DOM, we capture the visible content area as a single PNG image using `modern-screenshot` (`domToPng`).

**Why image capture over DOM cloning:**

- Virtualized rows are only partially in the DOM — a screenshot captures the visual state faithfully
- SVG arrows overlaid on positioned elements are hard to clone correctly
- Single image avoids CSS conflicts in the print iframe
- Proven approach for chart-heavy print scenarios per the print service guide

**Capture target:** The `<div className="min-w-[500px] flex flex-col flex-1 ...">` element that wraps the timeline header + virtualized body. This will be identified via a `data-gantt-printable` attribute added to that div.

**Print-friendly color override before capture:**

- Temporarily swap the dark background to white
- Timeline text from gray-400/gray-500 to black
- Bar text from white to black
- Grid lines from dark-600 to gray-300
- Restore all original values after capture (using `ElementColorState[]` pattern from the guide)

**Pixel ratio:** 2x for quality on retina displays while keeping memory reasonable.

**Scroll handling:** Before capture, temporarily expand the scrollable container to its full virtual height so all rows are rendered (disable virtualization momentarily), capture, then restore scroll/virtualization.

### 4. Print HTML Document

The print document is a standalone HTML string injected into a hidden iframe:

```html
<!DOCTYPE html>
<html>
<head>
  <style>
    @page {
      size: A4 {orientation}; /* 'landscape' or 'portrait' from user selection */
      margin: 1.5cm;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      color: #111;
      margin: 0;
      padding: 0;
    }
    .header {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid #ccc;
      padding-bottom: 8px;
      margin-bottom: 12px;
      font-size: 11px;
    }
    .gantt-image {
      width: 100%;
      height: auto;
      page-break-inside: avoid;
    }
    .legend {
      margin-top: 8px;
      font-size: 9px;
      color: #555;
      border-top: 1px solid #ccc;
      padding-top: 6px;
    }
    .footer {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      text-align: center;
      font-size: 8px;
      color: #999;
      padding: 4px 0;
    }
  </style>
</head>
<body>
  <div class="header">
    <div><strong>{projectName}</strong></div>
    <div>{viewName} | {itemCount} activities | Printed {timestamp}</div>
  </div>
  <img class="gantt-image" src="{dataUrl}" />
  <!-- Conditionally included based on user options -->
  {legendHtml?}
  {groupingHtml?}
  <div class="footer">Generated by P6 Assist</div>
</body>
</html>
```

**Page orientation:** User-selected via the Print Options Popup. Default is landscape — Gantt charts are wider than tall. The `@page { size }` rule is set dynamically based on the user's choice.

### 5. Print Transport

Hidden iframe approach (per guide recommendation):

```ts
async function printHtmlDocument(html: string): Promise<void> {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.left = '-9999px';
  iframe.style.width = '0';
  iframe.style.height = '0';
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!doc) { throw new Error('Cannot access iframe document'); }

  doc.open();
  doc.write(html);
  doc.close();

  await new Promise<void>((resolve) => {
    iframe.onload = () => {
      iframe.contentWindow?.print();
      resolve();
    };
  });

  // Clean up after a delay to let the print dialog close
  setTimeout(() => iframe.remove(), 1000);
}
```

### 6. Fallback Path

If `modern-screenshot` capture fails (e.g., CORS issues with fonts, memory on very large charts), fall back to a text-based print:

- Extract activity data from the `GanttChartData` prop
- Render a simple HTML table: Activity ID | Name | Start | Finish | Duration | Float | Status
- Print via the same iframe transport

This ensures the user always gets some output.

### 7. Data Attribute for Print Targeting

Add a `data-gantt-printable` attribute to the main content area in GanttPanel:

```tsx
<div
  data-gantt-printable
  className="min-w-[500px] flex flex-col flex-1 overflow-hidden relative"
>
```

The print service locates this element without coupling to internal class names.

---

## Types

```ts
// frontend/services/printService.types.ts

/** User-facing options selected in the Print Options Popup */
export interface PrintUserOptions {
  orientation: 'landscape' | 'portrait';
  includeGrouping: boolean;
  includeLegend: boolean;
  /** Activity count above which image capture is skipped in favor of table */
  imageThreshold: number;
}

/** Full options passed to the print service (popup selections + panel metadata) */
export interface PrintGanttOptions {
  /** Stable selector or direct ref to the gantt content area */
  panelElement?: HTMLElement;
  /** Project metadata for the print header */
  projectName: string;
  viewName?: string;
  itemCount: number;
  projectStart?: string;
  projectFinish?: string;
  /** Grouping label (e.g. "WBS") — printed only if includeGrouping is true */
  grouping?: string | null;
  /** User-selected print options from the popup */
  userOptions: PrintUserOptions;
  /** Fallback data for text-only / table print path */
  fallbackItems?: PrintFallbackItem[];
}

export interface PrintFallbackItem {
  activityId: string;
  name: string;
  start: string;
  finish: string;
  duration: string;
  totalFloat: string;
  status: string;
}

export interface ElementColorState {
  element: Element;
  attribute: string;
  originalValue: string | null;
}
```

---

## Dependencies

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| `modern-screenshot` | ^4.6 | DOM-to-PNG capture for the Gantt area (actively maintained fork of html-to-image with web worker support, smaller bundle) | ~9 KB gzipped |

`lucide-react` already includes the `Printer` icon — no new icon library needed.

No other new dependencies. `dompurify` is not required because we are building the print HTML ourselves (no user-supplied HTML/markdown in this flow).

---

## Integration with GanttPanel

The `GanttPanel` component will:

1. Add `data-gantt-printable` to the chart content wrapper
2. Manage `printPopupOpen` state (`useState<boolean>(false)`)
3. Pass `onPrintClick={() => setPrintPopupOpen(true)}` to the `Legend` component
4. Render `<PrintOptionsPopup>` conditionally when `printPopupOpen` is true
5. The popup's `onPrint` callback receives `PrintUserOptions` and invokes `printGanttPanel()`:

```tsx
const [printPopupOpen, setPrintPopupOpen] = useState(false);
const printButtonRef = useRef<HTMLButtonElement>(null);

const handlePrint = async (userOptions: PrintUserOptions) => {
  setPrintPopupOpen(false);

  const panelEl = document.querySelector('[data-gantt-printable]') as HTMLElement | null;
  if (!panelEl) return;

  await printGanttPanel({
    panelElement: panelEl,
    projectName: data.project_name ?? 'Schedule',
    viewName: activeView?.view_name,
    itemCount: visibleItems.length,
    projectStart: data.project_start,
    projectFinish: data.project_finish,
    grouping: data.grouping,
    userOptions,
    fallbackItems: visibleItems.map((item) => ({
      activityId: item.s_item_id,
      name: item.s_item,
      start: item.start,
      finish: item.finish,
      duration: `${item.working_days}d`,
      totalFloat: `${item.total_float.toFixed(1)}d`,
      status: item.status,
    })),
  });
};
```

---

## Scroll / Virtualization Handling

The GanttPanel uses `@tanstack/react-virtual` — only ~20-30 rows exist in the DOM at any time. To capture all activities:

1. Before capture: temporarily set the scroll container height to `rowVirtualizer.getTotalSize()` and force all rows to render (set overscan to `Infinity` or equivalent)
2. Capture the fully-expanded element
3. After capture: restore original container height and overscan

This is the trickiest part of the implementation. An alternative approach if this proves fragile:

- Use the **fallback table path** for schedules above the user-configured threshold (default: 100 activities)
- Use image capture only for reasonably-sized charts (at or below threshold)
- The threshold is configurable per session via the Print Options Popup

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Panel has 0 activities | Disable print icon (gray out, no onClick) |
| Activities > threshold | Fall back to tabular print (threshold configurable, default 100) |
| Relationship arrows visible | Captured in the image naturally (SVG overlay) |
| Baseline bars visible | Captured in the image naturally |
| Collapsed summary groups | Print what is visible (collapsed state) |
| Panel being resized | Disable print while drag is active |
| View loading in progress | Disable print icon during loading |

---

## Effort Estimate

| Task | Estimate |
|------|----------|
| `printService.ts` + types | 3-4 hours |
| `PrintOptionsPopup.tsx` component | 2-3 hours |
| Color override / restore helpers | 1-2 hours |
| Scroll expansion for full capture | 2-3 hours |
| Print HTML template + CSS (dynamic orientation) | 1-2 hours |
| GanttPanel integration (icon + popup state + wiring) | 1-2 hours |
| Fallback text path | 1 hour |
| Testing (manual: Chrome, Safari, multi-size datasets, popup UX) | 2-3 hours |
| **Total** | **~13-20 hours** |

---

## Testing Plan

**Manual testing (required before merge):**

- Print a Gantt with 10, 50, 200, 500+ activities
- Print with relationship arrows on/off
- Print with baseline overlay on/off
- Print with collapsed summary groups
- Print with optional columns (start, finish, float) visible
- Verify landscape and portrait A4 layout in Chrome and Safari print preview
- Toggle include legend on/off and verify output
- Toggle include grouped-by on/off and verify output
- Change image threshold and verify table fallback triggers at correct count
- Verify popup opens/closes correctly (icon click, cancel, outside click)
- Verify fallback triggers correctly (simulate capture failure)
- Verify iframe cleanup after print dialog close/cancel

**Automated tests (unit):**

- `buildPrintableHtml` produces valid HTML with correct metadata
- `buildPrintableHtml` respects orientation, includeLegend, includeGrouping flags
- `applyPrintFriendlyColors` / `restoreOriginalColors` round-trips correctly
- Fallback table generation includes all items
- Print icon disabled states (0 items, loading)
- Popup default values match spec (landscape, legend on, grouping on, threshold 100)

---

## Resolved Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Activity threshold for image vs. table fallback | Default 100. **Configurable** in the Print Options Popup per session |
| 2 | Page orientation | Default **landscape**. User selects in popup before printing |
| 3 | Grouped-by footer line | **User-selectable** in popup (checkbox, default on if grouping exists) |
| 4 | Keyboard shortcut | **No** — icon-only trigger |

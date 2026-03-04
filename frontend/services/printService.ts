/**
 * Print Service — @media print approach
 *
 * Uses the browser's native print engine to render the Gantt panel
 * exactly as displayed.  Injects @media print CSS rules that:
 *   1. Hide everything on the page except the Gantt panel
 *   2. Override dark-theme colors to print-friendly light theme
 *   3. Inject a print-only header with project metadata
 *
 * The caller (GanttPanel) is responsible for expanding the virtualizer
 * (set overscan to total item count) BEFORE calling `executePrint()`,
 * so all rows are in the DOM when the browser renders the print view.
 *
 * Flow: GanttPanel sets isPrinting=true -> virtualizer renders all rows
 *       -> useEffect calls executePrint() -> window.print() -> cleanup
 */

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface PrintMetadata {
  projectName: string;
  versionLabel?: string;
  viewName?: string;
  itemCount: number;
  projectStart?: string;
  projectFinish?: string;
  grouping?: string | null;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Inject print styles + header overlay, call window.print(), then clean up.
 * Always prints in landscape orientation.
 */
export async function executePrint(
  metadata: PrintMetadata,
): Promise<void> {
  if (typeof window === 'undefined') return;

  const cleanupFns: Array<() => void> = [];

  try {
    // 1. Mark ancestor chain so CSS can isolate the Gantt panel
    cleanupFns.push(markAncestorChain());

    // 2. Inject print-only header overlay (before measuring)
    cleanupFns.push(injectPrintHeader(metadata));

    // 3. Measure the panel's actual screen dimensions so we can
    //    create a custom page size that preserves proportions exactly.
    const panel = document.querySelector('[data-gantt-panel-root]');
    const rect = panel?.getBoundingClientRect();
    const panelWidthPx = rect ? rect.width : 1200;
    const panelHeightPx = rect ? rect.height : 800;

    // 4. Inject @media print stylesheet with custom page size
    cleanupFns.push(injectPrintStylesheet(panelWidthPx, panelHeightPx));

    // 5. Let the browser settle injected elements + expanded rows
    await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, 100));

    // 6. Print
    window.print();
  } finally {
    // 7. Clean up all injected elements (in reverse order)
    for (const fn of cleanupFns.reverse()) {
      try { fn(); } catch { /* ignore */ }
    }
  }
}

// ---------------------------------------------------------------------------
// Ancestor-chain marking (isolates Gantt panel from the rest of the page)
// ---------------------------------------------------------------------------

/**
 * Walk up the DOM from [data-gantt-panel-root] to <body>, marking each
 * ancestor with `data-print-ancestor`.  This lets the CSS hide everything
 * that isn't on the direct path to the Gantt panel.
 *
 * Returns a cleanup function that removes the attributes.
 */
function markAncestorChain(): () => void {
  const panel = document.querySelector('[data-gantt-panel-root]');
  if (!panel) return () => {};

  const marked: Element[] = [];
  let current = panel.parentElement;

  while (current && current !== document.body && current !== document.documentElement) {
    current.setAttribute('data-print-ancestor', '');
    marked.push(current);
    current = current.parentElement;
  }

  return () => {
    for (const el of marked) {
      el.removeAttribute('data-print-ancestor');
    }
  };
}

// ---------------------------------------------------------------------------
// @media print stylesheet
// ---------------------------------------------------------------------------

const PX_TO_MM = 25.4 / 96; // 1px at 96dpi = 0.2646mm
const PAGE_MARGIN_MM = 10; // 1cm margins

function buildPrintCSS(panelWidthPx: number, panelHeightPx: number): string {
  // Convert panel dimensions to mm and add margins for the page size
  const pageWidthMm = Math.ceil(panelWidthPx * PX_TO_MM) + PAGE_MARGIN_MM * 2;
  const pageHeightMm = Math.ceil(panelHeightPx * PX_TO_MM) + PAGE_MARGIN_MM * 2;

  return `
@media print {
  /* ---- Page setup: custom size matching panel proportions ---- */
  @page {
    size: ${pageWidthMm}mm ${pageHeightMm}mm;
    margin: ${PAGE_MARGIN_MM}mm;
  }

  /* ---- Hide EVERYTHING by default ---- */
  body * {
    visibility: hidden !important;
  }

  /* ---- White page background ---- */
  html, body {
    background: #ffffff !important;
    background-color: #ffffff !important;
  }

  /* ---- Show ancestor chain (structure only, no content) ---- */
  [data-print-ancestor] {
    visibility: visible !important;
    display: block !important;
    position: static !important;
    overflow: visible !important;
    width: 100% !important;
    height: auto !important;
    max-height: none !important;
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    background-color: transparent !important;
  }

  /* ---- Hide all siblings of ancestor-chain elements ---- */
  [data-print-ancestor] > *:not([data-print-ancestor]):not([data-gantt-panel-root]) {
    display: none !important;
  }

  /* ---- Show the Gantt panel and ALL its descendants ---- */
  [data-gantt-panel-root],
  [data-gantt-panel-root] * {
    visibility: visible !important;
  }

  /* ---- Panel layout: remove fixed positioning, fill page ---- */
  [data-gantt-panel-root] {
    display: flex !important;
    flex-direction: column !important;
    position: static !important;
    top: auto !important;
    right: auto !important;
    bottom: auto !important;
    left: auto !important;
    width: 100% !important;
    height: auto !important;
    max-height: none !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    overflow: visible !important;
    z-index: auto !important;
    margin: 0 !important;
    padding: 0 !important;
  }

  /* ---- Override dark backgrounds to white ---- */
  [data-gantt-panel-root],
  [data-gantt-panel-root] > div,
  [data-gantt-panel-root] [class*="bg-[#0d1117]"],
  [data-gantt-panel-root] [class*="bg-dark"],
  [data-gantt-printable],
  [data-gantt-printable] [class*="bg-[#0d1117]"],
  [data-gantt-printable] [class*="bg-dark"] {
    background-color: #ffffff !important;
    background: #ffffff !important;
  }

  /* ---- Dark text on white ---- */
  [data-gantt-panel-root],
  [data-gantt-panel-root] h2,
  [data-gantt-panel-root] span,
  [data-gantt-panel-root] div,
  [data-gantt-panel-root] p,
  [data-gantt-panel-root] button,
  [data-gantt-panel-root] [class*="text-gray"],
  [data-gantt-panel-root] [class*="text-white"],
  [data-gantt-panel-root] [class*="text-blue"] {
    color: #111111 !important;
  }

  /* ---- Borders: light gray ---- */
  [data-gantt-panel-root] [class*="border-dark"] {
    border-color: #dddddd !important;
  }

  /* ---- Remove overflow hidden so all rows show ---- */
  [data-gantt-panel-root] [class*="overflow-hidden"],
  [data-gantt-panel-root] [class*="overflow-auto"] {
    overflow: visible !important;
  }

  /* ---- Disable flex-grow on content wrapper so it doesn't fill empty space ---- */
  [data-gantt-panel-root] > .flex-1 {
    flex: none !important;
  }

  /* ---- Let the content wrapper grow with content ---- */
  [data-gantt-printable] {
    flex: none !important;
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
  }

  /* ---- Scroll container: auto height ---- */
  [data-gantt-printable] > div:last-child {
    flex: none !important;
    height: auto !important;
    overflow: visible !important;
  }

  /* ---- Hide UI-only elements (header, toolbar, resize handles, close, sticky summaries) ---- */
  [data-gantt-panel-root] [data-gantt-no-print] {
    display: none !important;
  }
  [data-gantt-panel-root] [aria-label="Close panel"],
  [data-gantt-panel-root] [aria-label="Resize activity column"],
  [data-gantt-panel-root] [class*="cursor-col-resize"],
  [data-gantt-panel-root] button[aria-label="Print schedule"] {
    display: none !important;
  }

  /* ---- Print overlays: visible only in print ---- */
  [data-print-overlay] {
    display: block !important;
    visibility: visible !important;
  }

  /* ---- Ensure bar text is readable ---- */
  [data-gantt-printable] [class*="text-white"] {
    color: #ffffff !important;  /* bar labels stay white on colored bars */
  }

  /* But activity names in the left column should be dark */
  [data-gantt-printable] [class*="text-white"]:not([style*="background"]) {
    color: #111111 !important;
  }

  /* ---- Color-adjust for bar fills ---- */
  * {
    print-color-adjust: exact !important;
    -webkit-print-color-adjust: exact !important;
  }

  /* ---- No page break inside the chart area ---- */
  [data-gantt-printable] {
    page-break-inside: avoid;
  }
}

/* Print overlays: hidden on screen */
[data-print-overlay] {
  display: none;
}
`;
}

function injectPrintStylesheet(panelWidthPx: number, panelHeightPx: number): () => void {
  const style = document.createElement('style');
  style.setAttribute('data-print-service', 'stylesheet');
  style.textContent = buildPrintCSS(panelWidthPx, panelHeightPx);
  document.head.appendChild(style);
  return () => style.remove();
}

// ---------------------------------------------------------------------------
// Print-only header overlay
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTimestamp(): string {
  const now = new Date();
  return now.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function injectPrintHeader(metadata: PrintMetadata): () => void {
  const panel = document.querySelector('[data-gantt-panel-root]');
  if (!panel) return () => {};

  const titleParts: string[] = [escapeHtml(metadata.projectName)];
  if (metadata.versionLabel) titleParts.push(escapeHtml(metadata.versionLabel));
  const titleText = titleParts.join(' — ');

  const metaParts: string[] = [];
  if (metadata.viewName) metaParts.push(escapeHtml(metadata.viewName));
  metaParts.push(
    `${metadata.itemCount} activit${metadata.itemCount !== 1 ? 'ies' : 'y'}`,
  );
  if (metadata.projectStart) metaParts.push(`Start: ${escapeHtml(metadata.projectStart)}`);
  if (metadata.projectFinish) metaParts.push(`Finish: ${escapeHtml(metadata.projectFinish)}`);
  metaParts.push(`Printed ${formatTimestamp()}`);

  const header = document.createElement('div');
  header.setAttribute('data-print-overlay', 'header');
  header.style.cssText =
    'display:none; padding:0 0 6px 0; margin-bottom:8px; border-bottom:1px solid #ccc; font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
  header.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:baseline;">
      <div style="font-size:14px; font-weight:600; color:#111;">${titleText}</div>
      <div style="font-size:9px; color:#555; text-align:right;">${metaParts.join(' | ')}</div>
    </div>
  `;

  // Insert as first child of the panel
  panel.prepend(header);
  return () => header.remove();
}
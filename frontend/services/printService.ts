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

    // Measure the heights of the two bands that must repeat on every
    // printed page so the @page top margin reserves the right amount of
    // space. The overlay is display:none on screen, so we briefly render
    // it off-screen with the panel's print width to get an accurate
    // measurement (including its padding + borders + cloned timeline).
    const headerEl = document.querySelector(
      '[data-print-overlay="header"]',
    ) as HTMLElement | null;
    const infoBarEl = document.querySelector(
      '[data-print-overlay="header"] [data-print-info-bar]',
    ) as HTMLElement | null;
    const timelineCloneEl = document.querySelector(
      '[data-print-overlay="header"] [data-print-timeline-clone]',
    ) as HTMLElement | null;

    let overlayHeightPx = 0;
    if (headerEl) {
      const prevDisplay = headerEl.style.display;
      const prevPosition = headerEl.style.position;
      const prevVisibility = headerEl.style.visibility;
      const prevLeft = headerEl.style.left;
      const prevTop = headerEl.style.top;
      const prevWidth = headerEl.style.width;
      headerEl.style.display = 'block';
      headerEl.style.position = 'absolute';
      headerEl.style.visibility = 'hidden';
      headerEl.style.left = '-10000px';
      headerEl.style.top = '0';
      headerEl.style.width = `${panelWidthPx}px`;
      overlayHeightPx = headerEl.getBoundingClientRect().height;
      headerEl.style.display = prevDisplay;
      headerEl.style.position = prevPosition;
      headerEl.style.visibility = prevVisibility;
      headerEl.style.left = prevLeft;
      headerEl.style.top = prevTop;
      headerEl.style.width = prevWidth;
    }
    // Fallback: sum of measurable children + a small safety pad.
    if (!overlayHeightPx) {
      const infoH = infoBarEl?.getBoundingClientRect().height ?? 32;
      const tlH = timelineCloneEl?.getBoundingClientRect().height ?? 56;
      overlayHeightPx = infoH + tlH;
    }
    // Split between the two bands purely for the CSS variable below; the
    // page top margin uses the total.
    const printHeaderPx = infoBarEl?.getBoundingClientRect().height ?? 32;
    const timelineHeaderPx = Math.max(0, overlayHeightPx - printHeaderPx);

    // 4. Inject @media print stylesheet with custom page size
    cleanupFns.push(
      injectPrintStylesheet(
        panelWidthPx,
        panelHeightPx,
        printHeaderPx,
        timelineHeaderPx,
      ),
    );

    // 5. Reflow virtualized rows from absolute -> normal flow so that
    //    page-break-inside actually works (Chrome ignores it on
    //    absolutely-positioned children, which is why rows that fall in
    //    the top margin band on subsequent pages were being clipped).
    cleanupFns.push(reflowVirtualizedRows());

    // 6. Let the browser settle injected elements + expanded rows
    await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, 100));

    // 7. Print
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

function buildPrintCSS(
  panelWidthPx: number,
  panelHeightPx: number,
  printHeaderPx: number,
  timelineHeaderPx: number,
): string {
  // Convert panel dimensions to mm.
  const panelWidthMm = Math.ceil(panelWidthPx * PX_TO_MM);
  const panelHeightMm = Math.ceil(panelHeightPx * PX_TO_MM);

  // Reserve room at the top of every page for the two repeating bands
  // (project info header + timeline / column header). Both are pinned via
  // position:fixed so they appear on every printed page, and the @page
  // top margin keeps row content from sliding under them. A small safety
  // pad accounts for px->mm rounding and font/line-height drift between
  // screen and print rasterization.
  const printHeaderMm = Math.ceil(printHeaderPx * PX_TO_MM);
  const timelineHeaderMm = Math.ceil(timelineHeaderPx * PX_TO_MM);
  const topReserveMm = printHeaderMm + timelineHeaderMm + 5;

  const pageWidthMm = panelWidthMm + PAGE_MARGIN_MM * 2;
  const pageHeightMm = panelHeightMm + topReserveMm + PAGE_MARGIN_MM;

  return `
@media print {
  /* ---- Page setup: custom size matching panel proportions ---- */
  @page {
    size: ${pageWidthMm}mm ${pageHeightMm}mm;
    margin: ${topReserveMm}mm ${PAGE_MARGIN_MM}mm ${PAGE_MARGIN_MM}mm ${PAGE_MARGIN_MM}mm;
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
  [data-gantt-panel-root] [aria-label="Resize activity name column"],
  [data-gantt-panel-root] [class*="cursor-col-resize"],
  [data-gantt-panel-root] button[aria-label="Print schedule"] {
    display: none !important;
  }

  /* ---- Print overlays: visible only in print ---- */
  [data-print-overlay] {
    display: block !important;
    visibility: visible !important;
  }

  /* ---- Project info header + cloned timeline/column header: pinned to the
          top of every printed page via position:fixed (Chrome repeats fixed
          elements per page). The overlay is built once and includes both
          bands so they render together on every page. ---- */
  [data-print-overlay="header"] {
    position: fixed !important;
    top: 0 !important;
    left: ${PAGE_MARGIN_MM}mm !important;
    right: ${PAGE_MARGIN_MM}mm !important;
    margin: 0 !important;
    padding: 0 !important;
    background: #ffffff !important;
    z-index: 9999 !important;
  }
  [data-print-overlay="header"] [data-print-info-bar] {
    padding: 2mm 0 !important;
    border-bottom: 1px solid #cccccc !important;
  }
  [data-print-overlay="header"] [data-print-timeline-clone] {
    padding-top: 1mm !important;
    border-bottom: 1px solid #dddddd !important;
  }
  /* Clone uses the same dark Tailwind classes; force light theme inside it. */
  [data-print-overlay="header"] [data-print-timeline-clone],
  [data-print-overlay="header"] [data-print-timeline-clone] * {
    background-color: #ffffff !important;
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #dddddd !important;
  }
  [data-print-overlay="header"] [data-print-timeline-clone] [class*="mb-4"] {
    margin-bottom: 0 !important;
  }

  /* ---- Hide the original on-screen sticky timeline header in print
          (the cloned copy inside the fixed overlay replaces it).  ---- */
  [data-gantt-printable] > div.sticky {
    display: none !important;
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

  /* ---- Hide the relationship-arrows overlay during print: it is
          absolutely positioned against the virtualizer canvas using the
          original row Y coordinates, so it cannot stay in sync once the
          rows are reflowed for pagination. ---- */
  [data-gantt-printable] svg,
  [data-gantt-printable] [class*="absolute top-0 bottom-0"]:not([data-gantt-row]) {
    display: none !important;
  }

  /* ---- Allow page breaks between rows but never split a single row.
          The rows have been reflowed (see reflowVirtualizedRows in
          executePrint) from absolute to normal flow so that this rule
          actually applies — Chrome does not honor page-break-inside on
          absolutely positioned children. ---- */
  [data-gantt-row] {
    page-break-inside: avoid;
    break-inside: avoid;
  }
}

/* Print overlays: hidden on screen */
[data-print-overlay] {
  display: none;
}
`;
}

function injectPrintStylesheet(
  panelWidthPx: number,
  panelHeightPx: number,
  printHeaderPx: number,
  timelineHeaderPx: number,
): () => void {
  const style = document.createElement('style');
  style.setAttribute('data-print-service', 'stylesheet');
  style.textContent = buildPrintCSS(
    panelWidthPx,
    panelHeightPx,
    printHeaderPx,
    timelineHeaderPx,
  );
  document.head.appendChild(style);
  return () => style.remove();
}

// ---------------------------------------------------------------------------
// Reflow virtualized rows for paginated print
// ---------------------------------------------------------------------------

/**
 * The Gantt's TanStack virtualizer renders every row as
 *   position: absolute; top: 0; left: 0; transform: translateY(<n>px)
 * over a tall canvas. Chrome's print engine does NOT honor
 * page-break-inside on absolutely-positioned children, so any row whose
 * pixel band intersects the @page top margin on subsequent pages is
 * silently clipped (visually: the first activities on every page after
 * the first are missing).
 *
 * At print time we walk every absolute row, capture its inline style,
 * rewrite it to flow layout, and tag it with [data-gantt-row] so the
 * print CSS can apply page-break-inside: avoid. The wrapper canvas is
 * also sized to auto so the parent doesn't enforce a fixed height.
 *
 * Returns a cleanup function that restores all original inline styles.
 */
function reflowVirtualizedRows(): () => void {
  const printable = document.querySelector('[data-gantt-printable]');
  if (!printable) return () => {};

  type Restore = { el: HTMLElement; style: string | null; tagged: boolean };
  const restores: Restore[] = [];

  // Collect row wrappers + virtualizer canvas (the relative-positioned
  // sized container) and the parentRef scroll container.
  const candidates = printable.querySelectorAll<HTMLElement>('div[style]');
  candidates.forEach((el) => {
    const cs = el.style;
    const isAbsoluteRow =
      cs.position === 'absolute' && cs.transform.includes('translateY');
    const isVirtualCanvas =
      cs.position === 'relative'
      && cs.height.endsWith('px')
      && (cs.width === '100%' || cs.width.endsWith('px'));

    if (isAbsoluteRow) {
      const original = el.getAttribute('style');
      restores.push({ el, style: original, tagged: true });
      el.style.position = 'static';
      el.style.transform = 'none';
      el.style.top = 'auto';
      el.style.left = 'auto';
      // Width/height/transform original values are kept implicitly via
      // the saved style string for restore.
      el.setAttribute('data-gantt-row', '');
    } else if (isVirtualCanvas) {
      const original = el.getAttribute('style');
      restores.push({ el, style: original, tagged: false });
      el.style.height = 'auto';
      el.style.minHeight = '0';
    }
  });

  // Also relax the scroll container so it expands to fit all rows in flow.
  const scrollContainers = printable.querySelectorAll<HTMLElement>('.overflow-auto');
  scrollContainers.forEach((el) => {
    restores.push({ el, style: el.getAttribute('style'), tagged: false });
    el.style.overflow = 'visible';
    el.style.height = 'auto';
  });

  return () => {
    for (const r of restores) {
      if (r.style === null) {
        r.el.removeAttribute('style');
      } else {
        r.el.setAttribute('style', r.style);
      }
      if (r.tagged) r.el.removeAttribute('data-gantt-row');
    }
  };
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
    'display:none; font-family:-apple-system,BlinkMacSystemFont,sans-serif;';

  // Project info bar
  const infoBar = document.createElement('div');
  infoBar.setAttribute('data-print-info-bar', '');
  infoBar.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:baseline;">
      <div style="font-size:14px; font-weight:600; color:#111;">${titleText}</div>
      <div style="font-size:9px; color:#555; text-align:right;">${metaParts.join(' | ')}</div>
    </div>
  `;
  header.appendChild(infoBar);

  // Clone the on-screen timeline / column header so it repeats on every
  // printed page as part of this fixed overlay (Chrome reliably repeats a
  // single fixed element with baked-in content; cloning sidesteps quirks
  // with re-laying out flex children of repeated fixed elements).
  const timelineHeader = document.querySelector(
    '[data-gantt-printable] > div.sticky',
  ) as HTMLElement | null;
  if (timelineHeader) {
    const clone = timelineHeader.cloneNode(true) as HTMLElement;
    clone.setAttribute('data-print-timeline-clone', '');
    // Strip on-screen sticky behavior on the clone itself.
    clone.style.position = 'static';
    clone.style.top = 'auto';
    clone.style.zIndex = 'auto';
    header.appendChild(clone);
  }

  // Insert as first child of the panel

  // Insert as first child of the panel
  panel.prepend(header);
  return () => header.remove();
}
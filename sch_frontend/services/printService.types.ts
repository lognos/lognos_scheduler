/**
 * Print Service Types
 *
 * Strict interfaces for the Gantt panel print flow.
 */

/** User-facing options selected in the Print Options Popup. */
export interface PrintUserOptions {
  orientation: 'landscape' | 'portrait';
  includeGrouping: boolean;
  includeLegend: boolean;
}

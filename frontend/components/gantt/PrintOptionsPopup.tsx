/**
 * PrintOptionsPopup
 *
 * Styled popup anchored above the print icon in the Gantt panel legend.
 * Lets the user configure orientation and included sections before
 * triggering the native browser print.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { Portal } from '@/components/Portal';
import type { PrintUserOptions } from '@/services/printService.types';

interface PrintOptionsPopupProps {
  open: boolean;
  onClose: () => void;
  onPrint: (options: PrintUserOptions) => void;
  hasGrouping: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
}

export function PrintOptionsPopup({
  open,
  onClose,
  onPrint,
  hasGrouping,
  anchorRef,
}: PrintOptionsPopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);

  const [orientation, setOrientation] = useState<'landscape' | 'portrait'>('landscape');
  const [includeGrouping, setIncludeGrouping] = useState(hasGrouping);
  const [includeLegend, setIncludeLegend] = useState(true);

  // Keep grouping default in sync with prop
  useEffect(() => {
    setIncludeGrouping(hasGrouping);
  }, [hasGrouping]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;

    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        popupRef.current &&
        !popupRef.current.contains(target) &&
        anchorRef.current &&
        !anchorRef.current.contains(target)
      ) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open, onClose, anchorRef]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  const handlePrint = useCallback(() => {
    onPrint({
      orientation,
      includeGrouping,
      includeLegend,
    });
  }, [onPrint, orientation, includeGrouping, includeLegend]);

  if (!open) return null;

  // Position above the anchor button
  const anchorRect = anchorRef.current?.getBoundingClientRect();
  const style: React.CSSProperties = anchorRect
    ? {
        position: 'fixed',
        bottom: `${window.innerHeight - anchorRect.top + 8}px`,
        right: `${window.innerWidth - anchorRect.right}px`,
        zIndex: 9999,
      }
    : { position: 'fixed', bottom: '80px', right: '32px', zIndex: 9999 };

  return (
    <Portal>
      <div ref={popupRef} style={style} className="w-72 rounded-lg border border-dark-600 bg-[#0d1117] shadow-2xl text-xs text-gray-200">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-dark-700">
          <span className="text-sm font-medium text-white">Print Schedule</span>
          <button
            type="button"
            onClick={onClose}
            className="p-0.5 hover:bg-dark-700 rounded transition-colors"
            aria-label="Close print options"
          >
            <X className="h-3.5 w-3.5 text-gray-400 hover:text-white" />
          </button>
        </div>

        {/* Body */}
        <div className="px-4 py-3 space-y-4">
          {/* Orientation */}
          <fieldset>
            <legend className="text-gray-400 mb-1.5 font-medium">Orientation</legend>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="orientation"
                  value="landscape"
                  checked={orientation === 'landscape'}
                  onChange={() => setOrientation('landscape')}
                  className="accent-blue-500"
                />
                <span>Landscape</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="orientation"
                  value="portrait"
                  checked={orientation === 'portrait'}
                  onChange={() => setOrientation('portrait')}
                  className="accent-blue-500"
                />
                <span>Portrait</span>
              </label>
            </div>
          </fieldset>

          {/* Include checkboxes */}
          <fieldset>
            <legend className="text-gray-400 mb-1.5 font-medium">Include</legend>
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeLegend}
                  onChange={(e) => setIncludeLegend(e.target.checked)}
                  className="accent-blue-500"
                />
                <span>Legend</span>
              </label>
              <label className={`flex items-center gap-1.5 ${hasGrouping ? 'cursor-pointer' : 'opacity-40 cursor-not-allowed'}`}>
                <input
                  type="checkbox"
                  checked={includeGrouping}
                  onChange={(e) => setIncludeGrouping(e.target.checked)}
                  disabled={!hasGrouping}
                  className="accent-blue-500"
                />
                <span>Grouped-by label</span>
              </label>
            </div>
          </fieldset>
        </div>

        {/* Footer buttons */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-dark-700">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded border border-dark-600 text-gray-300 hover:bg-dark-700 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handlePrint}
            className="px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-500 transition-colors font-medium"
          >
            Print
          </button>
        </div>
      </div>
    </Portal>
  );
}

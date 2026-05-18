/**
 * useActivityUpdates Hook
 *
 * Builds a lookup map from activity s_item_id to its update logs.
 * Returns the map and a boolean indicating whether any updates exist.
 */

import { useMemo } from 'react';
import { ActivityUpdate } from '@/types/schedule';

export interface ActivityUpdatesMap {
  /** Map from s_item_id to array of updates (most recent first) */
  byActivity: Map<string, ActivityUpdate[]>;
  /** Whether any updates exist */
  hasUpdates: boolean;
}

export function useActivityUpdates(
  updates?: ActivityUpdate[]
): ActivityUpdatesMap {
  return useMemo(() => {
    if (!updates || updates.length === 0) {
      return { byActivity: new Map(), hasUpdates: false };
    }

    const byActivity = new Map<string, ActivityUpdate[]>();
    for (const update of updates) {
      const existing = byActivity.get(update.s_item_id);
      if (existing) {
        existing.push(update);
      } else {
        byActivity.set(update.s_item_id, [update]);
      }
    }

    return { byActivity, hasUpdates: true };
  }, [updates]);
}

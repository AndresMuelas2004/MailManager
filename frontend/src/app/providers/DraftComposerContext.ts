import { createContext, useContext } from 'react';

import type { DraftOut } from '../../api/types/dto';

export type DraftComposerContextValue = {
  openForNewEmail: () => void;
  openForNewDraft: (args?: { accountId?: string }) => void;
  openForEditDraft: (draft: DraftOut) => void;
  setRefreshCallback: (fn: (() => void | Promise<void>) | null) => void;
};

export const DraftComposerContext = createContext<DraftComposerContextValue | null>(null);

export function useDraftComposerContext(): DraftComposerContextValue {
  const ctx = useContext(DraftComposerContext);
  if (!ctx) {
    throw new Error('useDraftComposerContext must be used within a DraftComposerProvider');
  }
  return ctx;
}

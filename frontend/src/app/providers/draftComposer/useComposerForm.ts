import { useCallback, useRef, useState } from 'react';

import type { DraftOut } from '../../../api/types/dto';

export type ComposerSnapshot = {
  accountId: string;
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body: string;
};

export type ComposerFields = ComposerSnapshot;

export type DraftPayload = {
  to_recipients: string[];
  cc_recipients: string[];
  bcc_recipients: string[];
  subject: string;
  body_html: string;
};

export type UseComposerFormReturn = {
  accountId: string;
  setAccountId: (id: string) => void;
  to: string;
  setTo: (v: string) => void;
  cc: string;
  setCc: (v: string) => void;
  bcc: string;
  setBcc: (v: string) => void;
  subject: string;
  setSubject: (v: string) => void;
  body: string;
  setBody: (v: string) => void;
  reset: () => void;
  seedFromDraft: (draft: DraftOut) => void;
  getSnapshot: () => ComposerSnapshot;
  hasSavedSnapshot: () => boolean;
  isDirty: () => boolean;
  hasAnyContent: () => boolean;
  buildDraftPayload: () => DraftPayload;
  parseRecipients: (value: string) => string[];
};

function parseRecipientsImpl(value: string): string[] {
  return value
    .split(',')
    .map((r) => r.trim())
    .filter(Boolean);
}

function joinRecipients(items: string[]): string {
  return items.join(', ');
}

function snapshotsDiffer(a: ComposerSnapshot, b: ComposerSnapshot): boolean {
  return (
    a.to !== b.to ||
    a.cc !== b.cc ||
    a.bcc !== b.bcc ||
    a.subject !== b.subject ||
    a.body !== b.body
  );
}

export default function useComposerForm(): UseComposerFormReturn {
  const [accountId, setAccountId] = useState('');
  const [to, setTo] = useState('');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const snapshotRef = useRef<ComposerSnapshot | null>(null);

  const reset = useCallback(() => {
    setAccountId('');
    setTo('');
    setCc('');
    setBcc('');
    setSubject('');
    setBody('');
    snapshotRef.current = null;
  }, []);

  const seedFromDraft = useCallback((draft: DraftOut) => {
    const initialTo = joinRecipients(draft.to_recipients);
    const initialCc = joinRecipients(draft.cc_recipients);
    const initialBcc = joinRecipients(draft.bcc_recipients);
    setAccountId(draft.account_id);
    setTo(initialTo);
    setCc(initialCc);
    setBcc(initialBcc);
    setSubject(draft.subject);
    setBody(draft.body_html);
    snapshotRef.current = {
      accountId: draft.account_id,
      to: initialTo,
      cc: initialCc,
      bcc: initialBcc,
      subject: draft.subject,
      body: draft.body_html,
    };
  }, []);

  const getSnapshot = useCallback(
    (): ComposerSnapshot => ({ accountId, to, cc, bcc, subject, body }),
    [accountId, to, cc, bcc, subject, body],
  );

  const hasSavedSnapshot = useCallback(() => snapshotRef.current !== null, []);

  const isDirty = useCallback(() => {
    const snap = snapshotRef.current;
    if (!snap) return false;
    return snapshotsDiffer(getSnapshot(), snap);
  }, [getSnapshot]);

  const hasAnyContent = useCallback(
    () =>
      to.trim().length > 0 ||
      cc.trim().length > 0 ||
      bcc.trim().length > 0 ||
      subject.trim().length > 0 ||
      body.trim().length > 0,
    [to, cc, bcc, subject, body],
  );

  const buildDraftPayload = useCallback(
    (): DraftPayload => ({
      to_recipients: parseRecipientsImpl(to),
      cc_recipients: parseRecipientsImpl(cc),
      bcc_recipients: parseRecipientsImpl(bcc),
      subject,
      body_html: body,
    }),
    [to, cc, bcc, subject, body],
  );

  return {
    accountId,
    setAccountId,
    to,
    setTo,
    cc,
    setCc,
    bcc,
    setBcc,
    subject,
    setSubject,
    body,
    setBody,
    reset,
    seedFromDraft,
    getSnapshot,
    hasSavedSnapshot,
    isDirty,
    hasAnyContent,
    buildDraftPayload,
    parseRecipients: parseRecipientsImpl,
  };
}

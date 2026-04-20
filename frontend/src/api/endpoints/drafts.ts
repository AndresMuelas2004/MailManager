import { request } from '../client/http';
import type {
  DraftCreate,
  DraftOut,
  DraftSendOut,
  DraftsSyncResultOut,
  DraftUpdate,
} from '../types/dto';

export function createDraft(
  mailboxId: string,
  accountId: string,
  payload: DraftCreate,
): Promise<DraftOut> {
  return request<DraftOut>(`/mailboxes/${mailboxId}/accounts/${accountId}/drafts`, {
    method: 'POST',
    body: payload,
  });
}

export function updateDraft(
  mailboxId: string,
  accountId: string,
  providerDraftId: string,
  payload: DraftUpdate,
): Promise<DraftOut> {
  return request<DraftOut>(
    `/mailboxes/${mailboxId}/accounts/${accountId}/drafts/${providerDraftId}`,
    { method: 'PATCH', body: payload },
  );
}

export function sendDraft(
  mailboxId: string,
  accountId: string,
  providerDraftId: string,
): Promise<DraftSendOut> {
  return request<DraftSendOut>(
    `/mailboxes/${mailboxId}/accounts/${accountId}/drafts/${providerDraftId}/send`,
    { method: 'POST' },
  );
}

export function listDrafts(mailboxId: string, accountId?: string): Promise<DraftOut[]> {
  const params = accountId ? `?account_id=${accountId}` : '';
  return request<DraftOut[]>(`/mailboxes/${mailboxId}/drafts${params}`);
}

export function syncDrafts(mailboxId: string, accountId?: string): Promise<DraftsSyncResultOut> {
  const params = accountId ? `?account_id=${accountId}` : '';
  return request<DraftsSyncResultOut>(`/mailboxes/${mailboxId}/drafts/sync${params}`, {
    method: 'POST',
  });
}

export function deleteDraft(
  mailboxId: string,
  accountId: string,
  draftId: string,
): Promise<{ status: string }> {
  return request<{ status: string }>(
    `/mailboxes/${mailboxId}/accounts/${accountId}/drafts/${draftId}`,
    { method: 'DELETE' },
  );
}

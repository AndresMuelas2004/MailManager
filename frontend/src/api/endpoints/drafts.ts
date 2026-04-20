import { request } from '../client/http';
import {
  draftListSchema,
  draftOutSchema,
  draftSendOutSchema,
  draftsSyncResultOutSchema,
  statusResponseSchema,
  type DraftCreate,
  type DraftOut,
  type DraftSendOut,
  type DraftUpdate,
  type DraftsSyncResultOut,
  type StatusResponse,
} from '../types/dto';

export function createDraft(
  mailboxId: string,
  accountId: string,
  payload: DraftCreate,
): Promise<DraftOut> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}/drafts`, {
    method: 'POST',
    body: payload,
    schema: draftOutSchema,
  });
}

export function updateDraft(
  mailboxId: string,
  accountId: string,
  providerDraftId: string,
  payload: DraftUpdate,
): Promise<DraftOut> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}/drafts/${providerDraftId}`, {
    method: 'PATCH',
    body: payload,
    schema: draftOutSchema,
  });
}

export function sendDraft(
  mailboxId: string,
  accountId: string,
  providerDraftId: string,
): Promise<DraftSendOut> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}/drafts/${providerDraftId}/send`, {
    method: 'POST',
    schema: draftSendOutSchema,
  });
}

export function listDrafts(mailboxId: string, accountId?: string): Promise<DraftOut[]> {
  const params = accountId ? `?account_id=${accountId}` : '';
  return request(`/mailboxes/${mailboxId}/drafts${params}`, { schema: draftListSchema });
}

export function syncDrafts(mailboxId: string, accountId?: string): Promise<DraftsSyncResultOut> {
  const params = accountId ? `?account_id=${accountId}` : '';
  return request(`/mailboxes/${mailboxId}/drafts/sync${params}`, {
    method: 'POST',
    schema: draftsSyncResultOutSchema,
  });
}

export function deleteDraft(
  mailboxId: string,
  accountId: string,
  draftId: string,
): Promise<StatusResponse> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}/drafts/${draftId}`, {
    method: 'DELETE',
    schema: statusResponseSchema,
  });
}

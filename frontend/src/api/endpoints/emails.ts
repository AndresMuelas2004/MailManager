import { request } from '../client/http';
import {
  emailContentOutSchema,
  emailMetadataListSchema,
  moveToTrashResultSchema,
  readStatusResponseSchema,
  spamResponseSchema,
  statusResponseSchema,
  syncResultOutSchema,
  trashActionResultSchema,
  type EmailContentOut,
  type EmailItemRef,
  type EmailMetadataOut,
  type EmailSendRequest,
  type MoveToTrashResult,
  type ReadStatusResponse,
  type SpamResponse,
  type StatusResponse,
  type SyncResultOut,
  type TrashActionResult,
} from '../types/dto';

export type ListEmailsOptions = {
  q?: string;
  signal?: AbortSignal;
};

export function listEmails(
  mailboxId: string,
  box: string,
  accountId?: string,
  options: ListEmailsOptions = {},
): Promise<EmailMetadataOut[]> {
  const params = new URLSearchParams({ box });
  if (accountId) params.set('account_id', accountId);
  if (options.q !== undefined && options.q.length > 0) params.set('q', options.q);
  return request(`/mailboxes/${mailboxId}/emails?${params}`, {
    schema: emailMetadataListSchema,
    signal: options.signal,
  });
}

export function getEmailContent(
  mailboxId: string,
  providerMessageId: string,
  accountId: string,
): Promise<EmailContentOut> {
  const params = new URLSearchParams({ account_id: accountId });
  return request(`/mailboxes/${mailboxId}/emails/${providerMessageId}/content?${params}`, {
    schema: emailContentOutSchema,
  });
}

export function syncEmailMetadata(mailboxId: string, accountId?: string): Promise<SyncResultOut> {
  const params = accountId ? `?account_id=${accountId}` : '';
  return request(`/mailboxes/${mailboxId}/emails/sync-metadata${params}`, {
    method: 'POST',
    schema: syncResultOutSchema,
  });
}

export function sendEmail(mailboxId: string, payload: EmailSendRequest): Promise<StatusResponse> {
  return request(`/mailboxes/${mailboxId}/emails/send`, {
    method: 'POST',
    body: payload,
    schema: statusResponseSchema,
  });
}

export function moveToTrash(mailboxId: string, items: EmailItemRef[]): Promise<MoveToTrashResult> {
  return request(`/mailboxes/${mailboxId}/emails/move-to-trash`, {
    method: 'POST',
    body: { items },
    schema: moveToTrashResultSchema,
  });
}

export function trashAction(
  mailboxId: string,
  action: 'delete' | 'restore',
  items: EmailItemRef[],
): Promise<TrashActionResult> {
  return request(`/mailboxes/${mailboxId}/emails/trash`, {
    method: 'POST',
    body: { action, items },
    schema: trashActionResultSchema,
  });
}

export function updateReadStatus(
  mailboxId: string,
  isRead: boolean,
  items: EmailItemRef[],
): Promise<ReadStatusResponse> {
  return request(`/mailboxes/${mailboxId}/emails/read-status`, {
    method: 'PATCH',
    body: { is_read: isRead, items },
    schema: readStatusResponseSchema,
  });
}

export function markAsSpam(mailboxId: string, items: EmailItemRef[]): Promise<SpamResponse> {
  return request(`/mailboxes/${mailboxId}/emails/spam`, {
    method: 'POST',
    body: { items },
    schema: spamResponseSchema,
  });
}

export function restoreFromSpam(mailboxId: string, items: EmailItemRef[]): Promise<SpamResponse> {
  return request(`/mailboxes/${mailboxId}/emails/restore-from-spam`, {
    method: 'POST',
    body: { items },
    schema: spamResponseSchema,
  });
}

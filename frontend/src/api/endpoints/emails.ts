import { request } from '../client/http';
import type {
  EmailContentOut,
  EmailItemRef,
  EmailMetadataOut,
  EmailSendRequest,
  MoveToTrashResult,
  ReadStatusResponse,
  SpamResponse,
  SyncResultOut,
  TrashActionResult,
} from '../types/dto';

export function listEmails(
  mailboxId: string,
  box: string,
  accountId?: string,
): Promise<EmailMetadataOut[]> {
  const params = new URLSearchParams({ box });
  if (accountId) params.set('account_id', accountId);
  return request<EmailMetadataOut[]>(`/mailboxes/${mailboxId}/emails?${params}`);
}

export function getEmailContent(
  mailboxId: string,
  providerMessageId: string,
  accountId: string,
): Promise<EmailContentOut> {
  const params = new URLSearchParams({ account_id: accountId });
  return request<EmailContentOut>(
    `/mailboxes/${mailboxId}/emails/${providerMessageId}/content?${params}`,
  );
}

export function syncEmailMetadata(mailboxId: string, accountId?: string): Promise<SyncResultOut> {
  const params = accountId ? `?account_id=${accountId}` : '';
  return request<SyncResultOut>(`/mailboxes/${mailboxId}/emails/sync-metadata${params}`, {
    method: 'POST',
  });
}

export function sendEmail(
  mailboxId: string,
  payload: EmailSendRequest,
): Promise<{ status: string }> {
  return request<{ status: string }>(`/mailboxes/${mailboxId}/emails/send`, {
    method: 'POST',
    body: payload,
  });
}

export function moveToTrash(mailboxId: string, items: EmailItemRef[]): Promise<MoveToTrashResult> {
  return request<MoveToTrashResult>(`/mailboxes/${mailboxId}/emails/move-to-trash`, {
    method: 'POST',
    body: { items },
  });
}

export function trashAction(
  mailboxId: string,
  action: 'delete' | 'restore',
  items: EmailItemRef[],
): Promise<TrashActionResult> {
  return request<TrashActionResult>(`/mailboxes/${mailboxId}/emails/trash`, {
    method: 'POST',
    body: { action, items },
  });
}

export function updateReadStatus(
  mailboxId: string,
  isRead: boolean,
  items: EmailItemRef[],
): Promise<ReadStatusResponse> {
  return request<ReadStatusResponse>(`/mailboxes/${mailboxId}/emails/read-status`, {
    method: 'PATCH',
    body: { is_read: isRead, items },
  });
}

export function markAsSpam(mailboxId: string, items: EmailItemRef[]): Promise<SpamResponse> {
  return request<SpamResponse>(`/mailboxes/${mailboxId}/emails/spam`, {
    method: 'POST',
    body: { items },
  });
}

export function restoreFromSpam(mailboxId: string, items: EmailItemRef[]): Promise<SpamResponse> {
  return request<SpamResponse>(`/mailboxes/${mailboxId}/emails/restore-from-spam`, {
    method: 'POST',
    body: { items },
  });
}

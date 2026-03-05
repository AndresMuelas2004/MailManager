import { request } from "../client/http";
import type { EmailSendRequest, SyncResultOut } from "../types/dto";

export function syncEmailMetadata(mailboxId: string): Promise<SyncResultOut> {
  return request<SyncResultOut>(`/mailboxes/${mailboxId}/emails/sync-metadata`, {
    method: "POST",
  });
}

export function sendEmail(mailboxId: string, payload: EmailSendRequest): Promise<{ status: string }> {
  return request<{ status: string }>(`/mailboxes/${mailboxId}/emails/send`, {
    method: "POST",
    body: payload,
  });
}

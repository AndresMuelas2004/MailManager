import { request } from "../client/http";
import type { MailboxCreate, MailboxOut } from "../types/dto";

export function createMailbox(payload: MailboxCreate): Promise<MailboxOut> {
  return request<MailboxOut>("/mailboxes", { method: "POST", body: payload });
}

export function listMailboxes(): Promise<MailboxOut[]> {
  return request<MailboxOut[]>("/mailboxes");
}

export function getMailbox(mailboxId: string): Promise<MailboxOut> {
  return request<MailboxOut>(`/mailboxes/${mailboxId}`);
}

export function deleteMailbox(mailboxId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/mailboxes/${mailboxId}`, { method: "DELETE" });
}

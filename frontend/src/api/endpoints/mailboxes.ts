import { request } from "../client/http";
import { toUiError } from "../client/errors";
import type { MailboxCreate, MailboxOut } from "../types/dto";
import { parseCreateMailboxResponse } from "../types/zod";

export function createMailbox(payload: MailboxCreate): Promise<MailboxOut> {
  return request<MailboxOut>("/mailboxes", { method: "POST", body: payload }).then((data) => {
    try {
      return parseCreateMailboxResponse(data) as MailboxOut;
    } catch (error) {
      throw toUiError(error);
    }
  });
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

import { request } from "../client/http";
import { toUiError } from "../client/errors";
import type { EmailOut, EmailSendRequest } from "../types/dto";
import { parseUnreadEmailsResponse } from "../types/zod";

export function listUnreadEmails(mailboxId: string): Promise<EmailOut[]> {
  return request<EmailOut[]>(`/users/${mailboxId}/emails/unread`).then((data) => {
    try {
      return parseUnreadEmailsResponse(data) as EmailOut[];
    } catch (error) {
      throw toUiError(error);
    }
  });
}

export function sendEmail(mailboxId: string, payload: EmailSendRequest): Promise<{ status: string }> {
  return request<{ status: string }>(`/users/${mailboxId}/emails/send`, {
    method: "POST",
    body: payload,
  });
}

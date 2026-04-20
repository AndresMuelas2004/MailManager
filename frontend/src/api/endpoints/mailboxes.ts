import { request } from '../client/http';
import {
  mailboxListSchema,
  mailboxOutSchema,
  statusResponseSchema,
  type MailboxCreate,
  type MailboxOut,
  type StatusResponse,
} from '../types/dto';

export function createMailbox(payload: MailboxCreate): Promise<MailboxOut> {
  return request('/mailboxes', { method: 'POST', body: payload, schema: mailboxOutSchema });
}

export function listMailboxes(): Promise<MailboxOut[]> {
  return request('/mailboxes', { schema: mailboxListSchema });
}

export function getMailbox(mailboxId: string): Promise<MailboxOut> {
  return request(`/mailboxes/${mailboxId}`, { schema: mailboxOutSchema });
}

export function deleteMailbox(mailboxId: string): Promise<StatusResponse> {
  return request(`/mailboxes/${mailboxId}`, {
    method: 'DELETE',
    schema: statusResponseSchema,
  });
}

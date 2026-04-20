import { request } from '../client/http';
import type {
  AccountConnectResponse,
  AccountCreate,
  AccountOut,
  AccountUpdate,
} from '../types/dto';

export function listAccounts(mailboxId: string): Promise<AccountOut[]> {
  return request<AccountOut[]>(`/mailboxes/${mailboxId}/accounts`);
}

export function createAccount(mailboxId: string, payload: AccountCreate): Promise<AccountOut> {
  return request<AccountOut>(`/mailboxes/${mailboxId}/accounts`, { method: 'POST', body: payload });
}

export function getAccount(mailboxId: string, accountId: string): Promise<AccountOut> {
  return request<AccountOut>(`/mailboxes/${mailboxId}/accounts/${accountId}`);
}

export function updateAccount(
  mailboxId: string,
  accountId: string,
  payload: AccountUpdate,
): Promise<AccountOut> {
  return request<AccountOut>(`/mailboxes/${mailboxId}/accounts/${accountId}`, {
    method: 'PATCH',
    body: payload,
  });
}

export function deleteAccount(mailboxId: string, accountId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/mailboxes/${mailboxId}/accounts/${accountId}`, {
    method: 'DELETE',
  });
}

export function connectAccount(
  mailboxId: string,
  accountId: string,
): Promise<AccountConnectResponse> {
  return request<AccountConnectResponse>(`/mailboxes/${mailboxId}/accounts/${accountId}/connect`, {
    method: 'POST',
  });
}

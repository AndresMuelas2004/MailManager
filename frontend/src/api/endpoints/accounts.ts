import { request } from '../client/http';
import {
  accountConnectResponseSchema,
  accountListSchema,
  accountOutSchema,
  statusResponseSchema,
  type AccountConnectResponse,
  type AccountCreate,
  type AccountOut,
  type AccountUpdate,
  type StatusResponse,
} from '../types/dto';

export function listAccounts(mailboxId: string): Promise<AccountOut[]> {
  return request(`/mailboxes/${mailboxId}/accounts`, { schema: accountListSchema });
}

export function createAccount(mailboxId: string, payload: AccountCreate): Promise<AccountOut> {
  return request(`/mailboxes/${mailboxId}/accounts`, {
    method: 'POST',
    body: payload,
    schema: accountOutSchema,
  });
}

export function getAccount(mailboxId: string, accountId: string): Promise<AccountOut> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}`, { schema: accountOutSchema });
}

export function updateAccount(
  mailboxId: string,
  accountId: string,
  payload: AccountUpdate,
): Promise<AccountOut> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}`, {
    method: 'PATCH',
    body: payload,
    schema: accountOutSchema,
  });
}

export function deleteAccount(mailboxId: string, accountId: string): Promise<StatusResponse> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}`, {
    method: 'DELETE',
    schema: statusResponseSchema,
  });
}

export function connectAccount(
  mailboxId: string,
  accountId: string,
): Promise<AccountConnectResponse> {
  return request(`/mailboxes/${mailboxId}/accounts/${accountId}/connect`, {
    method: 'POST',
    schema: accountConnectResponseSchema,
  });
}

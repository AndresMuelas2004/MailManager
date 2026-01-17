import { request } from "../client/http";
import { toUiError } from "../client/errors";
import type {
  AccountConnectResponse,
  AccountCreate,
  AccountOut,
  AccountUpdate,
} from "../types/dto";
import { parseListAccountsResponse } from "../types/zod";

export function listAccounts(mailboxId: string): Promise<AccountOut[]> {
  return request<AccountOut[]>(`/mailboxes/${mailboxId}/accounts`).then((data) => {
    try {
      return parseListAccountsResponse(data) as AccountOut[];
    } catch (error) {
      throw toUiError(error);
    }
  });
}

export function createAccount(mailboxId: string, payload: AccountCreate): Promise<AccountOut> {
  return request<AccountOut>(`/mailboxes/${mailboxId}/accounts`, { method: "POST", body: payload });
}

export function updateAccount(
  mailboxId: string,
  accountId: string,
  payload: AccountUpdate
): Promise<AccountOut> {
  return request<AccountOut>(`/mailboxes/${mailboxId}/accounts/${accountId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteAccount(mailboxId: string, accountId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/mailboxes/${mailboxId}/accounts/${accountId}`, {
    method: "DELETE",
  });
}

export function connectAccount(
  mailboxId: string,
  accountId: string
): Promise<AccountConnectResponse> {
  return request<AccountConnectResponse>(
    `/mailboxes/${mailboxId}/accounts/${accountId}/connect`,
    {
    method: "POST",
    }
  );
}

export type AddAccountAndConnectResult = {
  account: AccountOut;
  connect: AccountConnectResponse;
  connected: true;
};

export async function addAccountAndConnect(
  mailboxId: string,
  payload: AccountCreate
): Promise<AddAccountAndConnectResult> {
  const account = await createAccount(mailboxId, payload);
  const connect = await connectAccount(mailboxId, account.account_id);
  return { account, connect, connected: true };
}

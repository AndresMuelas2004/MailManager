import { request } from "../client/http";
import { toUiError } from "../client/errors";
import type { UserCreate, UserOut } from "../types/dto";
import { parseCreateUserResponse } from "../types/zod";

export function createUser(payload: UserCreate): Promise<UserOut> {
  return request<UserOut>("/users", { method: "POST", body: payload }).then((data) => {
    try {
      return parseCreateUserResponse(data) as UserOut;
    } catch (error) {
      throw toUiError(error);
    }
  });
}

export function listUsers(): Promise<UserOut[]> {
  return request<UserOut[]>("/users");
}

export function getUser(mailboxId: string): Promise<UserOut> {
  return request<UserOut>(`/users/${mailboxId}`);
}

export function deleteUser(mailboxId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/users/${mailboxId}`, { method: "DELETE" });
}

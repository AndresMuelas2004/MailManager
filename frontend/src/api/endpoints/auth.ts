import { request } from "../client/http";
import type { AuthResponse, UserOut } from "../types/dto";

export function loginWithGoogle(idToken: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/google", {
    method: "POST",
    body: { id_token: idToken },
  });
}

export function getMe(): Promise<UserOut> {
  return request<UserOut>("/auth/me");
}

export function logout(): Promise<{ message: string }> {
  return request<{ message: string }>("/auth/logout", { method: "POST" });
}

export function deleteAccount(): Promise<{ message: string }> {
  return request<{ message: string }>("/auth/me", { method: "DELETE" });
}

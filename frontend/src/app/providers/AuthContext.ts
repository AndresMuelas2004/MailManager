import { createContext, useContext } from "react";

import type { UserOut } from "../../api/types/dto";
import type { UiError } from "../../api/client/errors";

export type AuthState = {
  user: UserOut | null;
  loading: boolean;
  error: UiError | null;
  login: (idToken: string) => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

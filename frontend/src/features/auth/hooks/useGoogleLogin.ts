import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "../../../app/providers/AuthContext";
import { toUiError } from "../../../api/client/errors";
import type { UiError } from "../../../api/client/errors";

type UseGoogleLoginReturn = {
  buttonRef: React.RefObject<HTMLDivElement | null>;
  error: UiError | null;
  loading: boolean;
};

export default function useGoogleLogin(): UseGoogleLoginReturn {
  const { login } = useAuth();
  const buttonRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const [loading, setLoading] = useState(false);

  const handleCredentialResponse = useCallback(
    async (response: google.accounts.id.CredentialResponse) => {
      setError(null);
      setLoading(true);
      try {
        await login(response.credential);
      } catch (err) {
        setError(toUiError(err));
      } finally {
        setLoading(false);
      }
    },
    [login],
  );

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
    if (!clientId) {
      setError({ message: "Google Client ID is not configured." });
      return;
    }

    const intervalId = setInterval(() => {
      if (
        typeof google !== "undefined" &&
        google.accounts?.id &&
        buttonRef.current
      ) {
        clearInterval(intervalId);

        google.accounts.id.initialize({
          client_id: clientId,
          callback: handleCredentialResponse,
        });

        google.accounts.id.renderButton(buttonRef.current, {
          theme: "filled_blue",
          size: "large",
          shape: "pill",
          text: "continue_with",
          width: 400,
        });
      }
    }, 100);

    return () => clearInterval(intervalId);
  }, [handleCredentialResponse]);

  return { buttonRef, error, loading };
}

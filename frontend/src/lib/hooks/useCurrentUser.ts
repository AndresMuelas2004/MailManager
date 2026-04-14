import { useCallback, useState } from "react";

import { deleteMe, getMe } from "../../api/endpoints/auth";
import { toUiError } from "../../api/client/errors";
import type { UiError } from "../../api/client/errors";
import type { UserOut } from "../../api/types/dto";

export type UseCurrentUserReturn = {
  loading: boolean;
  error: UiError | null;
  fetchMe: () => Promise<UserOut | null>;
  deleteCurrentUser: () => Promise<boolean>;
};

export default function useCurrentUser(): UseCurrentUserReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const fetchMe = useCallback(async (): Promise<UserOut | null> => {
    setLoading(true);
    setError(null);
    try {
      return await getMe();
    } catch (err) {
      setError(toUiError(err));
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteCurrentUser = useCallback(async (): Promise<boolean> => {
    setError(null);
    try {
      await deleteMe();
      return true;
    } catch (err) {
      setError(toUiError(err));
      return false;
    }
  }, []);

  return { loading, error, fetchMe, deleteCurrentUser };
}

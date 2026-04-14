type ErrorDetail = {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
};

type ErrorResponse = {
  error: ErrorDetail;
};

export type UiError = {
  message: string;
  code?: string;
};

export class ApiError extends Error {
  code: string;
  status?: number;
  detail?: Record<string, unknown>;

  constructor(message: string, code: string, status?: number, detail?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function toApiError(status: number, payload?: unknown): ApiError {
  const data = payload as ErrorResponse | undefined;
  if (data?.error?.code) {
    return new ApiError(data.error.message, data.error.code, status, data.error.detail);
  }
  const message = typeof payload === "string" && payload.length > 0
    ? payload
    : "Request failed";
  return new ApiError(message, "http_error", status);
}

export function toNetworkError(message: string): ApiError {
  return new ApiError(message, "network_error");
}

export function toUiError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, code: error.code };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  if (typeof error === "string") {
    return { message: error };
  }
  return { message: "Unexpected error" };
}

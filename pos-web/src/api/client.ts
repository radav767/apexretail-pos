import axios from "axios";
import { advanceAuthenticationEpoch, authorizationFor, captureAuthentication, shouldInvalidateAuthentication } from "./authLifecycle.ts";
import type { AuthenticationSnapshot } from "./authLifecycle.ts";

// Keep credential snapshots out of serializable Axios configs/error reports.
const authenticationByRequest = new WeakMap<object, AuthenticationSnapshot>();

type ApiFieldError = {
  field?: unknown;
  message?: unknown;
};

type ApiErrorData = {
  detail?: unknown;
  message?: unknown;
  field_errors?: ApiFieldError[];
};

function normalizeFieldLabel(field: unknown): string {
  if (typeof field !== "string") {
    return "";
  }

  return field
    .split(".")
    .filter(Boolean)
    .join(".")
    .replace(/_/g, " ");
}

function getFieldErrors(
  data: ApiErrorData | undefined,
): Array<{ field: string; message: string }> {
  if (!Array.isArray(data?.field_errors)) {
    return [];
  }

  return data.field_errors
    .map((item) => ({
      field: normalizeFieldLabel(item?.field),
      message:
        typeof item?.message === "string"
          ? item.message.trim()
          : "",
    }))
    .filter((item) => item.message);
}

export function getApiErrorMessage(
  error: unknown,
  fallback = "Request failed",
): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | ApiErrorData
      | undefined;
    const fieldErrors = getFieldErrors(data);

    if (fieldErrors.length > 0) {
      const [firstError] = fieldErrors;

      return firstError.field
        ? `${firstError.field}: ${firstError.message}`
        : firstError.message;
    }

    if (typeof data?.message === "string") {
      return data.message;
    }

    if (typeof data?.detail === "string") {
      return data.detail;
    }

    if (!error.response && (
      error.code === "ERR_NETWORK" ||
      error.code === "ECONNABORTED" ||
      error.message === "Network Error"
    )) {
      return "Unable to reach ApexPOS. Check the connection and verify the transaction status before retrying.";
    }

    if (typeof error.message === "string") {
      return error.message;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

export const api = axios.create({
  baseURL:
    import.meta.env?.VITE_API_BASE_URL ||
    "https://api.apexpos.cloud/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const snapshot = captureAuthentication();
  authenticationByRequest.set(config, snapshot);
  const authorization = authorizationFor(snapshot);
  if (authorization) {
    config.headers.Authorization = authorization;
  } else if (config.headers.Authorization) {
    delete config.headers.Authorization;
  }

  return config;
}, undefined, { synchronous: true });

api.interceptors.response.use(
  (response) => {
    authenticationByRequest.delete(response.config);
    return response;
  },
  (error) => {
    const sent = error?.config ? authenticationByRequest.get(error.config) : undefined;
    if (error?.config) authenticationByRequest.delete(error.config);
    if (typeof window !== "undefined" && shouldInvalidateAuthentication(error?.response?.status, error?.config?.url, sent)) {
      error.apexInvalidatedAuthentication = true;
      const kind = sent?.employee ? "employee" : "owner";
      if (kind === "employee") {
        localStorage.removeItem("employee_token");
        localStorage.removeItem("employee_id");
      } else {
        localStorage.removeItem("token");
      }
      advanceAuthenticationEpoch();
      window.dispatchEvent(new CustomEvent("apex-session-invalidated", { detail: { kind } }));
    }
    if (error && typeof error === "object") {
      (
        error as {
          normalizedMessage?: string;
        }
      ).normalizedMessage = getApiErrorMessage(
        error,
        "Request failed",
      );
    }

    return Promise.reject(error);
  },
);

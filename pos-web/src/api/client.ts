import axios from "axios";

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
    import.meta.env.VITE_API_BASE_URL ||
    "https://api.apexpos.cloud/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const employeeToken =
    localStorage.getItem("employee_token");
  const employeeId =
    localStorage.getItem("employee_id");
  const ownerToken =
    localStorage.getItem("token");

  if (employeeToken) {
    config.headers.Authorization = `Bearer ${employeeToken}`;
  } else if (!employeeId && ownerToken) {
    config.headers.Authorization = `Bearer ${ownerToken}`;
  } else if (config.headers.Authorization) {
    delete config.headers.Authorization;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("employee_token");
      localStorage.removeItem("employee_id");
      window.dispatchEvent(new CustomEvent("apex-session-invalidated"));
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

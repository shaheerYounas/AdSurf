export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8720";
export const defaultWorkspaceId = process.env.NEXT_PUBLIC_LOCAL_WORKSPACE_ID ?? "00000000-0000-0000-0000-000000000001";
export const localUserId = "00000000-0000-0000-0000-000000000001";

type ApiEnvelope<T> = {
  success: boolean;
  data: T;
  error?: { message?: string; code?: string; details?: Record<string, unknown> };
  meta?: Record<string, unknown>;
};

export class ApiError extends Error {
  status?: number;
  code?: string;
  details?: Record<string, unknown>;

  constructor(message: string, options: { status?: number; code?: string; details?: Record<string, unknown>; cause?: unknown } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
    this.cause = options.cause;
  }
}

export function localAuthHeaders(workspaceId = defaultWorkspaceId, role = "analyst") {
  return {
    "x-user-id": localUserId,
    "x-test-workspaces": `${workspaceId}:${role}`,
  };
}

export async function readApiData<T>(response: Response, fallbackMessage: string): Promise<T> {
  let body: ApiEnvelope<T>;
  try {
    body = (await response.json()) as ApiEnvelope<T>;
  } catch (err) {
    if (!response.ok) {
      throw new ApiError(`${fallbackMessage} The server returned HTTP ${response.status}, but the response body could not be read.`, {
        status: response.status,
        details: err instanceof Error ? { parseError: err.message } : undefined,
        cause: err,
      });
    }
    throw err;
  }
  
  if (!response.ok) {
    throw new ApiError(body.error?.message ?? fallbackMessage, {
      status: response.status,
      code: body.error?.code,
      details: body.error?.details,
    });
  }
  return body.data;
}

export function formatApiError(caught: unknown, fallbackMessage = "The requested data could not be loaded."): string {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return "The request was cancelled before it completed.";
  }

  if (caught instanceof TypeError && caught.message === "Failed to fetch") {
    return `Unable to reach the API server at ${apiBaseUrl}. The browser reported "Failed to fetch"; check that the backend is running and that the network connection is available.`;
  }

  if (caught instanceof ApiError) {
    const status = caught.status ? ` HTTP ${caught.status}.` : "";
    return `${caught.message}${status}`;
  }

  if (caught instanceof Error) {
    return caught.message || fallbackMessage;
  }

  return fallbackMessage;
}

export async function fetchApiData<T>(input: RequestInfo | URL, init: RequestInit | undefined, fallbackMessage: string): Promise<T> {
  try {
    const response = await fetch(input, init);
    return await readApiData<T>(response, fallbackMessage);
  } catch (caught) {
    if (caught instanceof ApiError) throw caught;
    throw new ApiError(formatApiError(caught, fallbackMessage), { cause: caught });
  }
}

export function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

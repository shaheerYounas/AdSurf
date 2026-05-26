export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
export const defaultWorkspaceId = process.env.NEXT_PUBLIC_LOCAL_WORKSPACE_ID ?? "00000000-0000-0000-0000-000000000001";
export const localUserId = "00000000-0000-0000-0000-000000000001";

type ApiEnvelope<T> = {
  success: boolean;
  data: T;
  error?: { message?: string };
  meta?: Record<string, unknown>;
};

export function localAuthHeaders(workspaceId = defaultWorkspaceId) {
  return {
    "x-user-id": localUserId,
    "x-test-workspaces": `${workspaceId}:analyst`,
  };
}

export async function readApiData<T>(response: Response, fallbackMessage: string): Promise<T> {
  const body = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok) {
    throw new Error(body.error?.message ?? fallbackMessage);
  }
  return body.data;
}

export function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

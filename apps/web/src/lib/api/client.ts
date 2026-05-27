export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const defaultWorkspaceId = process.env.NEXT_PUBLIC_LOCAL_WORKSPACE_ID ?? "00000000-0000-0000-0000-000000000001";
export const localUserId = "00000000-0000-0000-0000-000000000001";

type ApiEnvelope<T> = {
  success: boolean;
  data: T;
  error?: { message?: string };
  meta?: Record<string, unknown>;
};

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
      throw new Error(`Server returned HTTP ${response.status}: ${fallbackMessage} (Failed to parse response)`);
    }
    throw err;
  }
  
  if (!response.ok) {
    throw new Error(body.error?.message ?? fallbackMessage);
  }
  return body.data;
}

export function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

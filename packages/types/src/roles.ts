export const WORKSPACE_ROLES = [
  "owner",
  "admin",
  "analyst",
  "approver",
  "viewer"
] as const;

export type WorkspaceRole = (typeof WORKSPACE_ROLES)[number];


import { jwtDecode } from 'jwt-decode';

/** Workspace the access token is scoped to (the server pins sockets to it). */
export const getWorkspaceIdFromToken = (token: string | null): string | null => {
  if (!token) return null;
  try {
    const claims = jwtDecode<{ workspace_id?: string }>(token);
    return claims.workspace_id ?? null;
  } catch {
    return null;
  }
};

/** ws(s)://host/api/ws, derived from the REST base URL unless set explicitly. */
export const getWebSocketUrl = (
  apiUrl: string = process.env.REACT_APP_API_URL || 'http://localhost:8000/api',
  explicit: string | undefined = process.env.REACT_APP_WS_URL
): string => {
  if (explicit) return explicit;
  return `${apiUrl.replace(/^http/, 'ws').replace(/\/+$/, '')}/ws`;
};

const TERMINAL = new Set(['COMPLETED', 'FAILED']);

/** True when a socket event says this transformation reached a final state. */
export const isTerminalUpdateFor = (update: any, transformationId: string | undefined): boolean =>
  !!update &&
  !!transformationId &&
  update.transformation_id === transformationId &&
  TERMINAL.has(String(update.status).toUpperCase());

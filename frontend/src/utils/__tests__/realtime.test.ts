import { getWebSocketUrl, getWorkspaceIdFromToken, isTerminalUpdateFor } from '../realtime';

const b64url = (obj: object) =>
  btoa(JSON.stringify(obj)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
const fakeJwt = (claims: object) => `${b64url({ alg: 'HS256' })}.${b64url(claims)}.sig`;

describe('getWorkspaceIdFromToken', () => {
  it('reads the workspace claim', () => {
    expect(getWorkspaceIdFromToken(fakeJwt({ workspace_id: 'ws-1' }))).toBe('ws-1');
  });

  it('returns null for missing or malformed tokens', () => {
    expect(getWorkspaceIdFromToken(null)).toBeNull();
    expect(getWorkspaceIdFromToken('not-a-jwt')).toBeNull();
    expect(getWorkspaceIdFromToken(fakeJwt({ sub: 'u' }))).toBeNull();
  });
});

describe('getWebSocketUrl', () => {
  it('derives ws/wss from the REST base URL', () => {
    expect(getWebSocketUrl('http://localhost:8000/api', undefined)).toBe('ws://localhost:8000/api/ws');
    expect(getWebSocketUrl('https://api.example.com/api/', undefined)).toBe('wss://api.example.com/api/ws');
  });

  it('prefers an explicit URL', () => {
    expect(getWebSocketUrl('http://x/api', 'wss://rt.example.com/ws')).toBe('wss://rt.example.com/ws');
  });
});

describe('isTerminalUpdateFor', () => {
  it('matches completed/failed events for the same transformation', () => {
    expect(isTerminalUpdateFor({ transformation_id: 't1', status: 'COMPLETED' }, 't1')).toBe(true);
    expect(isTerminalUpdateFor({ transformation_id: 't1', status: 'failed' }, 't1')).toBe(true);
  });

  it('ignores progress events and other transformations', () => {
    expect(isTerminalUpdateFor({ transformation_id: 't1', status: 'PROCESSING' }, 't1')).toBe(false);
    expect(isTerminalUpdateFor({ transformation_id: 't2', status: 'COMPLETED' }, 't1')).toBe(false);
    expect(isTerminalUpdateFor(null, 't1')).toBe(false);
  });
});

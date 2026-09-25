import React, { createContext, useContext, ReactNode } from 'react';
import { useWebSocket, WebSocketState, WebSocketMessage } from '../services/websocketService';
import { useAuth } from './AuthContext';
import { getWebSocketUrl, getWorkspaceIdFromToken } from '../utils/realtime';

interface WebSocketContextType {
  connectionState: WebSocketState;
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  transformationUpdates: any[];
  presenceData: any;
  error: Error | null;
  sendMessage: (message: Partial<WebSocketMessage>) => boolean;
  getWorkspacePresence: () => void;
  sendWorkspaceMessage: (messageData: any) => boolean;
  clearError: () => void;
  clearTransformationUpdates: () => void;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

/**
 * Opens one socket per signed-in session. The server pins it to the workspace in
 * the access token and pushes transformation progress from the Celery worker.
 */
export const RealtimeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  // Re-read on user change so login/logout opens/closes the socket.
  const token = user ? localStorage.getItem('token') : null;
  const webSocketState = useWebSocket(token, getWorkspaceIdFromToken(token), {
    baseUrl: getWebSocketUrl(),
    reconnectInterval: 5000,
    maxReconnectAttempts: 5,
    pingInterval: 30000,
  });

  return <WebSocketContext.Provider value={webSocketState}>{children}</WebSocketContext.Provider>;
};

/** Realtime state, or null outside a RealtimeProvider (callers fall back to polling). */
export const useRealtime = (): WebSocketContextType | null => useContext(WebSocketContext);

export default WebSocketContext;

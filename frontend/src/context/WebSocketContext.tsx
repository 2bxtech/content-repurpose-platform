import React, { createContext, useContext, ReactNode } from 'react';
import { useWebSocket, WebSocketState, WebSocketMessage } from '../services/websocketService';

// WebSocket context interface
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

// Create context
const WebSocketContext = createContext<WebSocketContextType | null>(null);

// WebSocket provider props
interface WebSocketProviderProps {
  children: ReactNode;
  token: string | null;
  workspaceId: string | null;
}

// WebSocket provider component
export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({
  children,
  token,
  workspaceId
}) => {
  const webSocketState = useWebSocket(token, workspaceId, {
    baseUrl: process.env.REACT_APP_WS_URL || 'ws://localhost:8000/api/ws',
    reconnectInterval: 5000,
    maxReconnectAttempts: 5,
    pingInterval: 30000
  });

  return (
    <WebSocketContext.Provider value={webSocketState}>
      {children}
    </WebSocketContext.Provider>
  );
};

// Hook to use WebSocket context
export const useWebSocketContext = (): WebSocketContextType => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
};

export default WebSocketContext;
import { useState, useEffect, useRef } from 'react';

// WebSocket connection states
export enum WebSocketState {
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED',
  DISCONNECTED = 'DISCONNECTED',
  ERROR = 'ERROR'
}

// WebSocket message types
export interface WebSocketMessage {
  type: string;
  data: any;
  target?: string;
  target_id?: string;
  sender_id?: string;
  timestamp?: string;
}

// WebSocket event callbacks
export interface WebSocketCallbacks {
  onMessage?: (message: WebSocketMessage) => void;
  onConnectionChange?: (state: WebSocketState) => void;
  onTransformationUpdate?: (update: any) => void;
  onPresenceUpdate?: (presence: any) => void;
  onError?: (error: Error) => void;
}

// WebSocket configuration
export interface WebSocketConfig {
  baseUrl?: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  pingInterval?: number;
}

export class WebSocketService {
  private ws: WebSocket | null = null;
  private config: WebSocketConfig;
  private callbacks: WebSocketCallbacks = {};
  private state: WebSocketState = WebSocketState.DISCONNECTED;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private pingTimer: NodeJS.Timeout | null = null;
  private token: string | null = null;
  private workspaceId: string | null = null;

  constructor(config: WebSocketConfig = {}) {
    this.config = {
      baseUrl: 'ws://localhost:8000/api/ws',
      reconnectInterval: 5000,
      maxReconnectAttempts: 5,
      pingInterval: 30000,
      ...config
    };
  }

  // Connect to WebSocket
  connect(token: string, workspaceId: string, callbacks: WebSocketCallbacks = {}): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.token = token;
        this.workspaceId = workspaceId;
        this.callbacks = callbacks;

        // Build WebSocket URL with authentication
        const wsUrl = `${this.config.baseUrl}?token=${encodeURIComponent(token)}&workspace_id=${encodeURIComponent(workspaceId)}`;
        
        this.setState(WebSocketState.CONNECTING);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = (event) => {
          console.log('WebSocket connected');
          this.setState(WebSocketState.CONNECTED);
          this.reconnectAttempts = 0;
          this.startPing();
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            this.handleMessage(message);
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
            this.callbacks.onError?.(new Error('Failed to parse WebSocket message'));
          }
        };

        this.ws.onerror = (event) => {
          console.error('WebSocket error:', event);
          this.setState(WebSocketState.ERROR);
          this.callbacks.onError?.(new Error('WebSocket connection error'));
          reject(new Error('WebSocket connection error'));
        };

        this.ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.code, event.reason);
          this.setState(WebSocketState.DISCONNECTED);
          this.stopPing();
          
          // Attempt to reconnect if not manually closed
          if (event.code !== 1000 && this.reconnectAttempts < this.config.maxReconnectAttempts!) {
            this.scheduleReconnect();
          }
        };

      } catch (error) {
        this.setState(WebSocketState.ERROR);
        this.callbacks.onError?.(error as Error);
        reject(error);
      }
    });
  }

  // Disconnect from WebSocket
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    this.stopPing();
    
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close(1000, 'Client disconnect');
    }
    
    this.ws = null;
    this.setState(WebSocketState.DISCONNECTED);
  }

  // Send message through WebSocket
  send(message: Partial<WebSocketMessage>): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not connected, cannot send message');
      return false;
    }

    try {
      const fullMessage: WebSocketMessage = {
        type: message.type || 'message',
        data: message.data || {},
        timestamp: new Date().toISOString(),
        ...message
      };

      this.ws.send(JSON.stringify(fullMessage));
      return true;
    } catch (error) {
      console.error('Error sending WebSocket message:', error);
      this.callbacks.onError?.(error as Error);
      return false;
    }
  }

  // Send ping message
  private sendPing(): void {
    this.send({
      type: 'ping',
      data: { timestamp: new Date().toISOString() }
    });
  }

  // Start ping timer
  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      this.sendPing();
    }, this.config.pingInterval!);
  }

  // Stop ping timer
  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  // Schedule reconnection attempt
  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectAttempts++;
    const delay = this.config.reconnectInterval! * Math.pow(2, Math.min(this.reconnectAttempts - 1, 5));
    
    console.log(`Scheduling WebSocket reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);
    
    this.reconnectTimer = setTimeout(() => {
      if (this.token && this.workspaceId) {
        this.connect(this.token, this.workspaceId, this.callbacks).catch((error) => {
          console.error('Reconnect failed:', error);
        });
      }
    }, delay);
  }

  // Handle incoming messages
  private handleMessage(message: WebSocketMessage): void {
    console.log('WebSocket message received:', message);

    // Route messages to specific handlers
    switch (message.type) {
      case 'connection_established':
        console.log('WebSocket connection established:', message.data);
        break;

      case 'pong':
        // Handle ping response
        break;

      case 'transformation_started':
      case 'transformation_progress':
      case 'transformation_completed':
      case 'transformation_failed':
        this.callbacks.onTransformationUpdate?.(message.data);
        break;

      case 'presence_update':
      case 'workspace_presence':
        this.callbacks.onPresenceUpdate?.(message.data);
        break;

      case 'workspace_message':
        // Handle workspace-wide messages
        break;

      case 'error':
        console.error('WebSocket error message:', message.data);
        this.callbacks.onError?.(new Error(message.data.message || 'WebSocket error'));
        break;

      default:
        console.log('Unknown WebSocket message type:', message.type);
    }

    // Call general message handler
    this.callbacks.onMessage?.(message);
  }

  // Set connection state and notify callbacks
  private setState(newState: WebSocketState): void {
    if (this.state !== newState) {
      this.state = newState;
      this.callbacks.onConnectionChange?.(newState);
    }
  }

  // Get current connection state
  getState(): WebSocketState {
    return this.state;
  }

  // Check if connected
  isConnected(): boolean {
    return this.state === WebSocketState.CONNECTED && this.ws?.readyState === WebSocket.OPEN;
  }

  // Get workspace presence
  getWorkspacePresence(): void {
    this.send({
      type: 'get_workspace_presence',
      data: {}
    });
  }

  // Send workspace message
  sendWorkspaceMessage(messageData: any): boolean {
    return this.send({
      type: 'workspace_message',
      data: messageData
    });
  }
}

// React hook for WebSocket connection
export const useWebSocket = (
  token: string | null,
  workspaceId: string | null,
  config: WebSocketConfig = {}
) => {
  const [connectionState, setConnectionState] = useState<WebSocketState>(WebSocketState.DISCONNECTED);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [transformationUpdates, setTransformationUpdates] = useState<any[]>([]);
  const [presenceData, setPresenceData] = useState<any>(null);
  const [error, setError] = useState<Error | null>(null);

  const wsRef = useRef<WebSocketService | null>(null);
  const configRef = useRef(config);
  configRef.current = config;

  useEffect(() => {
    if (!token || !workspaceId) {
      return;
    }

    // Create WebSocket service
    wsRef.current = new WebSocketService(configRef.current);

    // Connect with callbacks
    wsRef.current.connect(token, workspaceId, {
      onConnectionChange: setConnectionState,
      onMessage: setLastMessage,
      onTransformationUpdate: (update) => {
        setTransformationUpdates(prev => [...prev, update]);
      },
      onPresenceUpdate: setPresenceData,
      onError: setError
    }).catch((err) => {
      console.error('WebSocket connection failed:', err);
      setError(err);
    });

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect();
        wsRef.current = null;
      }
    };
  }, [token, workspaceId]);

  // Provide interface for sending messages
  const sendMessage = (message: Partial<WebSocketMessage>) => {
    return wsRef.current?.send(message) || false;
  };

  const getWorkspacePresence = () => {
    wsRef.current?.getWorkspacePresence();
  };

  const sendWorkspaceMessage = (messageData: any) => {
    return wsRef.current?.sendWorkspaceMessage(messageData) || false;
  };

  return {
    connectionState,
    isConnected: connectionState === WebSocketState.CONNECTED,
    lastMessage,
    transformationUpdates,
    presenceData,
    error,
    sendMessage,
    getWorkspacePresence,
    sendWorkspaceMessage,
    clearError: () => setError(null),
    clearTransformationUpdates: () => setTransformationUpdates([])
  };
};

export default WebSocketService;
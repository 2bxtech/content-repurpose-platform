import { WebSocketService, WebSocketState, WebSocketMessage, WebSocketCallbacks } from '../websocketService';

// Mock WebSocket
class MockWebSocket {
  public readyState: number = WebSocket.CONNECTING;
  public onopen: ((event: Event) => void) | null = null;
  public onclose: ((event: CloseEvent) => void) | null = null;
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public onerror: ((event: Event) => void) | null = null;
  public url: string;

  constructor(url: string, autoOpen: boolean = true) {
    this.url = url;
    // Simulate async connection
    if (autoOpen) {
      setTimeout(() => {
        this.readyState = WebSocket.OPEN;
        this.onopen?.(new Event('open'));
      }, 0);
    }
  }

  send(data: string) {
    // Mock send method
  }

  close(code?: number, reason?: string) {
    this.readyState = WebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }

  // Helper methods for testing
  simulateMessage(data: any) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
  }

  simulateError() {
    this.onerror?.(new Event('error'));
  }

  simulateClose(code: number = 1000, reason: string = '') {
    this.readyState = WebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }
}

// Mock global WebSocket
global.WebSocket = MockWebSocket as any;

describe('WebSocketService', () => {
  let service: WebSocketService;
  let mockCallbacks: WebSocketCallbacks;

  beforeEach(() => {
    global.WebSocket = MockWebSocket as any;
    service = new WebSocketService();
    mockCallbacks = {
      onMessage: jest.fn(),
      onConnectionChange: jest.fn(),
      onTransformationUpdate: jest.fn(),
      onPresenceUpdate: jest.fn(),
      onError: jest.fn()
    };
    jest.clearAllTimers();
    jest.useFakeTimers();
  });

  afterEach(() => {
    service.disconnect();
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('connection', () => {
    it('should connect successfully', async () => {
      const token = 'test-token';
      const workspaceId = 'workspace123';

      const connectPromise = service.connect(token, workspaceId, mockCallbacks);
      
      // Fast forward to allow connection
      jest.runOnlyPendingTimers();
      await connectPromise;

      expect(service.getState()).toBe(WebSocketState.CONNECTED);
      expect(service.isConnected()).toBe(true);
      expect(mockCallbacks.onConnectionChange).toHaveBeenCalledWith(WebSocketState.CONNECTING);
      expect(mockCallbacks.onConnectionChange).toHaveBeenCalledWith(WebSocketState.CONNECTED);
    });

    it('should build correct WebSocket URL with token and workspace', async () => {
      const token = 'test-token';
      const workspaceId = 'workspace123';

      const connectPromise = service.connect(token, workspaceId, mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;

      // Check that URL was constructed correctly
      expect((service as any).ws.url).toContain('token=test-token');
      expect((service as any).ws.url).toContain('workspace_id=workspace123');
    });

    it('should handle connection errors', async () => {
      const token = 'test-token';
      const workspaceId = 'workspace123';

      // Override WebSocket to simulate error
      global.WebSocket = class extends MockWebSocket {
        constructor(url: string) {
          super(url, false);
          setTimeout(() => {
            this.onerror?.(new Event('error'));
          }, 0);
        }
      } as any;

      service = new WebSocketService();

      const connectPromise = service.connect(token, workspaceId, mockCallbacks);
      jest.runOnlyPendingTimers();

      await expect(connectPromise).rejects.toThrow('WebSocket connection error');
      expect(service.getState()).toBe(WebSocketState.ERROR);
      expect(mockCallbacks.onError).toHaveBeenCalled();
    });

    it('should disconnect cleanly', async () => {
      const token = 'test-token';
      const workspaceId = 'workspace123';

      const connectPromise = service.connect(token, workspaceId, mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;

      service.disconnect();

      expect(service.getState()).toBe(WebSocketState.DISCONNECTED);
      expect(service.isConnected()).toBe(false);
    });
  });

  describe('message handling', () => {
    beforeEach(async () => {
      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;
    });

    it('should handle connection_established message', () => {
      const message: WebSocketMessage = {
        type: 'connection_established',
        data: { connection_id: 'conn123', user_id: 'user123' }
      };

      (service as any).ws.simulateMessage(message);

      expect(mockCallbacks.onMessage).toHaveBeenCalledWith(message);
    });

    it('should handle transformation updates', () => {
      const transformationUpdate: WebSocketMessage = {
        type: 'transformation_progress',
        data: { transformation_id: 'trans123', progress: 50, status: 'processing' }
      };

      (service as any).ws.simulateMessage(transformationUpdate);

      expect(mockCallbacks.onTransformationUpdate).toHaveBeenCalledWith(transformationUpdate.data);
      expect(mockCallbacks.onMessage).toHaveBeenCalledWith(transformationUpdate);
    });

    it('should handle presence updates', () => {
      const presenceUpdate: WebSocketMessage = {
        type: 'presence_update',
        data: { user_id: 'user123', status: 'online' }
      };

      (service as any).ws.simulateMessage(presenceUpdate);

      expect(mockCallbacks.onPresenceUpdate).toHaveBeenCalledWith(presenceUpdate.data);
      expect(mockCallbacks.onMessage).toHaveBeenCalledWith(presenceUpdate);
    });

    it('should handle error messages', () => {
      const errorMessage: WebSocketMessage = {
        type: 'error',
        data: { message: 'Something went wrong' }
      };

      (service as any).ws.simulateMessage(errorMessage);

      expect(mockCallbacks.onError).toHaveBeenCalledWith(new Error('Something went wrong'));
      expect(mockCallbacks.onMessage).toHaveBeenCalledWith(errorMessage);
    });

    it('should handle pong messages', () => {
      const pongMessage: WebSocketMessage = {
        type: 'pong',
        data: { timestamp: new Date().toISOString() }
      };

      (service as any).ws.simulateMessage(pongMessage);

      expect(mockCallbacks.onMessage).toHaveBeenCalledWith(pongMessage);
      // Should not trigger other callbacks
      expect(mockCallbacks.onTransformationUpdate).not.toHaveBeenCalled();
      expect(mockCallbacks.onPresenceUpdate).not.toHaveBeenCalled();
    });

    it('should handle malformed JSON gracefully', () => {
      const mockWs = (service as any).ws;
      mockWs.onmessage?.(new MessageEvent('message', { data: 'invalid json' }));

      expect(mockCallbacks.onError).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'Failed to parse WebSocket message' })
      );
    });
  });

  describe('sending messages', () => {
    beforeEach(async () => {
      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;
    });

    it('should send messages successfully', () => {
      const mockSend = jest.fn();
      (service as any).ws.send = mockSend;

      const message = {
        type: 'test_message',
        data: { content: 'Hello World' }
      };

      const result = service.send(message);

      expect(result).toBe(true);
      const sent = JSON.parse(mockSend.mock.calls[0][0]);
      expect(sent).toEqual(expect.objectContaining({
        type: 'test_message',
        data: { content: 'Hello World' },
        timestamp: expect.any(String)
      }));
    });

    it('should fail to send when not connected', () => {
      service.disconnect();

      const message = {
        type: 'test_message',
        data: { content: 'Hello World' }
      };

      const result = service.send(message);

      expect(result).toBe(false);
    });

    it('should handle send errors', () => {
      const mockSend = jest.fn(() => {
        throw new Error('Send failed');
      });
      (service as any).ws.send = mockSend;

      const message = {
        type: 'test_message',
        data: { content: 'Hello World' }
      };

      const result = service.send(message);

      expect(result).toBe(false);
      expect(mockCallbacks.onError).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'Send failed' })
      );
    });

    it('should send workspace messages', () => {
      const mockSend = jest.fn();
      (service as any).ws.send = mockSend;

      const messageData = { content: 'Workspace message' };
      const result = service.sendWorkspaceMessage(messageData);

      expect(result).toBe(true);
      const sent = JSON.parse(mockSend.mock.calls[0][0]);
      expect(sent).toEqual(expect.objectContaining({
        type: 'workspace_message',
        data: messageData,
        timestamp: expect.any(String)
      }));
    });

    it('should get workspace presence', () => {
      const mockSend = jest.fn();
      (service as any).ws.send = mockSend;

      service.getWorkspacePresence();

      const sent = JSON.parse(mockSend.mock.calls[0][0]);
      expect(sent).toEqual(expect.objectContaining({
        type: 'get_workspace_presence',
        data: {},
        timestamp: expect.any(String)
      }));
    });
  });

  describe('ping/pong mechanism', () => {
    beforeEach(async () => {
      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;
    });

    it('should send ping messages at configured interval', () => {
      const mockSend = jest.fn();
      (service as any).ws.send = mockSend;

      // Fast forward by ping interval (30 seconds)
      jest.advanceTimersByTime(30000);

      const sent = JSON.parse(mockSend.mock.calls[0][0]);
      expect(sent).toEqual(expect.objectContaining({
        type: 'ping',
        data: { timestamp: expect.any(String) },
        timestamp: expect.any(String)
      }));
    });

    it('should stop ping timer when disconnected', () => {
      const mockSend = jest.fn();
      (service as any).ws.send = mockSend;

      service.disconnect();

      // Fast forward by ping interval
      jest.advanceTimersByTime(30000);

      // Should not have sent ping after disconnect
      expect(mockSend).not.toHaveBeenCalled();
    });
  });

  describe('reconnection', () => {
    it('should attempt to reconnect on unexpected close', async () => {
      const connectSpy = jest.spyOn(service, 'connect');
      
      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;

      // Simulate unexpected close (not code 1000)
      (service as any).ws.simulateClose(1006, 'Connection lost');

      expect(service.getState()).toBe(WebSocketState.DISCONNECTED);

      // Fast forward to trigger reconnect
      jest.advanceTimersByTime(5000);

      expect(connectSpy).toHaveBeenCalledTimes(2); // Initial connect + reconnect
    });

    it('should not reconnect on manual close', async () => {
      const connectSpy = jest.spyOn(service, 'connect');
      
      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      jest.runOnlyPendingTimers();
      await connectPromise;

      // Simulate manual close (code 1000)
      (service as any).ws.simulateClose(1000, 'Manual close');

      // Fast forward past reconnect interval
      jest.advanceTimersByTime(10000);

      expect(connectSpy).toHaveBeenCalledTimes(1); // Only initial connect
    });

    it('should use exponential backoff for reconnection', async () => {
      // Create service with shorter reconnect interval for testing
      service = new WebSocketService({ reconnectInterval: 1000 });
      
      const connectSpy = jest.spyOn(service, 'connect').mockImplementation(() => {
        return Promise.reject(new Error('Connection failed'));
      });

      try {
        await service.connect('test-token', 'workspace123', mockCallbacks);
      } catch (e) {
        // Expected to fail
      }

      // Simulate connection loss to trigger reconnect logic
      (service as any).token = 'test-token';
      (service as any).workspaceId = 'workspace123';
      (service as any).reconnectAttempts = 0;
      (service as any).scheduleReconnect();

      // First reconnect after 1 second
      jest.advanceTimersByTime(1000);
      
      // Second reconnect should be after 2 seconds (exponential backoff)
      (service as any).reconnectAttempts = 1;
      (service as any).scheduleReconnect();
      
      jest.advanceTimersByTime(2000);

      expect(connectSpy).toHaveBeenCalledTimes(3); // Initial + 2 reconnects
    });
  });

  describe('configuration', () => {
    it('should use custom configuration', () => {
      const customConfig = {
        baseUrl: 'ws://custom-url:9000/ws',
        reconnectInterval: 10000,
        maxReconnectAttempts: 10,
        pingInterval: 60000
      };

      service = new WebSocketService(customConfig);

      expect((service as any).config.baseUrl).toBe(customConfig.baseUrl);
      expect((service as any).config.reconnectInterval).toBe(customConfig.reconnectInterval);
      expect((service as any).config.maxReconnectAttempts).toBe(customConfig.maxReconnectAttempts);
      expect((service as any).config.pingInterval).toBe(customConfig.pingInterval);
    });

    it('should use default configuration when not provided', () => {
      service = new WebSocketService();

      expect((service as any).config.baseUrl).toBe('ws://localhost:8000/api/ws');
      expect((service as any).config.reconnectInterval).toBe(5000);
      expect((service as any).config.maxReconnectAttempts).toBe(5);
      expect((service as any).config.pingInterval).toBe(30000);
    });
  });

  describe('state management', () => {
    it('should track connection state correctly', async () => {
      expect(service.getState()).toBe(WebSocketState.DISCONNECTED);
      expect(service.isConnected()).toBe(false);

      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      
      expect(service.getState()).toBe(WebSocketState.CONNECTING);
      expect(service.isConnected()).toBe(false);

      jest.runOnlyPendingTimers();
      await connectPromise;

      expect(service.getState()).toBe(WebSocketState.CONNECTED);
      expect(service.isConnected()).toBe(true);

      service.disconnect();

      expect(service.getState()).toBe(WebSocketState.DISCONNECTED);
      expect(service.isConnected()).toBe(false);
    });

    it('should track error state', async () => {
      // Override WebSocket to simulate error
      global.WebSocket = class extends MockWebSocket {
        constructor(url: string) {
          super(url, false);
          setTimeout(() => {
            this.onerror?.(new Event('error'));
          }, 0);
        }
      } as any;

      service = new WebSocketService();

      const connectPromise = service.connect('test-token', 'workspace123', mockCallbacks);
      jest.runOnlyPendingTimers();

      await expect(connectPromise).rejects.toThrow();
      expect(service.getState()).toBe(WebSocketState.ERROR);
      expect(service.isConnected()).toBe(false);
    });
  });
});

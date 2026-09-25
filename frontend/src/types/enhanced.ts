// Import types for extension
import { Transformation } from './index';

// Re-export existing types
export * from './index';

export interface BaseEntity {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface User extends BaseEntity {
  email: string;
  username: string;
  isActive: boolean;
  preferences: UserPreferences;
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system';
  notifications: {
    email: boolean;
    push: boolean;
    realTime: boolean;
  };
  accessibility: {
    reducedMotion: boolean;
    highContrast: boolean;
    fontSize: 'small' | 'medium' | 'large';
  };
}

export interface TransformationWithProgress extends Transformation {
  progress: number;
  estimatedTimeRemaining?: number;
  realTimeUpdates: boolean;
}

export interface SystemHealth {
  overall: 'healthy' | 'degraded' | 'critical';
  services: ServiceHealth[];
  metrics: SystemMetrics;
  lastChecked: string;
}

export interface ServiceHealth {
  name: string;
  status: 'up' | 'down' | 'degraded';
  responseTime?: number;
  details?: Record<string, any>;
}

export interface SystemMetrics {
  cpu: number;
  memory: number;
  activeConnections: number;
  requestsPerMinute: number;
  errorRate: number;
}

// Utility types for enhanced development
export type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: Error | null;
};

export type OptimisticUpdate<T> = {
  id: string;
  data: T;
  timestamp: number;
  confirmed: boolean;
};

// Re-export existing types for backward compatibility
export * from './index';
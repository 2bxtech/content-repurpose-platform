import api from './authService';
import { Transformation, TransformationList, TransformationCreate, TransformationType } from '../types';

// Transformation API calls
export const createTransformation = async (transformationData: TransformationCreate): Promise<Transformation> => {
  const response = await api.post<Transformation>('/transformations', transformationData);
  return response.data;
};

export interface QuickTransformRequest {
  content: string;
  transformation_type: TransformationType;
  title?: string;
  parameters?: Record<string, unknown>;
  preset_id?: string;
}

export const quickTransform = async (request: QuickTransformRequest): Promise<Transformation> => {
  const response = await api.post<Transformation>('/transformations/quick', request);
  return response.data;
};

export const getUserTransformations = async (): Promise<TransformationList> => {
  const response = await api.get<TransformationList>('/transformations');
  return response.data;
};

export const getTransformation = async (id: string): Promise<Transformation> => {
  const response = await api.get<Transformation>(`/transformations/${id}`);
  return response.data;
};

export const deleteTransformation = async (id: string): Promise<void> => {
  await api.delete(`/transformations/${id}`);
};

export const refineTransformation = async (id: string, instruction: string): Promise<Transformation> => {
  const response = await api.post<Transformation>(`/transformations/${id}/refine`, { instruction });
  return response.data;
};

// Real-time status checking (fallback for non-WebSocket scenarios)
export const getTransformationStatus = async (id: string) => {
  const response = await api.get(`/transformations/${id}/status`);
  return response.data;
};

// Cancel transformation
export const cancelTransformation = async (id: string) => {
  const response = await api.post(`/transformations/${id}/cancel`);
  return response.data;
};

// Polling utility for status updates (fallback when WebSocket is not available)
export const pollTransformationStatus = (
  transformationId: string,
  onUpdate: (status: any) => void,
  onComplete: (finalStatus: any) => void,
  interval: number = 2000
) => {
  let polling = true;
  let timer: ReturnType<typeof setTimeout> | null = null;
  
  const poll = async () => {
    if (!polling) return;
    
    try {
      const status = await getTransformationStatus(transformationId);
      onUpdate(status);
      
      // Check if transformation is complete
      const databaseStatus = String(status.database_status || '').toUpperCase();
      if (databaseStatus === 'COMPLETED' || databaseStatus === 'FAILED') {
        polling = false;
        onComplete(status);
        return;
      }
      
      // Continue polling
      timer = setTimeout(poll, interval);
    } catch (error) {
      console.error('Error polling transformation status:', error);
      // Continue polling even on error, unless explicitly stopped
      if (polling) {
        timer = setTimeout(poll, interval * 2); // Back off on error
      }
    }
  };
  
  // Start polling
  timer = setTimeout(poll, 0);
  
  // Return stop function
  return () => {
    polling = false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
};

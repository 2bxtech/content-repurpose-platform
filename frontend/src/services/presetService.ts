import api from './authService';
import { PresetResponse, PresetList, PresetCreate, PresetUpdate } from '../types';

/**
 * Transformation Preset API Service
 * Handles all CRUD operations for transformation presets
 */

// List all accessible presets (personal + shared)
export const getPresets = async (): Promise<PresetList> => {
  const response = await api.get<PresetList>('/transformation-presets');
  return response.data;
};

// Get single preset by ID
export const getPreset = async (id: string): Promise<PresetResponse> => {
  const response = await api.get<PresetResponse>(`/transformation-presets/${id}`);
  return response.data;
};

// Create new preset
export const createPreset = async (data: PresetCreate): Promise<PresetResponse> => {
  const response = await api.post<PresetResponse>('/transformation-presets', data);
  return response.data;
};

// Update existing preset (owner only)
export const updatePreset = async (id: string, data: PresetUpdate): Promise<PresetResponse> => {
  const response = await api.patch<PresetResponse>(`/transformation-presets/${id}`, data);
  return response.data;
};

// Delete preset (owner only)
export const deletePreset = async (id: string): Promise<void> => {
  await api.delete(`/transformation-presets/${id}`);
};

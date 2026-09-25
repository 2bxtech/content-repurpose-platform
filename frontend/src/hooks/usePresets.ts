import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  getPresets, 
  getPreset, 
  createPreset, 
  updatePreset, 
  deletePreset 
} from '../services/presetService';
import { PresetCreate, PresetUpdate } from '../types';
import toast from 'react-hot-toast';

/**
 * React Query hooks for transformation presets
 */

// Query key factory
export const presetKeys = {
  all: ['presets'] as const,
  lists: () => [...presetKeys.all, 'list'] as const,
  list: () => [...presetKeys.lists()] as const,
  details: () => [...presetKeys.all, 'detail'] as const,
  detail: (id: string) => [...presetKeys.details(), id] as const,
};

// Fetch all presets
export const usePresets = () => {
  return useQuery({
    queryKey: presetKeys.list(),
    queryFn: getPresets,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

// Fetch single preset
export const usePreset = (id: string) => {
  return useQuery({
    queryKey: presetKeys.detail(id),
    queryFn: () => getPreset(id),
    enabled: !!id,
  });
};

// Create preset
export const useCreatePreset = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data: PresetCreate) => createPreset(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: presetKeys.list() });
      toast.success('Preset created successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to create preset';
      toast.error(message);
    },
  });
};

// Update preset
export const useUpdatePreset = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PresetUpdate }) => 
      updatePreset(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: presetKeys.list() });
      queryClient.invalidateQueries({ queryKey: presetKeys.detail(variables.id) });
      toast.success('Preset updated successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to update preset';
      toast.error(message);
    },
  });
};

// Delete preset
export const useDeletePreset = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id: string) => deletePreset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: presetKeys.list() });
      toast.success('Preset deleted successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to delete preset';
      toast.error(message);
    },
  });
};

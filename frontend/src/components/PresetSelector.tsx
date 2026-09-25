import React from 'react';
import {
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Box,
  Typography,
  Chip,
  CircularProgress,
  Alert,
  SelectChangeEvent
} from '@mui/material';
import { TransformationType, PresetResponse } from '../types';
import { usePresets } from '../hooks/usePresets';

interface PresetSelectorProps {
  transformationType: TransformationType;
  selectedPresetId?: string;
  onPresetSelect: (presetId: string | null, preset: PresetResponse | null) => void;
  disabled?: boolean;
}

const PresetSelector: React.FC<PresetSelectorProps> = ({
  transformationType,
  selectedPresetId,
  onPresetSelect,
  disabled = false,
}) => {
  const { data: presetsData, isLoading, error } = usePresets();
  
  // Filter presets by transformation type
  const filteredPresets = React.useMemo(() => {
    if (!presetsData?.presets) return [];
    return presetsData.presets.filter(
      preset => preset.transformation_type === transformationType
    );
  }, [presetsData, transformationType]);
  
  const handleChange = (event: SelectChangeEvent) => {
    const presetId = event.target.value;
    if (presetId === '') {
      onPresetSelect(null, null);
    } else {
      const preset = filteredPresets.find(p => p.id === presetId);
      onPresetSelect(presetId, preset || null);
    }
  };
  
  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, my: 2 }}>
        <CircularProgress size={20} />
        <Typography variant="body2" color="text.secondary">
          Loading presets...
        </Typography>
      </Box>
    );
  }
  
  if (error) {
    return (
      <Alert severity="warning" sx={{ my: 2 }}>
        Failed to load presets. You can still create a transformation manually.
      </Alert>
    );
  }
  
  if (filteredPresets.length === 0) {
    return (
      <Alert severity="info" sx={{ my: 2 }}>
        No presets available for this transformation type. Create one to save time in the future!
      </Alert>
    );
  }
  
  const selectedPreset = filteredPresets.find(p => p.id === selectedPresetId);
  
  return (
    <Box sx={{ my: 2 }}>
      <FormControl fullWidth>
        <InputLabel id="preset-selector-label">Use Preset (Optional)</InputLabel>
        <Select
          labelId="preset-selector-label"
          value={selectedPresetId || ''}
          label="Use Preset (Optional)"
          onChange={handleChange}
          disabled={disabled}
        >
          <MenuItem value="">
            <em>None - Enter parameters manually</em>
          </MenuItem>
          {filteredPresets.map((preset) => (
            <MenuItem key={preset.id} value={preset.id}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                <Typography>{preset.name}</Typography>
                {preset.is_shared && (
                  <Chip label="Shared" size="small" color="primary" variant="outlined" />
                )}
                <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                  Used {preset.usage_count} times
                </Typography>
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      
      {selectedPreset && (
        <Box sx={{ mt: 1, p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary">
            <strong>Preset:</strong> {selectedPreset.name}
          </Typography>
          {selectedPreset.description && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {selectedPreset.description}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            You can override any preset parameters below.
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default PresetSelector;

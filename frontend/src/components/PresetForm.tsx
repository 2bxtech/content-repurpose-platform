import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Checkbox,
  Box,
  Alert,
  SelectChangeEvent
} from '@mui/material';
import { TransformationType, PresetCreate, PresetUpdate, PresetResponse } from '../types';

interface PresetFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: PresetCreate | PresetUpdate) => void;
  initialData?: PresetResponse;
  mode: 'create' | 'edit';
  loading?: boolean;
  transformationType?: TransformationType; // For pre-selecting type in create mode
  initialParameters?: Record<string, any>; // For "Save as Preset" from transformation form
}

const PresetForm: React.FC<PresetFormProps> = ({
  open,
  onClose,
  onSubmit,
  initialData,
  mode,
  loading = false,
  transformationType,
  initialParameters,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedType, setSelectedType] = useState<TransformationType>(
    transformationType || TransformationType.BLOG_POST
  );
  const [parameters, setParameters] = useState('{}');
  const [isShared, setIsShared] = useState(false);
  const [error, setError] = useState('');
  
  // Initialize form with existing data or initial values
  useEffect(() => {
    if (mode === 'edit' && initialData) {
      setName(initialData.name);
      setDescription(initialData.description || '');
      setSelectedType(initialData.transformation_type);
      setParameters(JSON.stringify(initialData.parameters, null, 2));
      setIsShared(initialData.is_shared);
    } else if (mode === 'create') {
      // For "Save as Preset" functionality
      if (transformationType) {
        setSelectedType(transformationType);
      }
      if (initialParameters) {
        setParameters(JSON.stringify(initialParameters, null, 2));
      }
    }
  }, [mode, initialData, transformationType, initialParameters]);
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    // Validate parameters JSON
    let parsedParameters: Record<string, any>;
    try {
      parsedParameters = JSON.parse(parameters);
      if (typeof parsedParameters !== 'object' || Array.isArray(parsedParameters)) {
        throw new Error('Parameters must be a JSON object');
      }
    } catch (err) {
      setError('Invalid JSON in parameters field');
      return;
    }
    
    if (mode === 'create') {
      const data: PresetCreate = {
        name: name.trim(),
        description: description.trim() || undefined,
        transformation_type: selectedType,
        parameters: parsedParameters,
        is_shared: isShared,
      };
      onSubmit(data);
    } else {
      const data: PresetUpdate = {
        name: name.trim(),
        description: description.trim() || undefined,
        parameters: parsedParameters,
        is_shared: isShared,
      };
      onSubmit(data);
    }
  };
  
  const handleTypeChange = (event: SelectChangeEvent) => {
    setSelectedType(event.target.value as TransformationType);
  };
  
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle>
          {mode === 'create' ? 'Create New Preset' : 'Edit Preset'}
        </DialogTitle>
        
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          
          <TextField
            label="Preset Name"
            fullWidth
            required
            margin="normal"
            value={name}
            onChange={(e) => setName(e.target.value)}
            helperText="A descriptive name for this preset"
          />
          
          <TextField
            label="Description (Optional)"
            fullWidth
            multiline
            rows={2}
            margin="normal"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            helperText="Describe what this preset is for"
          />
          
          <FormControl fullWidth margin="normal" required disabled={mode === 'edit'}>
            <InputLabel>Transformation Type</InputLabel>
            <Select
              value={selectedType}
              label="Transformation Type"
              onChange={handleTypeChange}
            >
              <MenuItem value={TransformationType.BLOG_POST}>Blog Post</MenuItem>
              <MenuItem value={TransformationType.SOCIAL_MEDIA}>Social Media Content</MenuItem>
              <MenuItem value={TransformationType.EMAIL_SEQUENCE}>Email Sequence</MenuItem>
              <MenuItem value={TransformationType.NEWSLETTER}>Newsletter</MenuItem>
              <MenuItem value={TransformationType.SUMMARY}>Summary</MenuItem>
              <MenuItem value={TransformationType.CUSTOM}>Custom</MenuItem>
            </Select>
            {mode === 'edit' && (
              <Box sx={{ mt: 0.5, fontSize: '0.75rem', color: 'text.secondary' }}>
                Transformation type cannot be changed after creation
              </Box>
            )}
          </FormControl>
          
          <TextField
            label="Parameters (JSON)"
            fullWidth
            required
            multiline
            rows={8}
            margin="normal"
            value={parameters}
            onChange={(e) => setParameters(e.target.value)}
            helperText='JSON object with transformation parameters, e.g., {"tone": "professional", "word_count": 800}'
            sx={{ fontFamily: 'monospace' }}
          />
          
          <FormControlLabel
            control={
              <Checkbox
                checked={isShared}
                onChange={(e) => setIsShared(e.target.checked)}
              />
            }
            label="Share with workspace members"
            sx={{ mt: 2 }}
          />
        </DialogContent>
        
        <DialogActions>
          <Button onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={loading}>
            {loading ? 'Saving...' : mode === 'create' ? 'Create' : 'Update'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default PresetForm;

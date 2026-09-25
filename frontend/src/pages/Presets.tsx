import React, { useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Paper,
  Button,
  Grid,
  Card,
  CardContent,
  CardActions,
  Chip,
  IconButton,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Share as ShareIcon,
  Person as PersonIcon
} from '@mui/icons-material';
import { usePresets, useCreatePreset, useUpdatePreset, useDeletePreset } from '../hooks/usePresets';
import { PresetCreate, PresetUpdate, PresetResponse, TransformationType } from '../types';
import PresetForm from '../components/PresetForm';

const transformationTypeLabels: Record<TransformationType, string> = {
  [TransformationType.BLOG_POST]: 'Blog Post',
  [TransformationType.SOCIAL_MEDIA]: 'Social Media',
  [TransformationType.EMAIL_SEQUENCE]: 'Email Sequence',
  [TransformationType.NEWSLETTER]: 'Newsletter',
  [TransformationType.SUMMARY]: 'Summary',
  [TransformationType.CUSTOM]: 'Custom',
};

const PresetsPage: React.FC = () => {
  const { data: presetsData, isLoading, error } = usePresets();
  const createMutation = useCreatePreset();
  const updateMutation = useUpdatePreset();
  const deleteMutation = useDeletePreset();
  
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');
  const [selectedPreset, setSelectedPreset] = useState<PresetResponse | undefined>();
  
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [presetToDelete, setPresetToDelete] = useState<PresetResponse | null>(null);
  
  const handleCreateClick = () => {
    setFormMode('create');
    setSelectedPreset(undefined);
    setFormOpen(true);
  };
  
  const handleEditClick = (preset: PresetResponse) => {
    setFormMode('edit');
    setSelectedPreset(preset);
    setFormOpen(true);
  };
  
  const handleDeleteClick = (preset: PresetResponse) => {
    setPresetToDelete(preset);
    setDeleteDialogOpen(true);
  };
  
  const handleFormSubmit = async (data: PresetCreate | PresetUpdate) => {
    if (formMode === 'create') {
      await createMutation.mutateAsync(data as PresetCreate);
      setFormOpen(false);
    } else if (formMode === 'edit' && selectedPreset) {
      await updateMutation.mutateAsync({ id: selectedPreset.id, data: data as PresetUpdate });
      setFormOpen(false);
    }
  };
  
  const handleDeleteConfirm = async () => {
    if (presetToDelete) {
      await deleteMutation.mutateAsync(presetToDelete.id);
      setDeleteDialogOpen(false);
      setPresetToDelete(null);
    }
  };
  
  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
        <CircularProgress />
      </Box>
    );
  }
  
  if (error) {
    return (
      <Container maxWidth="lg">
        <Alert severity="error" sx={{ mt: 4 }}>
          Failed to load presets. Please try again later.
        </Alert>
      </Container>
    );
  }
  
  const presets = presetsData?.presets || [];
  
  return (
    <Container maxWidth="lg">
      <Box sx={{ mt: 4, mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
          <Box>
            <Typography variant="h4" component="h1" gutterBottom>
              Transformation Presets
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Save and reuse transformation configurations to speed up your workflow
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleCreateClick}
          >
            Create Preset
          </Button>
        </Box>
        
        {presets.length === 0 ? (
          <Paper sx={{ p: 6, textAlign: 'center' }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No presets yet
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Create your first preset to save time on future transformations
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleCreateClick}
            >
              Create Your First Preset
            </Button>
          </Paper>
        ) : (
          <Grid container spacing={3}>
            {presets.map((preset) => (
              <Grid item xs={12} md={6} lg={4} key={preset.id}>
                <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="h6" component="h2" sx={{ flexGrow: 1 }}>
                        {preset.name}
                      </Typography>
                      {preset.is_shared ? (
                        <Chip
                          icon={<ShareIcon />}
                          label="Shared"
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                      ) : (
                        <Chip
                          icon={<PersonIcon />}
                          label="Private"
                          size="small"
                          variant="outlined"
                        />
                      )}
                    </Box>
                    
                    <Chip
                      label={transformationTypeLabels[preset.transformation_type]}
                      size="small"
                      sx={{ mb: 2 }}
                    />
                    
                    {preset.description && (
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {preset.description}
                      </Typography>
                    )}
                    
                    <Divider sx={{ my: 2 }} />
                    
                    <Typography variant="caption" color="text.secondary" display="block">
                      Used {preset.usage_count} times
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Created {new Date(preset.created_at).toLocaleDateString()}
                    </Typography>
                  </CardContent>
                  
                  <CardActions sx={{ justifyContent: 'flex-end', p: 2, pt: 0 }}>
                    <IconButton
                      size="small"
                      onClick={() => handleEditClick(preset)}
                      title="Edit preset"
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => handleDeleteClick(preset)}
                      title="Delete preset"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </CardActions>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
      
      {/* Create/Edit Form Dialog */}
      <PresetForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={handleFormSubmit}
        initialData={selectedPreset}
        mode={formMode}
        loading={createMutation.isLoading || updateMutation.isLoading}
      />
      
      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Preset?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete "{presetToDelete?.name}"? This action cannot be undone.
          </Typography>
          {presetToDelete && presetToDelete.usage_count > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              This preset has been used {presetToDelete.usage_count} times. Deleting it won't affect existing transformations.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleDeleteConfirm}
            color="error"
            variant="contained"
            disabled={deleteMutation.isLoading}
          >
            {deleteMutation.isLoading ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default PresetsPage;

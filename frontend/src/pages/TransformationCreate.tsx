import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container, Typography, Box, Paper, FormControl, InputLabel,
  MenuItem, Select, TextField, Button, Alert, CircularProgress,
  Divider, SelectChangeEvent, IconButton, Tooltip} from '@mui/material';
import { Save as SaveIcon } from '@mui/icons-material';
import { getDocument } from '../services/documentService';
import { createTransformation } from '../services/transformationService';
import { getErrorMessage } from '../utils/apiError';
import { TransformationType, Document, PresetResponse } from '../types';
import type { TransformationCreate } from '../types';
import PresetSelector from '../components/PresetSelector';
import PresetForm from '../components/PresetForm';
import { useCreatePreset } from '../hooks/usePresets';

const TransformationCreatePage: React.FC = () => {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  
  const [document, setDocument] = useState<Document | null>(null);
  const [transformationType, setTransformationType] = useState<TransformationType>(TransformationType.BLOG_POST);
  const [parameters, setParameters] = useState<Record<string, any>>({});
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  
  const [loading, setLoading] = useState(false);
  const [documentLoading, setDocumentLoading] = useState(true);
  const [error, setError] = useState('');
  
  // "Save as Preset" dialog state
  const [savePresetDialogOpen, setSavePresetDialogOpen] = useState(false);
  const createPresetMutation = useCreatePreset();

  useEffect(() => {
    const fetchDocument = async () => {
      if (!documentId) return;
      
      try {
        setDocumentLoading(true);
        const fetchedDocument = await getDocument(documentId);
        setDocument(fetchedDocument);
      } catch (err: any) {
        console.error('Error fetching document:', err);
        setError('Failed to load document details.');
      } finally {
        setDocumentLoading(false);
      }
    };

    fetchDocument();
  }, [documentId]);

  const getInitialParameters = (type: TransformationType) => {
    switch (type) {
      case TransformationType.BLOG_POST:
        return { word_count: 800, tone: 'professional' };
      case TransformationType.SOCIAL_MEDIA:
        return { platform: 'twitter', post_count: 3 };
      case TransformationType.EMAIL_SEQUENCE:
        return { email_count: 3 };
      case TransformationType.NEWSLETTER:
        return { sections: ['introduction', 'main_content', 'conclusion'] };
      case TransformationType.SUMMARY:
        return { length: 300 };
      case TransformationType.CUSTOM:
        return { custom_instructions: '' };
      default:
        return {};
    }
  };

  const handleTransformationTypeChange = (event: SelectChangeEvent) => {
    const newType = event.target.value as TransformationType;
    setTransformationType(newType);
    setParameters(getInitialParameters(newType));
    // Reset preset selection when type changes
    setSelectedPresetId(null);
  };
  
  const handlePresetSelect = (presetId: string | null, preset: PresetResponse | null) => {
    setSelectedPresetId(presetId);
    
    if (preset) {
      // Apply preset parameters (preset values override any existing form values)
      setParameters({ ...preset.parameters });
    } else {
      // If no preset selected, reset to default parameters for current type
      setParameters(getInitialParameters(transformationType));
    }
  };
  
  const handleSaveAsPreset = () => {
    setSavePresetDialogOpen(true);
  };
  
  const handlePresetFormSubmit = async (data: any) => {
    await createPresetMutation.mutateAsync(data);
    setSavePresetDialogOpen(false);
  };

  const handleParameterChange = (key: string, value: any) => {
    setParameters(prev => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!document || !documentId) {
      setError('Document not found');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      const transformationData: TransformationCreate = {
        document_id: document.id,
        transformation_type: transformationType,
        parameters: parameters,
        preset_id: selectedPresetId || undefined
      };
      
      const result = await createTransformation(transformationData);
      navigate(`/transformations/${result.id}`);
    } catch (err: any) {
      console.error('Error creating transformation:', err);
      
      setError(getErrorMessage(err, 'Failed to create transformation. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const renderParametersForm = () => {
    switch (transformationType) {
      case TransformationType.BLOG_POST:
        return (
          <>
            <TextField
              label="Word Count"
              type="number"
              fullWidth
              margin="normal"
              value={parameters.word_count || ''}
              onChange={(e) => handleParameterChange('word_count', parseInt(e.target.value))}
              InputProps={{ inputProps: { min: 300, max: 3000 } }}
              helperText="Target word count for the blog post (300-3000)"
            />
            <FormControl fullWidth margin="normal">
              <InputLabel>Tone</InputLabel>
              <Select
                value={parameters.tone || ''}
                label="Tone"
                onChange={(e) => handleParameterChange('tone', e.target.value)}
              >
                <MenuItem value="professional">Professional</MenuItem>
                <MenuItem value="casual">Casual</MenuItem>
                <MenuItem value="academic">Academic</MenuItem>
                <MenuItem value="friendly">Friendly</MenuItem>
                <MenuItem value="persuasive">Persuasive</MenuItem>
              </Select>
            </FormControl>
          </>
        );
        
      case TransformationType.SOCIAL_MEDIA:
        return (
          <>
            <FormControl fullWidth margin="normal">
              <InputLabel>Platform</InputLabel>
              <Select
                value={parameters.platform || ''}
                label="Platform"
                onChange={(e) => handleParameterChange('platform', e.target.value)}
              >
                <MenuItem value="twitter">Twitter</MenuItem>
                <MenuItem value="instagram">Instagram</MenuItem>
                <MenuItem value="linkedin">LinkedIn</MenuItem>
                <MenuItem value="facebook">Facebook</MenuItem>
              </Select>
            </FormControl>
            <TextField
              label="Number of Posts"
              type="number"
              fullWidth
              margin="normal"
              value={parameters.post_count || ''}
              onChange={(e) => handleParameterChange('post_count', parseInt(e.target.value))}
              InputProps={{ inputProps: { min: 1, max: 10 } }}
              helperText="Number of social media posts to generate (1-10)"
            />
          </>
        );
        
      case TransformationType.EMAIL_SEQUENCE:
        return (
          <TextField
            label="Number of Emails"
            type="number"
            fullWidth
            margin="normal"
            value={parameters.email_count || ''}
            onChange={(e) => handleParameterChange('email_count', parseInt(e.target.value))}
            InputProps={{ inputProps: { min: 1, max: 7 } }}
            helperText="Number of emails in the sequence (1-7)"
          />
        );
        
      case TransformationType.NEWSLETTER:
        return (
          <TextField
            label="Sections"
            fullWidth
            margin="normal"
            value={parameters.sections?.join(', ') || ''}
            onChange={(e) => handleParameterChange('sections', e.target.value.split(',').map(s => s.trim()))}
            helperText="Comma-separated list of sections to include in the newsletter"
          />
        );
        
      case TransformationType.SUMMARY:
        return (
          <TextField
            label="Length (words)"
            type="number"
            fullWidth
            margin="normal"
            value={parameters.length || ''}
            onChange={(e) => handleParameterChange('length', parseInt(e.target.value))}
            InputProps={{ inputProps: { min: 100, max: 1000 } }}
            helperText="Target word count for the summary (100-1000)"
          />
        );
        
      case TransformationType.CUSTOM:
        return (
          <TextField
            label="Custom Instructions"
            fullWidth
            multiline
            rows={4}
            margin="normal"
            value={parameters.custom_instructions || ''}
            onChange={(e) => handleParameterChange('custom_instructions', e.target.value)}
            helperText="Detailed instructions for how to transform the content"
          />
        );
        
      default:
        return null;
    }
  };

  if (documentLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!document && !documentLoading) {
    return (
      <Container maxWidth="md">
        <Alert severity="error" sx={{ mt: 4 }}>
          Document not found or you don't have permission to access it.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="md">
      <Paper elevation={3} sx={{ p: 4, mt: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Create Transformation
        </Typography>
        
        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}
        
        {document && (
          <Box sx={{ mb: 3 }}>
            <Typography variant="h6">Source Document</Typography>
            <Typography variant="body1">{document.title}</Typography>
            {document.description && (
              <Typography variant="body2" color="text.secondary">
                {document.description}
              </Typography>
            )}
          </Box>
        )}
        
        <Divider sx={{ mb: 3 }} />
        
        <Box component="form" onSubmit={handleSubmit}>
          <FormControl fullWidth margin="normal">
            <InputLabel>Transformation Type</InputLabel>
            <Select
              value={transformationType}
              label="Transformation Type"
              onChange={handleTransformationTypeChange}
            >
              <MenuItem value={TransformationType.BLOG_POST}>Blog Post</MenuItem>
              <MenuItem value={TransformationType.SOCIAL_MEDIA}>Social Media Content</MenuItem>
              <MenuItem value={TransformationType.EMAIL_SEQUENCE}>Email Sequence</MenuItem>
              <MenuItem value={TransformationType.NEWSLETTER}>Newsletter</MenuItem>
              <MenuItem value={TransformationType.SUMMARY}>Summary</MenuItem>
              <MenuItem value={TransformationType.CUSTOM}>Custom</MenuItem>
            </Select>
          </FormControl>
          
          <PresetSelector
            transformationType={transformationType}
            selectedPresetId={selectedPresetId || undefined}
            onPresetSelect={handlePresetSelect}
            disabled={loading}
          />
          
          <Box sx={{ mt: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="h6">Parameters</Typography>
            <Tooltip title="Save current parameters as a preset for future use">
              <IconButton
                size="small"
                onClick={handleSaveAsPreset}
                color="primary"
              >
                <SaveIcon />
              </IconButton>
            </Tooltip>
          </Box>
          <Box sx={{ mt: 1 }}>
            {renderParametersForm()}
          </Box>
          
          <Button
            type="submit"
            variant="contained"
            color="primary"
            disabled={loading}
            sx={{ mt: 4 }}
          >
            {loading ? <CircularProgress size={24} /> : 'Create Transformation'}
          </Button>
        </Box>
      </Paper>
      
      {/* Save as Preset Dialog */}
      <PresetForm
        open={savePresetDialogOpen}
        onClose={() => setSavePresetDialogOpen(false)}
        onSubmit={handlePresetFormSubmit}
        mode="create"
        loading={createPresetMutation.isLoading}
        transformationType={transformationType}
        initialParameters={parameters}
      />
    </Container>
  );
};

export default TransformationCreatePage;

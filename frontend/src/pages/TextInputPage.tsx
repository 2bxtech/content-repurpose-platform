import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Paper,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { createTextDocument } from '../services/documentService';
import { getErrorMessage } from '../utils/apiError';

const MIN_CONTENT_LENGTH = 20;

const TextInputPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const presetId = searchParams.get('preset_id') ?? undefined;
  const transformationType = searchParams.get('type') ?? undefined;

  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isValid = title.trim().length > 0 && content.trim().length >= MIN_CONTENT_LENGTH;

  const handleSubmit = async () => {
    if (!isValid) return;
    setSubmitting(true);
    setError('');
    try {
      const doc = await createTextDocument(title.trim(), content.trim(), description.trim() || undefined);
      // Navigate to transformation create, forwarding preset/type hints if present
      const params = new URLSearchParams();
      if (presetId) params.set('preset_id', presetId);
      if (transformationType) params.set('type', transformationType);
      const query = params.toString() ? `?${params.toString()}` : '';
      navigate(`/transformations/create/${doc.id}${query}`);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Failed to create document. Please try again.'));
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 720, mx: 'auto', mt: 4 }}>
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate('/')}
        sx={{ mb: 2, textTransform: 'none' }}
      >
        Back
      </Button>

      <Paper elevation={2} sx={{ p: 4 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          Paste your content
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Give it a title, paste or type your content, then choose a transformation.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <TextField
          label="Title"
          fullWidth
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Q3 product update"
          sx={{ mb: 2 }}
          inputProps={{ maxLength: 255 }}
        />

        <TextField
          label="Content"
          fullWidth
          required
          multiline
          rows={12}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste or type your content here..."
          helperText={
            content.trim().length < MIN_CONTENT_LENGTH && content.length > 0
              ? `${MIN_CONTENT_LENGTH - content.trim().length} more characters needed`
              : `${content.trim().split(/\s+/).filter(Boolean).length} words`
          }
          sx={{ mb: 2 }}
        />

        <TextField
          label="Description (optional)"
          fullWidth
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Add a note about this content"
          sx={{ mb: 3 }}
          inputProps={{ maxLength: 500 }}
        />

        <Button
          variant="contained"
          size="large"
          fullWidth
          disabled={!isValid || submitting}
          onClick={handleSubmit}
          sx={{ py: 1.5 }}
        >
          {submitting ? (
            <CircularProgress size={22} color="inherit" />
          ) : (
            'Continue to Transform →'
          )}
        </Button>
      </Paper>
    </Box>
  );
};

export default TextInputPage;

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
import LinkIcon from '@mui/icons-material/Link';
import { createUrlDocument } from '../services/documentService';
import { getErrorMessage } from '../utils/apiError';

const UrlInputPage: React.FC = () => {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isValidUrl = (value: string) => {
    try {
      const u = new URL(value.trim());
      return u.protocol === 'http:' || u.protocol === 'https:';
    } catch {
      return false;
    }
  };

  const isValid = isValidUrl(url);

  const handleSubmit = async () => {
    if (!isValid || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const doc = await createUrlDocument(url.trim(), title.trim() || undefined);
      navigate(`/transformations/create/${doc.id}`);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Failed to fetch URL. Please check the address and try again.'));
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
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <LinkIcon color="primary" />
          <Typography variant="h5" fontWeight={700}>
            Fetch a URL
          </Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Enter any public web page. We'll extract the text and let you transform it.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <TextField
          label="URL"
          fullWidth
          required
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder="https://example.com/article"
          error={url.length > 0 && !isValid}
          helperText={url.length > 0 && !isValid ? 'Enter a valid http:// or https:// URL' : ' '}
          sx={{ mb: 2 }}
        />

        <TextField
          label="Title (optional)"
          fullWidth
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Auto-detected from page if left blank"
          inputProps={{ maxLength: 255 }}
          sx={{ mb: 3 }}
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
            <>
              <CircularProgress size={20} color="inherit" sx={{ mr: 1 }} />
              Fetching…
            </>
          ) : (
            'Fetch & Transform →'
          )}
        </Button>
      </Paper>
    </Box>
  );
};

export default UrlInputPage;

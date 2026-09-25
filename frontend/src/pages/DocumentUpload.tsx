import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container, Typography, Box, Button, TextField, Paper,
  Alert, CircularProgress, FormHelperText
} from '@mui/material';
import { uploadDocument } from '../services/documentService';

const DocumentUpload: React.FC = () => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      const file = event.target.files[0];
      setSelectedFile(file);
    }
  };

  const validateForm = () => {
    if (!title) {
      setError('Title is required');
      return false;
    }

    if (!selectedFile) {
      setError('Please select a file to upload');
      return false;
    }

    // Check file extension
    const allowedExtensions = ['pdf', 'docx', 'txt', 'md'];
    const fileNameParts = selectedFile.name.split('.');
    const fileExt = fileNameParts.length > 1 ? fileNameParts.pop()?.toLowerCase() : '';

    if (!fileExt || !allowedExtensions.includes(fileExt)) {
      setError(`File type not supported. Allowed types: ${allowedExtensions.join(', ')}`);
      return false;
    }

    // Check file size (10MB max)
    const maxSize = 10 * 1024 * 1024; // 10MB in bytes
    if (selectedFile.size > maxSize) {
      setError('File is too large. Maximum size is 10MB');
      return false;
    }

    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!validateForm()) {
      return;
    }

    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('title', title);
      if (description) {
        formData.append('description', description);
      }
      if (selectedFile) {
        formData.append('file', selectedFile);
      }

      const response = await uploadDocument(formData);
      navigate(`/documents/${response.id}`);
    } catch (err: any) {
      console.error('Upload error:', err);
      
      // Handle validation errors properly
      let errorMessage = 'Failed to upload document. Please try again.';
      
      if (err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (Array.isArray(detail)) {
          // FastAPI validation errors - extract the first error message
          errorMessage = detail[0]?.msg || errorMessage;
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        }
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="md">
      <Paper elevation={3} sx={{ p: 4, mt: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Upload Document
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSubmit}>
          <TextField
            label="Document Title"
            variant="outlined"
            fullWidth
            required
            margin="normal"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />

          <TextField
            label="Description (Optional)"
            variant="outlined"
            fullWidth
            multiline
            rows={3}
            margin="normal"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />

          <Box sx={{ mt: 3, mb: 3 }}>
            <input
              accept=".pdf,.docx,.txt,.md"
              style={{ display: 'none' }}
              id="file-upload"
              type="file"
              onChange={handleFileChange}
            />
            <label htmlFor="file-upload">
              <Button variant="outlined" component="span">
                Select File
              </Button>
            </label>

            {selectedFile && (
              <Typography variant="body2" sx={{ mt: 1 }}>
                Selected file: {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
              </Typography>
            )}

            <FormHelperText>
              Supported file types: PDF, DOCX, TXT, MD. Maximum size: 10MB
            </FormHelperText>
          </Box>

          <Button
            type="submit"
            variant="contained"
            color="primary"
            disabled={loading}
            sx={{ mt: 2 }}
          >
            {loading ? <CircularProgress size={24} /> : 'Upload Document'}
          </Button>
        </Box>
      </Paper>
    </Container>
  );
};

export default DocumentUpload;
import React, { useState, useEffect } from 'react';
import { useParams, Link as RouterLink } from 'react-router-dom';
import {
  Container, Typography, Box, Paper, Button, Divider,
  Grid, Card, CardContent, CardActions, Chip, CircularProgress,
  Alert
} from '@mui/material';
import { getDocument } from '../services/documentService';
import { getUserTransformations } from '../services/transformationService';
import { Document, DocumentStatus, Transformation } from '../types';

const DocumentDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [document, setDocument] = useState<Document | null>(null);
  const [transformations, setTransformations] = useState<Transformation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      
      try {
        setLoading(true);
        const documentData = await getDocument(id);
        setDocument(documentData);
        
        const transformationsData = await getUserTransformations();
        // Filter for transformations related to this document
        const documentTransformations = transformationsData.transformations.filter(
          t => t.document_id === id
        );
        setTransformations(documentTransformations);
      } catch (err: any) {
        console.error('Error fetching document:', err);
        setError('Failed to load document details.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [id]);

  const getStatusColor = (status: DocumentStatus) => {
    switch (status) {
      case 'COMPLETED':
        return 'success';
      case 'PROCESSING':
        return 'warning';
      case 'FAILED':
        return 'error';
      default:
        return 'default';
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!document && !loading) {
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
      {error && (
        <Alert severity="error" sx={{ mt: 4, mb: 2 }}>
          {error}
        </Alert>
      )}
      
      {document && (
        <Paper elevation={3} sx={{ p: 4, mt: 4 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={8}>
              <Typography variant="h4" component="h1" gutterBottom>
                {document.title}
              </Typography>
            </Grid>
            <Grid item xs={12} sm={4} sx={{ textAlign: { sm: 'right' } }}>
              <Chip 
                label={document.status} 
                color={getStatusColor(document.status)} 
              />
            </Grid>
          </Grid>
          
          {document.description && (
            <Typography variant="body1" sx={{ mt: 2 }}>
              {document.description}
            </Typography>
          )}
          
          <Box sx={{ mt: 3 }}>
            <Typography variant="h6">Document Details</Typography>
            <Card variant="outlined" sx={{ mt: 1 }}>
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2">
                      <strong>Original Filename:</strong> {document.original_filename}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2">
                      <strong>Content Type:</strong> {document.content_type}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2">
                      <strong>Uploaded:</strong> {new Date(document.created_at).toLocaleString()}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Box>
          
          <Box sx={{ mt: 4 }}>
            <Grid container alignItems="center" spacing={2}>
              <Grid item>
                <Typography variant="h6">Transformations</Typography>
              </Grid>
              <Grid item>
                <Button 
                  variant="contained" 
                  component={RouterLink} 
                  to={`/transformations/create/${document.id}`}
                >
                  Create New Transformation
                </Button>
              </Grid>
            </Grid>
            
            <Divider sx={{ my: 2 }} />
            
            {transformations.length === 0 ? (
              <Box sx={{ mt: 2, textAlign: 'center', p: 3 }}>
                <Typography variant="body1" color="text.secondary">
                  No transformations have been created for this document yet.
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  Transform this document into different formats like blog posts, social media content, email sequences, and more.
                </Typography>
              </Box>
            ) : (
              <Grid container spacing={2}>
                {transformations.map(transformation => (
                  <Grid item xs={12} sm={6} md={4} key={transformation.id}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" component="div" noWrap>
                          {transformation.transformation_type.replace(/_/g, ' ')}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Created: {new Date(transformation.created_at).toLocaleString()}
                        </Typography>
                        <Box sx={{ mt: 1 }}>
                          <Chip 
                            label={transformation.status} 
                            size="small" 
                            color={getStatusColor(transformation.status as unknown as DocumentStatus)} 
                          />
                        </Box>
                      </CardContent>
                      <CardActions>
                        <Button 
                          size="small" 
                          component={RouterLink} 
                          to={`/transformations/${transformation.id}`}
                        >
                          View Result
                        </Button>
                      </CardActions>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            )}
          </Box>
        </Paper>
      )}
    </Container>
  );
};

export default DocumentDetail;
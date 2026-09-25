import React, { useState, useEffect } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { 
  Container, Typography, Box, Grid, Card, CardContent, 
  CardActions, Button, Divider, Chip, CircularProgress,
  Alert
} from '@mui/material';
import { Document, DocumentStatus, Transformation, TransformationStatus } from '../types';
import { getUserDocuments } from '../services/documentService';
import { getUserTransformations } from '../services/transformationService';

const Dashboard: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [transformations, setTransformations] = useState<Transformation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const documentsData = await getUserDocuments();
        const transformationsData = await getUserTransformations();
        
        setDocuments(documentsData.documents);
        setTransformations(transformationsData.transformations);
      } catch (err) {
        console.error('Error fetching data:', err);
        setError('Failed to load your content. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const getStatusColor = (status: DocumentStatus | TransformationStatus) => {
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
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container>
      <Typography variant="h4" component="h1" gutterBottom sx={{ mt: 4 }}>
        Dashboard
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 4 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" component="h2" gutterBottom>
          Recent Documents
        </Typography>
        
        {documents.length === 0 ? (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body1" color="text.secondary">
              You haven't uploaded any documents yet.
            </Typography>
            <Button 
              component={RouterLink} 
              to="/documents/upload" 
              variant="contained" 
              sx={{ mt: 2 }}
            >
              Upload Your First Document
            </Button>
          </Box>
        ) : (
          <Grid container spacing={3}>
            {documents.slice(0, 4).map((document) => (
              <Grid item xs={12} sm={6} md={3} key={document.id}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" component="div" noWrap>
                      {document.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" noWrap>
                      {document.original_filename}
                    </Typography>
                    <Box sx={{ mt: 1 }}>
                      <Chip 
                        label={document.status} 
                        size="small" 
                        color={getStatusColor(document.status)} 
                      />
                    </Box>
                  </CardContent>
                  <Divider />
                  <CardActions>
                    <Button 
                      size="small" 
                      component={RouterLink} 
                      to={`/documents/${document.id}`}
                    >
                      View Details
                    </Button>
                    <Button 
                      size="small" 
                      component={RouterLink} 
                      to={`/transformations/create/${document.id}`}
                    >
                      Transform
                    </Button>
                  </CardActions>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" component="h2" gutterBottom>
          Recent Transformations
        </Typography>
        
        {transformations.length === 0 ? (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body1" color="text.secondary">
              You haven't created any transformations yet.
            </Typography>
            {documents.length > 0 && (
              <Button 
                component={RouterLink} 
                to={`/transformations/create/${documents[0].id}`} 
                variant="contained" 
                sx={{ mt: 2 }}
              >
                Create Your First Transformation
              </Button>
            )}
          </Box>
        ) : (
          <Grid container spacing={3}>
            {transformations.slice(0, 4).map((transformation) => (
              <Grid item xs={12} sm={6} md={3} key={transformation.id}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" component="div" noWrap>
                      {transformation.transformation_type.replace('_', ' ')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Document ID: {transformation.document_id}
                    </Typography>
                    <Box sx={{ mt: 1 }}>
                      <Chip 
                        label={transformation.status} 
                        size="small" 
                        color={getStatusColor(transformation.status)} 
                      />
                    </Box>
                  </CardContent>
                  <Divider />
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
    </Container>
  );
};

export default Dashboard;
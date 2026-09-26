import React, { useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, CircularProgress, Container, Paper, Typography } from '@mui/material';
import { verifyEmail } from '../services/authService';
import { useAuth } from '../context/AuthContext';

type State = 'verifying' | 'verified' | 'failed';

/** Landing page for the link in the verification email (/verify-email?token=...). */
const VerifyEmail: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [state, setState] = useState<State>(token ? 'verifying' : 'failed');
  const { refreshUser } = useAuth();
  const started = useRef(false);

  useEffect(() => {
    // StrictMode runs effects twice in development; verify once.
    if (!token || started.current) return;
    started.current = true;
    verifyEmail(token)
      .then(async () => {
        setState('verified');
        await refreshUser();
      })
      .catch(() => setState('failed'));
  }, [token, refreshUser]);

  return (
    <Container maxWidth="sm">
      <Paper sx={{ p: 4, mt: 8, textAlign: 'center' }}>
        <Typography variant="h5" component="h1" gutterBottom>
          Email verification
        </Typography>
        {state === 'verifying' && (
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}>
            <CircularProgress />
          </Box>
        )}
        {state === 'verified' && (
          <Alert severity="success" sx={{ my: 2 }}>
            Your email address is confirmed.
          </Alert>
        )}
        {state === 'failed' && (
          <Alert severity="error" sx={{ my: 2 }}>
            This verification link is invalid or has expired. Sign in and request a new one.
          </Alert>
        )}
        {state !== 'verifying' && (
          <Button component={RouterLink} to="/" variant="contained">
            Continue
          </Button>
        )}
      </Paper>
    </Container>
  );
};

export default VerifyEmail;

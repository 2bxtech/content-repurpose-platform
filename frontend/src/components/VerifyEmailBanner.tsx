import React, { useState } from 'react';
import { Alert, Button } from '@mui/material';
import { useAuth } from '../context/AuthContext';
import { resendVerification } from '../services/authService';
import { getErrorMessage } from '../utils/apiError';

/** Reminder shown to signed-in users who haven't confirmed their email yet. */
const VerifyEmailBanner: React.FC = () => {
  const { user } = useAuth();
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [error, setError] = useState('');

  if (!user || user.is_verified !== false) return null;

  const resend = async () => {
    setStatus('sending');
    try {
      await resendVerification();
      setStatus('sent');
    } catch (err) {
      setError(getErrorMessage(err, 'Could not send the email. Try again later.'));
      setStatus('error');
    }
  };

  return (
    <Alert
      severity={status === 'error' ? 'error' : 'info'}
      sx={{ mb: 2 }}
      action={
        status !== 'sent' && (
          <Button color="inherit" size="small" onClick={resend} disabled={status === 'sending'}>
            Resend email
          </Button>
        )
      }
    >
      {status === 'sent'
        ? `We sent a new confirmation link to ${user.email}.`
        : status === 'error'
          ? error
          : `Confirm your email address (${user.email}) using the link we sent you.`}
    </Alert>
  );
};

export default VerifyEmailBanner;

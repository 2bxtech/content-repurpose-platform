import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Paper,
  Stack,
  Chip,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import BoltIcon from '@mui/icons-material/Bolt';
import { TransformationType } from '../types';
import { quickTransform } from '../services/transformationService';
import { getPreset } from '../services/presetService';
import { getErrorMessage } from '../utils/apiError';

const TYPES: { value: TransformationType; label: string }[] = [
  { value: TransformationType.SUMMARY, label: 'Summary' },
  { value: TransformationType.BLOG_POST, label: 'Blog Post' },
  { value: TransformationType.SOCIAL_MEDIA, label: 'Social Media' },
  { value: TransformationType.EMAIL_SEQUENCE, label: 'Email Sequence' },
  { value: TransformationType.NEWSLETTER, label: 'Newsletter' },
  { value: TransformationType.CUSTOM, label: 'Custom' },
];

const MIN_CONTENT_LENGTH = 20;

const QuickTransformPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const paramType = searchParams.get('type') as TransformationType | null;
  const paramPresetId = searchParams.get('preset_id');

  const [content, setContent] = useState('');
  const [type, setType] = useState<TransformationType>(
    paramType && Object.values(TransformationType).includes(paramType)
      ? paramType
      : TransformationType.SUMMARY
  );
  const [presetName, setPresetName] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Load preset name for display when arriving from a preset card
  useEffect(() => {
    if (!paramPresetId) return;
    getPreset(paramPresetId)
      .then((data) => setPresetName(data.name))
      .catch(() => {/* preset name is cosmetic — ignore errors */});
  }, [paramPresetId]);

  const isValid = content.trim().length >= MIN_CONTENT_LENGTH;
  const wordCount = content.trim().split(/\s+/).filter(Boolean).length;

  const handleSubmit = async () => {
    if (!isValid || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await quickTransform({
        content: content.trim(),
        transformation_type: type,
        ...(paramPresetId ? { preset_id: paramPresetId } : {}),
      });
      navigate(`/transformations/${result.id}`);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Transform failed. Please try again.'));
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 760, mx: 'auto', mt: 4 }}>
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate('/')}
        sx={{ mb: 2, textTransform: 'none' }}
      >
        Back
      </Button>

      <Paper elevation={2} sx={{ p: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <BoltIcon color="primary" />
          <Typography variant="h5" fontWeight={700}>
            Quick Transform
          </Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Paste your content, pick a format, get output — no extra steps.
        </Typography>

        {presetName && (
          <Alert severity="info" sx={{ mb: 2 }}>
            Using preset: <strong>{presetName}</strong>
          </Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Type selector */}
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          Output format
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 3 }}>
          {TYPES.map(({ value, label }) => (
            <Chip
              key={value}
              label={label}
              clickable
              color={type === value ? 'primary' : 'default'}
              variant={type === value ? 'filled' : 'outlined'}
              onClick={() => setType(value)}
            />
          ))}
        </Stack>

        {/* Content textarea */}
        <TextField
          label="Content"
          fullWidth
          required
          multiline
          rows={14}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste or type your content here…"
          helperText={
            content.length > 0 && content.trim().length < MIN_CONTENT_LENGTH
              ? `${MIN_CONTENT_LENGTH - content.trim().length} more characters needed`
              : wordCount > 0
              ? `${wordCount} words`
              : undefined
          }
          sx={{ mb: 3 }}
        />

        <Button
          variant="contained"
          size="large"
          fullWidth
          startIcon={submitting ? undefined : <BoltIcon />}
          disabled={!isValid || submitting}
          onClick={handleSubmit}
          sx={{ py: 1.5 }}
        >
          {submitting ? (
            <CircularProgress size={22} color="inherit" />
          ) : (
            `Transform to ${TYPES.find((t) => t.value === type)?.label ?? 'output'} →`
          )}
        </Button>
      </Paper>
    </Box>
  );
};

export default QuickTransformPage;

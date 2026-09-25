import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Stack,
  Divider,
  CircularProgress,
  Chip,
} from '@mui/material';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import LinkIcon from '@mui/icons-material/Link';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import BoltIcon from '@mui/icons-material/Bolt';
import { TransformationType } from '../types';
import { getPresets } from '../services/presetService';

/** Labels for quick-launch preset chips */
const QUICK_TYPE_LABELS: Partial<Record<TransformationType, string>> = {
  [TransformationType.BLOG_POST]: 'Blog Post',
  [TransformationType.SOCIAL_MEDIA]: 'Social Media',
  [TransformationType.EMAIL_SEQUENCE]: 'Email Sequence',
  [TransformationType.NEWSLETTER]: 'Newsletter',
  [TransformationType.SUMMARY]: 'Summary',
  [TransformationType.CUSTOM]: 'Custom',
};

interface QuickPreset {
  id: string;
  name: string;
  transformation_type: TransformationType;
}

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [presets, setPresets] = useState<QuickPreset[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(true);

  useEffect(() => {
    getPresets()
      .then((data) => setPresets(data.presets.slice(0, 6)))
      .catch(() => {/* silent — presets are optional on the homepage */})
      .finally(() => setPresetsLoading(false));
  }, []);

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        pt: { xs: 4, md: 8 },
        pb: 6,
        gap: 4,
      }}
    >
      {/* Heading */}
      <Box textAlign="center">
        <Typography variant="h4" fontWeight={700} gutterBottom>
          What would you like to transform?
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Paste text, drop a URL, or upload a file — your content, repurposed in seconds.
        </Typography>
      </Box>
      {/* Quick Transform shortcut */}
      <Button
        variant="contained"
        size="large"
        startIcon={<BoltIcon />}
        onClick={() => navigate('/quick')}
        sx={{ borderRadius: 3, px: 4, py: 1.25 }}
      >
        Quick Transform
      </Button>
      {/* Input method cards */}
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ width: '100%', maxWidth: 720 }}
      >
        <InputCard
          icon={<TextFieldsIcon fontSize="large" />}
          label="Paste Text"
          description="Type or paste content directly"
          onClick={() => navigate('/documents/new/text')}
          primary
        />
        <InputCard
          icon={<LinkIcon fontSize="large" />}
          label="Fetch a URL"
          description="Pull content from any web page"
          onClick={() => navigate('/documents/new/url')}
        />
        <InputCard
          icon={<UploadFileIcon fontSize="large" />}
          label="Upload File"
          description="PDF, DOCX, or plain text"
          onClick={() => navigate('/documents/upload')}
        />
      </Stack>

      {/* Quick-launch presets */}
      <Box sx={{ width: '100%', maxWidth: 720 }}>
        <Divider sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Quick Launch — your saved presets
          </Typography>
        </Divider>

        {presetsLoading ? (
          <Box display="flex" justifyContent="center" py={1}>
            <CircularProgress size={20} />
          </Box>
        ) : (
          <Stack direction="row" flexWrap="wrap" gap={2} justifyContent="center">
            {presets.map((preset) => (
              <Card
                key={preset.id}
                variant="outlined"
                sx={{ width: 200, cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }}
              >
                <CardActionArea
                  onClick={() =>
                    navigate(`/quick?preset_id=${preset.id}&type=${preset.transformation_type}`)
                  }
                  sx={{ p: 2, height: '100%' }}
                >
                  <CardContent sx={{ p: 0 }}>
                    <Typography variant="subtitle2" fontWeight={600} gutterBottom noWrap>
                      {preset.name}
                    </Typography>
                    <Chip
                      label={QUICK_TYPE_LABELS[preset.transformation_type] ?? preset.transformation_type}
                      size="small"
                      variant="outlined"
                      color="primary"
                    />
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
            {presets.length < 3 && (
              <Card
                variant="outlined"
                sx={{
                  width: 200,
                  cursor: 'pointer',
                  borderStyle: 'dashed',
                  '&:hover': { borderColor: 'primary.main' },
                }}
              >
                <CardActionArea
                  onClick={() => navigate('/presets')}
                  sx={{ p: 2, height: '100%' }}
                >
                  <CardContent
                    sx={{
                      p: 0,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 0.5,
                      textAlign: 'center',
                    }}
                  >
                    <Typography variant="h5" color="text.disabled">
                      +
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Create preset
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            )}
          </Stack>
        )}
      </Box>

      {/* Secondary link to full history */}
      <Typography variant="body2" color="text.secondary">
        <Button
          variant="text"
          size="small"
          onClick={() => navigate('/dashboard')}
          sx={{ textTransform: 'none' }}
        >
          View document history
        </Button>
      </Typography>
    </Box>
  );
};

/* ── Sub-component ─────────────────────────────────────────────────────────── */

interface InputCardProps {
  icon: React.ReactNode;
  label: string;
  description: string;
  onClick: () => void;
  primary?: boolean;
}

const InputCard: React.FC<InputCardProps> = ({
  icon,
  label,
  description,
  onClick,
  primary = false,
}) => (
  <Card
    variant={primary ? 'elevation' : 'outlined'}
    elevation={primary ? 3 : 0}
    sx={{ flex: 1, minWidth: 160 }}
  >
    <CardActionArea onClick={onClick} sx={{ p: 2, height: '100%' }}>
      <CardContent
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 1,
          textAlign: 'center',
          p: 0,
        }}
      >
        <Box color={primary ? 'primary.main' : 'text.secondary'}>{icon}</Box>
        <Typography variant="subtitle1" fontWeight={600}>
          {label}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {description}
        </Typography>
      </CardContent>
    </CardActionArea>
  </Card>
);

export default HomePage;

import React from 'react';
import { 
  Box, 
  LinearProgress, 
  Typography, 
  Card, 
  CardContent,
  Chip,
  Avatar
} from '@mui/material';
import { 
  CheckCircle as CompleteIcon,
  Error as ErrorIcon,
  Schedule as PendingIcon,
  Psychology as ProcessingIcon
} from '@mui/icons-material';

interface ProgressIndicatorProps {
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  progress?: number;
  title: string;
  subtitle?: string;
  estimatedTime?: string;
}

export const ProgressIndicator: React.FC<ProgressIndicatorProps> = ({
  status,
  progress = 0,
  title,
  subtitle,
  estimatedTime
}) => {
  const getStatusConfig = () => {
    switch (status) {
      case 'COMPLETED':
        return {
          color: 'success' as const,
          icon: <CompleteIcon />,
          label: 'Completed'
        };
      case 'FAILED':
        return {
          color: 'error' as const,
          icon: <ErrorIcon />,
          label: 'Failed'
        };
      case 'PROCESSING':
        return {
          color: 'primary' as const,
          icon: <ProcessingIcon />,
          label: 'Processing'
        };
      default:
        return {
          color: 'default' as const,
          icon: <PendingIcon />,
          label: 'Pending'
        };
    }
  };

  const statusConfig = getStatusConfig();

  return (
    <Card elevation={2} sx={{ mb: 2 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Avatar sx={{ bgcolor: `${statusConfig.color}.main`, mr: 2 }}>
            {statusConfig.icon}
          </Avatar>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h6">{title}</Typography>
            {subtitle && (
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            )}
          </Box>
          <Chip 
            label={statusConfig.label}
            color={statusConfig.color}
            size="small"
          />
        </Box>
        
        {status === 'PROCESSING' && (
          <Box sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="body2">Progress</Typography>
              <Typography variant="body2">{Math.round(progress)}%</Typography>
            </Box>
            <LinearProgress 
              variant="determinate" 
              value={progress}
              sx={{ height: 8, borderRadius: 4 }}
            />
            {estimatedTime && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                Estimated time: {estimatedTime}
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};
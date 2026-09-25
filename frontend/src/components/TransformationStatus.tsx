import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Typography,
  LinearProgress,
  Chip,
  Box,
  Alert,
  Collapse,
  IconButton
} from '@mui/material';
import {
  PlayArrow,
  ExpandMore,
  ExpandLess,
  CheckCircle,
  Error as ErrorIcon,
  AccessTime
} from '@mui/icons-material';
import { useWebSocketContext } from '../context/WebSocketContext';

interface TransformationStatusProps {
  transformationId: string;
  initialStatus?: string;
  onStatusChange?: (status: string, data: any) => void;
}

interface TransformationUpdate {
  transformation_id: string;
  progress: number;
  status: string;
  error_message?: string;
  result_preview?: string;
  provider?: string;
  tokens_used?: number;
}

const TransformationStatus: React.FC<TransformationStatusProps> = ({
  transformationId,
  initialStatus = 'pending',
  onStatusChange
}) => {
  const { transformationUpdates, isConnected, connectionState } = useWebSocketContext();
  
  const [status, setStatus] = useState(initialStatus);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Initializing...');
  const [error, setError] = useState<string | null>(null);
  const [resultPreview, setResultPreview] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<any>({});
  const [isExpanded, setIsExpanded] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  // Handle transformation updates
  const handleTransformationUpdate = useCallback((update: TransformationUpdate) => {
    console.log('Processing transformation update:', update);
    
    setProgress(update.progress || 0);
    setMessage(update.status || 'Processing...');
    setLastUpdate(new Date());

    // Determine status based on the message type that delivered this update
    // This would be set by the WebSocket service based on message.type
    const messageType = (update as any).message_type;
    
    switch (messageType) {
      case 'transformation_started':
        setStatus('PROCESSING');
        setError(null);
        break;
      
      case 'transformation_progress':
        setStatus('PROCESSING');
        setError(null);
        break;
      
      case 'transformation_completed':
        setStatus('COMPLETED');
        setProgress(100);
        setError(null);
        setResultPreview(update.result_preview || null);
        setMetadata({
          provider: update.provider,
          tokens_used: update.tokens_used
        });
        break;
      
      case 'transformation_failed':
        setStatus('FAILED');
        setError(update.error_message || 'Transformation failed');
        break;
    }

    // Notify parent component
    onStatusChange?.(status, {
      progress: update.progress,
      message: update.status,
      error: update.error_message,
      resultPreview: update.result_preview,
      metadata: {
        provider: update.provider,
        tokens_used: update.tokens_used
      }
    });
  }, [onStatusChange, status]);

  // Process transformation updates from WebSocket
  useEffect(() => {
    const relevantUpdates = transformationUpdates.filter(
      update => update.transformation_id === transformationId
    );

    if (relevantUpdates.length > 0) {
      const latestUpdate = relevantUpdates[relevantUpdates.length - 1];
      handleTransformationUpdate(latestUpdate);
    }
  }, [transformationUpdates, transformationId, handleTransformationUpdate]);

  const getStatusColor = () => {
    switch (status) {
      case 'PENDING': return 'default';
      case 'PROCESSING': return 'primary';
      case 'COMPLETED': return 'success';
      case 'FAILED': return 'error';
      default: return 'default';
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'PENDING':
        return <AccessTime />;
      case 'PROCESSING':
        return <PlayArrow />;
      case 'COMPLETED':
        return <CheckCircle />;
      case 'FAILED':
        return <ErrorIcon />;
      default:
        return <AccessTime />;
    }
  };

  const formatLastUpdate = () => {
    const now = new Date();
    const diffMs = now.getTime() - lastUpdate.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);

    if (diffSecs < 60) {
      return `${diffSecs}s ago`;
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else {
      return lastUpdate.toLocaleTimeString();
    }
  };

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        {/* Header */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <Chip
              icon={getStatusIcon()}
              label={status.charAt(0).toUpperCase() + status.slice(1)}
              color={getStatusColor()}
              size="small"
            />
            <Typography variant="body2" color="text.secondary">
              ID: {transformationId.slice(0, 8)}...
            </Typography>
          </Box>
          
          <Box display="flex" alignItems="center" gap={1}>
            <Chip
              label={isConnected ? 'Live' : 'Offline'}
              color={isConnected ? 'success' : 'default'}
              size="small"
              variant="outlined"
            />
            <IconButton
              size="small"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          </Box>
        </Box>

        {/* Progress Bar */}
        {status === 'PROCESSING' && (
          <Box mb={2}>
            <LinearProgress 
              variant="determinate" 
              value={progress} 
              sx={{ height: 8, borderRadius: 1 }}
            />
            <Box display="flex" justifyContent="space-between" mt={0.5}>
              <Typography variant="body2" color="text.secondary">
                {message}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {progress}%
              </Typography>
            </Box>
          </Box>
        )}

        {/* Status Message */}
        {status !== 'processing' && (
          <Typography variant="body2" color="text.secondary" mb={1}>
            {message}
          </Typography>
        )}

        {/* Error Display */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Success with Preview */}
        {status === 'COMPLETED' && resultPreview && (
          <Alert severity="success" sx={{ mb: 2 }}>
            <Typography variant="body2" fontWeight="bold" mb={1}>
              Transformation completed successfully!
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Preview: {resultPreview}
            </Typography>
          </Alert>
        )}

        {/* Expanded Details */}
        <Collapse in={isExpanded}>
          <Box mt={2} p={2} bgcolor="grey.50" borderRadius={1}>
            <Typography variant="body2" fontWeight="bold" mb={1}>
              Details
            </Typography>
            
            <Box display="grid" gridTemplateColumns="1fr 1fr" gap={1}>
              <Typography variant="body2" color="text.secondary">
                Last Update:
              </Typography>
              <Typography variant="body2">
                {formatLastUpdate()}
              </Typography>
              
              <Typography variant="body2" color="text.secondary">
                Connection:
              </Typography>
              <Typography variant="body2">
                {connectionState}
              </Typography>
              
              {metadata.provider && (
                <>
                  <Typography variant="body2" color="text.secondary">
                    AI Provider:
                  </Typography>
                  <Typography variant="body2">
                    {metadata.provider}
                  </Typography>
                </>
              )}
              
              {metadata.tokens_used && (
                <>
                  <Typography variant="body2" color="text.secondary">
                    Tokens Used:
                  </Typography>
                  <Typography variant="body2">
                    {metadata.tokens_used.toLocaleString()}
                  </Typography>
                </>
              )}
            </Box>
          </Box>
        </Collapse>

        {/* Last Update Time */}
        <Typography variant="caption" color="text.secondary" mt={1} display="block">
          Last updated: {formatLastUpdate()}
        </Typography>
      </CardContent>
    </Card>
  );
};

export default TransformationStatus;
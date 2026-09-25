import React, { useState } from 'react';
import { 
  AppBar, 
  Toolbar, 
  Typography, 
  Button, 
  Box, 
  Avatar,
  IconButton,
  Menu,
  MenuItem,
  Tooltip,
  Chip,
  useScrollTrigger,
  Slide
} from '@mui/material';
import { 
  Brightness4 as DarkIcon,
  Brightness7 as LightIcon,
  SettingsBrightness as SystemIcon,
  Dashboard as DashboardIcon,
  Upload as UploadIcon,
  Logout as LogoutIcon,
  Bookmarks as PresetsIcon
} from '@mui/icons-material';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { motion } from 'framer-motion';

interface HideOnScrollProps {
  children: React.ReactElement;
}

function HideOnScroll({ children }: HideOnScrollProps) {
  const trigger = useScrollTrigger();
  return (
    <Slide appear={false} direction="down" in={!trigger}>
      {children}
    </Slide>
  );
}

const NavBar: React.FC = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const { mode, actualMode, toggleMode } = useTheme();
  const navigate = useNavigate();
  const [userMenuAnchor, setUserMenuAnchor] = useState<null | HTMLElement>(null);

  const handleLogout = () => {
    logout();
    navigate('/login');
    setUserMenuAnchor(null);
  };

  const handleUserMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setUserMenuAnchor(event.currentTarget);
  };

  const handleUserMenuClose = () => {
    setUserMenuAnchor(null);
  };

  // Keyboard shortcuts (only when authenticated)
  const shortcuts = isAuthenticated ? [
    {
      key: 't',
      ctrl: true,
      action: toggleMode,
      description: 'Toggle theme'
    },
    {
      key: 'd',
      ctrl: true,
      action: () => navigate('/'),
      description: 'Go to dashboard'
    },
    {
      key: 'u',
      ctrl: true,
      action: () => navigate('/documents/upload'),
      description: 'Upload document'
    },
    {
      key: 'p',
      ctrl: true,
      action: () => navigate('/presets'),
      description: 'Manage presets'
    }
  ] : [];

  useKeyboardShortcuts(shortcuts);

  const getThemeIcon = () => {
    switch (mode) {
      case 'light':
        return <LightIcon />;
      case 'dark':
        return <DarkIcon />;
      default:
        return <SystemIcon />;
    }
  };

  const getThemeLabel = () => {
    switch (mode) {
      case 'light':
        return 'Light Mode';
      case 'dark':
        return 'Dark Mode';
      default:
        return 'System Mode';
    }
  };

  return (
    <HideOnScroll>
      <AppBar 
        position="sticky" 
        elevation={0}
        sx={{ 
          backdropFilter: 'blur(20px)',
          backgroundColor: actualMode === 'dark' 
            ? 'rgba(18, 18, 18, 0.9)' 
            : 'rgba(255, 255, 255, 0.9)',
          borderBottom: 1,
          borderColor: 'divider'
        }}
      >
        <Toolbar sx={{ px: { xs: 2, sm: 3 } }}>
          <motion.div
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <Typography 
              variant="h6" 
              component={RouterLink} 
              to="/" 
              sx={{ 
                flexGrow: 1, 
                textDecoration: 'none', 
                color: 'text.primary',
                fontWeight: 700,
                background: `linear-gradient(45deg, ${actualMode === 'dark' ? '#90caf9' : '#1976d2'}, ${actualMode === 'dark' ? '#f48fb1' : '#dc004e'})`,
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent'
              }}
            >
              Content Repurpose
            </Typography>
          </motion.div>

          <Box sx={{ flexGrow: 1 }} />
          
          {/* Theme Toggle */}
          <Tooltip title={`${getThemeLabel()} (Ctrl+T)`}>
            <IconButton
              color="inherit"
              onClick={toggleMode}
              sx={{ 
                mr: 1,
                color: 'text.primary',
                '&:hover': {
                  backgroundColor: 'action.hover'
                }
              }}
            >
              {getThemeIcon()}
            </IconButton>
          </Tooltip>
        
        {isAuthenticated ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Tooltip title="Dashboard (Ctrl+D)">
              <Button 
                color="inherit" 
                component={RouterLink} 
                to="/"
                startIcon={<DashboardIcon />}
                sx={{ 
                  color: 'text.primary',
                  '&:hover': {
                    backgroundColor: 'action.hover'
                  }
                }}
              >
                Dashboard
              </Button>
            </Tooltip>
            
            <Tooltip title="Upload (Ctrl+U)">
              <Button 
                color="inherit" 
                component={RouterLink} 
                to="/documents/upload"
                startIcon={<UploadIcon />}
                sx={{ 
                  color: 'text.primary',
                  '&:hover': {
                    backgroundColor: 'action.hover'
                  }
                }}
              >
                Upload
              </Button>
            </Tooltip>
            
            <Tooltip title="Presets (Ctrl+P)">
              <Button 
                color="inherit" 
                component={RouterLink} 
                to="/presets"
                startIcon={<PresetsIcon />}
                sx={{ 
                  color: 'text.primary',
                  '&:hover': {
                    backgroundColor: 'action.hover'
                  }
                }}
              >
                Presets
              </Button>
            </Tooltip>

            {/* Admin Dashboard Link (temporarily disabled until we create the page) */}
            {/*
            <Tooltip title="Admin Dashboard">
              <Button 
                color="inherit" 
                component={RouterLink} 
                to="/admin"
                startIcon={<AdminIcon />}
                sx={{ 
                  color: 'text.primary',
                  '&:hover': {
                    backgroundColor: 'action.hover'
                  }
                }}
              >
                Admin
              </Button>
            </Tooltip>
            */}

            {/* User Menu */}
            <Box sx={{ display: 'flex', alignItems: 'center', ml: 2 }}>
              <Tooltip title="User menu">
                <IconButton
                  onClick={handleUserMenuOpen}
                  sx={{ p: 0 }}
                >
                  <Avatar 
                    sx={{ 
                      width: 40, 
                      height: 40,
                      bgcolor: 'primary.main',
                      border: 2,
                      borderColor: 'divider'
                    }}
                  >
                    {user?.username.charAt(0).toUpperCase()}
                  </Avatar>
                </IconButton>
              </Tooltip>
              
              <Menu
                anchorEl={userMenuAnchor}
                open={Boolean(userMenuAnchor)}
                onClose={handleUserMenuClose}
                onClick={handleUserMenuClose}
                transformOrigin={{ horizontal: 'right', vertical: 'top' }}
                anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
                sx={{
                  '& .MuiPaper-root': {
                    mt: 1,
                    minWidth: 200
                  }
                }}
              >
                <Box sx={{ px: 2, py: 1, borderBottom: 1, borderColor: 'divider' }}>
                  <Typography variant="subtitle2" color="text.primary">
                    {user?.username}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {user?.email}
                  </Typography>
                  <Chip 
                    label="Active" 
                    size="small" 
                    color="success" 
                    sx={{ mt: 0.5 }} 
                  />
                </Box>
                
                <MenuItem onClick={handleLogout}>
                  <LogoutIcon sx={{ mr: 1 }} />
                  Logout
                </MenuItem>
              </Menu>
            </Box>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button 
              color="inherit" 
              component={RouterLink} 
              to="/login"
              sx={{ 
                color: 'text.primary',
                '&:hover': {
                  backgroundColor: 'action.hover'
                }
              }}
            >
              Login
            </Button>
            <Button 
              variant="contained"
              component={RouterLink} 
              to="/register"
              sx={{
                background: `linear-gradient(45deg, ${actualMode === 'dark' ? '#90caf9' : '#1976d2'}, ${actualMode === 'dark' ? '#f48fb1' : '#dc004e'})`,
                '&:hover': {
                  background: `linear-gradient(45deg, ${actualMode === 'dark' ? '#64b5f6' : '#1565c0'}, ${actualMode === 'dark' ? '#f06292' : '#c62828'})`
                }
              }}
            >
              Register
            </Button>
          </Box>
        )}
      </Toolbar>
    </AppBar>
    </HideOnScroll>
  );
};

export default NavBar;
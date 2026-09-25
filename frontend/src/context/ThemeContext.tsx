import React, { createContext, useContext, useState, useEffect } from 'react';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { motion } from 'framer-motion';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeContextType {
  mode: ThemeMode;
  actualMode: 'light' | 'dark';
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
}

const ThemeContext = createContext<ThemeContextType | null>(null);

export const CustomThemeProvider: React.FC<{ children: React.ReactNode }> = ({
  children
}) => {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem('theme-mode');
    return (stored as ThemeMode) || 'system';
  });

  const [systemPreference, setSystemPreference] = useState<'light' | 'dark'>(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  );

  const actualMode = mode === 'system' ? systemPreference : mode;

  // Listen for system theme changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      setSystemPreference(e.matches ? 'dark' : 'light');
    };

    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  // Save preference
  useEffect(() => {
    localStorage.setItem('theme-mode', mode);
  }, [mode]);

  const toggleMode = () => {
    setMode(prev => {
      if (prev === 'light') return 'dark';
      if (prev === 'dark') return 'system';
      return 'light';
    });
  };

  const theme = createTheme({
    palette: {
      mode: actualMode,
      primary: {
        main: actualMode === 'dark' ? '#90caf9' : '#1976d2',
      },
      secondary: {
        main: actualMode === 'dark' ? '#f48fb1' : '#dc004e',
      },
      background: {
        default: actualMode === 'dark' ? '#121212' : '#fafafa',
        paper: actualMode === 'dark' ? '#1e1e1e' : '#ffffff',
      },
      text: {
        primary: actualMode === 'dark' ? '#ffffff' : '#333333',
        secondary: actualMode === 'dark' ? '#b3b3b3' : '#666666',
      },
    },
    typography: {
      fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
      h1: {
        fontWeight: 700,
      },
      h2: {
        fontWeight: 600,
      },
      h3: {
        fontWeight: 600,
      },
    },
    shape: {
      borderRadius: 12,
    },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            boxShadow: actualMode === 'dark' 
              ? '0 4px 20px rgba(0,0,0,0.3)'
              : '0 4px 20px rgba(0,0,0,0.1)',
            transition: 'box-shadow 0.3s ease-in-out',
            '&:hover': {
              boxShadow: actualMode === 'dark'
                ? '0 8px 30px rgba(0,0,0,0.4)'
                : '0 8px 30px rgba(0,0,0,0.15)',
            },
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            textTransform: 'none',
            borderRadius: 8,
            fontWeight: 600,
          },
        },
      },
    },
  });

  return (
    <ThemeContext.Provider value={{ mode, actualMode, setMode, toggleMode }}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <motion.div
          key={actualMode}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {children}
        </motion.div>
      </ThemeProvider>
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within CustomThemeProvider');
  }
  return context;
};
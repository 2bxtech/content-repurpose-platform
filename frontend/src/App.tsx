import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Container } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Enhanced context providers
import { AuthProvider } from './context/AuthContext';
import { CustomThemeProvider } from './context/ThemeContext';
import { NotificationProvider } from './context/NotificationContext';
import { AccessibilityProvider } from './context/AccessibilityProvider';
// import { WebSocketProvider } from './context/WebSocketContext'; // Will integrate in Session 2

// Enhanced components
import { ErrorBoundary } from './components/ErrorBoundary';
import NavBar from './components/NavBar';
import ProtectedRoute from './components/ProtectedRoute';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import HomePage from './pages/HomePage';
import Dashboard from './pages/Dashboard';
import TextInputPage from './pages/TextInputPage';
import QuickTransformPage from './pages/QuickTransformPage';
import UrlInputPage from './pages/UrlInputPage';
import DocumentUpload from './pages/DocumentUpload';
import DocumentDetail from './pages/DocumentDetail';
import TransformationCreate from './pages/TransformationCreate';
import TransformationDetail from './pages/TransformationDetail';
import Presets from './pages/Presets';
// import AdminDashboard from './pages/AdminDashboard'; // Will create this next

// Create a client for React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AccessibilityProvider>
          <CustomThemeProvider>
            <AuthProvider>
              {/* WebSocket provider with auth integration - will be enhanced */}
              <NotificationProvider>
                <Router>
                  <NavBar />
                  <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
                    <Routes>
                    {/* Public routes */}
                    <Route path="/login" element={<Login />} />
                    <Route path="/register" element={<Register />} />
                    
                    {/* Protected routes */}
                    <Route
                      path="/"
                      element={
                        <ProtectedRoute>
                          <HomePage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/dashboard"
                      element={
                        <ProtectedRoute>
                          <Dashboard />
                        </ProtectedRoute>
                      }
                    />
                    {/* Commented out until we create AdminDashboard
                    <Route
                      path="/admin"
                      element={
                        <ProtectedRoute>
                          <AdminDashboard />
                        </ProtectedRoute>
                      }
                    />
                    */}
                    <Route
                      path="/documents/new/text"
                      element={
                        <ProtectedRoute>
                          <TextInputPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/quick"
                      element={
                        <ProtectedRoute>
                          <QuickTransformPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/documents/new/url"
                      element={
                        <ProtectedRoute>
                          <UrlInputPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/documents/upload"
                      element={
                        <ProtectedRoute>
                          <DocumentUpload />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/documents/:id"
                      element={
                        <ProtectedRoute>
                          <DocumentDetail />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/transformations/create/:documentId"
                      element={
                        <ProtectedRoute>
                          <TransformationCreate />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/transformations/:id"
                      element={
                        <ProtectedRoute>
                          <TransformationDetail />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/presets"
                      element={
                        <ProtectedRoute>
                          <Presets />
                        </ProtectedRoute>
                      }
                    />
                    
                    {/* Fallback route */}
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Container>
              </Router>
            </NotificationProvider>
          </AuthProvider>
        </CustomThemeProvider>
      </AccessibilityProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};

export default App;
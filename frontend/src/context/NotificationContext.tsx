import React, { createContext, useContext, useState, useCallback } from 'react';
import { Snackbar, Alert, AlertColor } from '@mui/material';

interface Notification {
  id: string;
  message: string;
  type: AlertColor;
  duration?: number;
  action?: React.ReactNode;
}

interface NotificationContextType {
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  clearAll: () => void;
}

const NotificationContext = createContext<NotificationContextType | null>(null);

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({
  children
}) => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  
  // WebSocket integration will be added in Phase 10 Session 2
  // For now, we'll skip WebSocket notifications
  const lastMessage: any = null;

  const addNotification = useCallback((notification: Omit<Notification, 'id'>) => {
    const id = Math.random().toString(36).substr(2, 9);
    setNotifications(prev => [...prev, { ...notification, id }]);
    
    // Auto-remove after duration
    if (notification.duration) {
      setTimeout(() => {
        setNotifications(current => current.filter(n => n.id !== id));
      }, notification.duration);
    }
  }, []);

  const removeNotification = useCallback((id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  // Handle WebSocket notifications
  React.useEffect(() => {
    if (lastMessage?.type === 'transformation_update') {
      const { status } = lastMessage.data;
      if (status === 'COMPLETED') {
        addNotification({
          message: 'Transformation completed successfully!',
          type: 'success',
          duration: 5000
        });
      } else if (status === 'FAILED') {
        addNotification({
          message: 'Transformation failed. Please try again.',
          type: 'error',
          duration: 8000
        });
      }
    }
  }, [lastMessage, addNotification]);

  return (
    <NotificationContext.Provider value={{
      notifications,
      addNotification,
      removeNotification,
      clearAll
    }}>
      {children}
      {notifications.map(notification => (
        <Snackbar
          key={notification.id}
          open
          autoHideDuration={notification.duration}
          onClose={() => removeNotification(notification.id)}
          anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
        >
          <Alert 
            severity={notification.type}
            onClose={() => removeNotification(notification.id)}
            action={notification.action}
          >
            {notification.message}
          </Alert>
        </Snackbar>
      ))}
    </NotificationContext.Provider>
  );
};

export const useNotifications = () => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider');
  }
  return context;
};
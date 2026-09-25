import axios from 'axios';
import { AuthToken, UserLogin, UserRegister, User } from '../types';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

// Create axios instance with default config
const api = axios.create({
  baseURL: API_URL,
});

// Add interceptor to add auth token to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Auth API calls
export const login = async (credentials: UserLogin): Promise<AuthToken> => {
  const formData = new FormData();
  formData.append('username', credentials.email);
  formData.append('password', credentials.password);
  
  // Use corrected endpoint - single prefix
  const response = await axios.post<AuthToken>(`${API_URL}/auth/token`, formData);
  return response.data;
};

export const register = async (userData: UserRegister): Promise<User> => {
  // Use corrected endpoint - single prefix 
  const response = await api.post<User>('/auth/register', userData);
  return response.data;
};

export const getCurrentUser = async (): Promise<User> => {
  // Use corrected endpoint - single prefix
  const response = await api.get<User>('/auth/me');
  return response.data;
};

export default api;

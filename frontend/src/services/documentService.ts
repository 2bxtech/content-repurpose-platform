import api from './authService';
import { Document, DocumentList } from '../types';

// Document API calls
export const uploadDocument = async (formData: FormData): Promise<Document> => {
  const response = await api.post<Document>('/documents/upload', formData);
  return response.data;
};

export const createTextDocument = async (
  title: string,
  content: string,
  description?: string
): Promise<Document> => {
  const formData = new FormData();
  formData.append('title', title);
  formData.append('content', content);
  if (description) formData.append('description', description);
  const response = await api.post<Document>('/documents/text', formData);
  return response.data;
};

export const createUrlDocument = async (url: string, title?: string): Promise<Document> => {
  const response = await api.post<Document>('/documents/url', { url, ...(title ? { title } : {}) });
  return response.data;
};

export const getUserDocuments = async (): Promise<DocumentList> => {
  const response = await api.get<DocumentList>('/documents');
  return response.data;
};

export const getDocument = async (id: string): Promise<Document> => {
  const response = await api.get<Document>(`/documents/${id}`);
  return response.data;
};

export const deleteDocument = async (id: number): Promise<void> => {
  await api.delete(`/documents/${id}`);
};

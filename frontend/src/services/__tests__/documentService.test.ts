import {
  uploadDocument,
  createTextDocument,
  createUrlDocument,
  getUserDocuments,
  getDocument,
  deleteDocument,
} from '../documentService';
import api from '../authService';
import { Document, DocumentList, DocumentStatus } from '../../types';

// Mock the auth service
jest.mock('../authService');
const mockedApi = api as jest.Mocked<typeof api>;

describe('documentService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('uploadDocument', () => {
    it('should upload a document successfully', async () => {
      const mockDocument: Document = {
        id: '1',
        user_id: 'user123',
        title: 'Test Document',
        description: 'Test description',
        file_path: '/uploads/test.pdf',
        original_filename: 'test.pdf',
        content_type: 'application/pdf',
        status: DocumentStatus.COMPLETED,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      const mockFormData = new FormData();
      mockFormData.append('title', 'Test Document');
      mockFormData.append('description', 'Test description');
      mockFormData.append('file', new File(['test content'], 'test.pdf', { type: 'application/pdf' }));

      mockedApi.post.mockResolvedValue({ data: mockDocument });

      const result = await uploadDocument(mockFormData);

      expect(mockedApi.post).toHaveBeenCalledWith(
        '/documents/upload',
        mockFormData
      );
      expect(result).toEqual(mockDocument);
    });

    it('should handle upload errors', async () => {
      const mockFormData = new FormData();
      const error = new Error('Upload failed');
      
      mockedApi.post.mockRejectedValue(error);

      await expect(uploadDocument(mockFormData)).rejects.toThrow('Upload failed');
    });

    it('should let the browser generate multipart headers for file upload', async () => {
      const mockDocument: Document = {
        id: '1',
        user_id: 'user123',
        title: 'Test Document',
        description: 'Test description',
        file_path: '/uploads/test.pdf',
        original_filename: 'test.pdf',
        content_type: 'application/pdf',
        status: DocumentStatus.COMPLETED,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      const mockFormData = new FormData();
      mockedApi.post.mockResolvedValue({ data: mockDocument });

      await uploadDocument(mockFormData);

      expect(mockedApi.post).toHaveBeenCalledWith(
        '/documents/upload',
        expect.any(FormData)
      );
    });
  });

  describe('getUserDocuments', () => {
    it('should fetch user documents successfully', async () => {
      const mockDocumentList: DocumentList = {
        documents: [
          {
            id: '1',
            user_id: 'user123',
            title: 'Document 1',
            description: 'First document',
            file_path: '/uploads/doc1.pdf',
            original_filename: 'doc1.pdf',
            content_type: 'application/pdf',
            status: DocumentStatus.COMPLETED,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          }
        ],
        count: 1
      };

      mockedApi.get.mockResolvedValue({ data: mockDocumentList });

      const result = await getUserDocuments();

      expect(mockedApi.get).toHaveBeenCalledWith('/documents');
      expect(result).toEqual(mockDocumentList);
    });

    it('should handle empty document list', async () => {
      const mockEmptyList: DocumentList = {
        documents: [],
        count: 0
      };

      mockedApi.get.mockResolvedValue({ data: mockEmptyList });

      const result = await getUserDocuments();

      expect(result.documents).toHaveLength(0);
      expect(result.count).toBe(0);
    });

    it('should handle API errors', async () => {
      const error = new Error('Network error');
      mockedApi.get.mockRejectedValue(error);

      await expect(getUserDocuments()).rejects.toThrow('Network error');
    });
  });

  describe('getDocument', () => {
    it('should fetch a specific document successfully', async () => {
      const mockDocument: Document = {
        id: '123',
        user_id: 'user123',
        title: 'Specific Document',
        description: 'Document description',
        file_path: '/uploads/specific.pdf',
        original_filename: 'specific.pdf',
        content_type: 'application/pdf',
        status: DocumentStatus.COMPLETED,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      mockedApi.get.mockResolvedValue({ data: mockDocument });

      const result = await getDocument('123');

      expect(mockedApi.get).toHaveBeenCalledWith('/documents/123');
      expect(result).toEqual(mockDocument);
    });

    it('should handle document not found', async () => {
      const error = new Error('Document not found');
      mockedApi.get.mockRejectedValue(error);

      await expect(getDocument('nonexistent')).rejects.toThrow('Document not found');
    });

    it('should handle invalid document ID', async () => {
      const error = new Error('Invalid document ID');
      mockedApi.get.mockRejectedValue(error);

      await expect(getDocument('')).rejects.toThrow('Invalid document ID');
    });
  });

  describe('deleteDocument', () => {
    it('should delete document successfully', async () => {
      mockedApi.delete.mockResolvedValue({ data: {} });

      await deleteDocument(123);

      expect(mockedApi.delete).toHaveBeenCalledWith('/documents/123');
    });

    it('should handle delete errors', async () => {
      const error = new Error('Delete failed');
      mockedApi.delete.mockRejectedValue(error);

      await expect(deleteDocument(123)).rejects.toThrow('Delete failed');
    });

    it('should handle authorization errors', async () => {
      const error = new Error('Unauthorized');
      mockedApi.delete.mockRejectedValue(error);

      await expect(deleteDocument(123)).rejects.toThrow('Unauthorized');
    });

    it('should handle non-existent document delete', async () => {
      const error = new Error('Document not found');
      mockedApi.delete.mockRejectedValue(error);

      await expect(deleteDocument(999)).rejects.toThrow('Document not found');
    });
  });

  describe('edge cases', () => {
    it('should handle network timeouts', async () => {
      const timeoutError = new Error('Network timeout');
      mockedApi.get.mockRejectedValue(timeoutError);

      await expect(getUserDocuments()).rejects.toThrow('Network timeout');
    });

    it('should handle malformed responses', async () => {
      mockedApi.get.mockResolvedValue({ data: null });

      const result = await getUserDocuments();
      expect(result).toBeNull();
    });

    it('should validate FormData for upload', async () => {
      const mockDocument: Document = {
        id: '1',
        user_id: 'user123',
        title: 'Test Document',
        description: 'Test description',
        file_path: '/uploads/test.pdf',
        original_filename: 'test.pdf',
        content_type: 'application/pdf',
        status: DocumentStatus.COMPLETED,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      mockedApi.post.mockResolvedValue({ data: mockDocument });

      const formData = new FormData();
      await uploadDocument(formData);

      expect(mockedApi.post).toHaveBeenCalledWith(
        '/documents/upload',
        expect.any(FormData)
      );
    });
  });

  describe('createTextDocument', () => {
    it('posts FormData without overriding the multipart boundary', async () => {
      const mockDocument = { id: 'text-1' } as Document;
      mockedApi.post.mockResolvedValue({ data: mockDocument });

      await createTextDocument('Title', 'Content long enough to submit', 'Description');

      expect(mockedApi.post).toHaveBeenCalledTimes(1);
      const [path, body, config] = mockedApi.post.mock.calls[0];
      expect(path).toBe('/documents/text');
      expect(body).toBeInstanceOf(FormData);
      expect((body as FormData).get('title')).toBe('Title');
      expect((body as FormData).get('content')).toBe('Content long enough to submit');
      expect(config).toBeUndefined();
    });
  });

  describe('createUrlDocument', () => {
    it('uses the forward-slash API path', async () => {
      mockedApi.post.mockResolvedValue({ data: { id: 'url-1' } as Document });

      await createUrlDocument('https://example.com', 'Example');

      expect(mockedApi.post).toHaveBeenCalledWith('/documents/url', {
        url: 'https://example.com',
        title: 'Example',
      });
    });
  });
});

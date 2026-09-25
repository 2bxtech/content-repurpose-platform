import {
  createTransformation,
  getUserTransformations,
  getTransformation,
  deleteTransformation,
  getTransformationStatus,
  cancelTransformation,
  pollTransformationStatus
} from '../transformationService';
import api from '../authService';
import { Transformation, TransformationList, TransformationCreate, TransformationType, TransformationStatus } from '../../types';

// Mock the auth service
jest.mock('../authService');
const mockedApi = api as jest.Mocked<typeof api>;

describe('transformationService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.clearAllTimers();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('createTransformation', () => {
    it('should create a transformation successfully', async () => {
      const mockTransformationData: TransformationCreate = {
        document_id: 'doc123',
        transformation_type: TransformationType.BLOG_POST,
        parameters: { wordCount: 500, tone: 'professional' }
      };

      const mockTransformation: Transformation = {
        id: 'trans123',
        user_id: 'user123',
        document_id: 'doc123',
        transformation_type: TransformationType.BLOG_POST,
        parameters: { wordCount: 500, tone: 'professional' },
        status: TransformationStatus.PENDING,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      mockedApi.post.mockResolvedValue({ data: mockTransformation });

      const result = await createTransformation(mockTransformationData);

      expect(mockedApi.post).toHaveBeenCalledWith('/transformations', mockTransformationData);
      expect(result).toEqual(mockTransformation);
    });

    it('should handle transformation creation errors', async () => {
      const mockTransformationData: TransformationCreate = {
        document_id: 'doc123',
        transformation_type: TransformationType.BLOG_POST,
        parameters: { wordCount: 500, tone: 'professional' }
      };

      const error = new Error('Creation failed');
      mockedApi.post.mockRejectedValue(error);

      await expect(createTransformation(mockTransformationData)).rejects.toThrow('Creation failed');
    });

    it('should validate transformation type', async () => {
      const mockTransformationData: TransformationCreate = {
        document_id: 'doc123',
        transformation_type: TransformationType.SOCIAL_MEDIA,
        parameters: { wordCount: 280, tone: 'casual' }
      };

      const mockTransformation: Transformation = {
        id: 'trans123',
        user_id: 'user123',
        document_id: 'doc123',
        transformation_type: TransformationType.SOCIAL_MEDIA,
        parameters: { wordCount: 280, tone: 'casual' },
        status: TransformationStatus.PENDING,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      mockedApi.post.mockResolvedValue({ data: mockTransformation });

      const result = await createTransformation(mockTransformationData);

      expect(result.transformation_type).toBe(TransformationType.SOCIAL_MEDIA);
      expect(result.parameters).toEqual({ wordCount: 280, tone: 'casual' });
    });
  });

  describe('getUserTransformations', () => {
    it('should fetch user transformations successfully', async () => {
      const mockTransformationList: TransformationList = {
        transformations: [
          {
            id: 'trans1',
            user_id: 'user123',
            document_id: 'doc123',
            transformation_type: TransformationType.BLOG_POST,
            parameters: { wordCount: 500, tone: 'professional' },
            status: TransformationStatus.COMPLETED,
            result: 'Generated blog post content...',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          }
        ],
        count: 1
      };

      mockedApi.get.mockResolvedValue({ data: mockTransformationList });

      const result = await getUserTransformations();

      expect(mockedApi.get).toHaveBeenCalledWith('/transformations');
      expect(result).toEqual(mockTransformationList);
    });

    it('should handle empty transformation list', async () => {
      const mockEmptyList: TransformationList = {
        transformations: [],
        count: 0
      };

      mockedApi.get.mockResolvedValue({ data: mockEmptyList });

      const result = await getUserTransformations();

      expect(result.transformations).toHaveLength(0);
      expect(result.count).toBe(0);
    });

    it('should handle API errors', async () => {
      const error = new Error('Network error');
      mockedApi.get.mockRejectedValue(error);

      await expect(getUserTransformations()).rejects.toThrow('Network error');
    });
  });

  describe('getTransformation', () => {
    it('should fetch a specific transformation successfully', async () => {
      const mockTransformation: Transformation = {
        id: 'trans123',
        user_id: 'user123',
        document_id: 'doc123',
        transformation_type: TransformationType.EMAIL_SEQUENCE,
        parameters: { wordCount: 1000, tone: 'persuasive' },
        status: TransformationStatus.PROCESSING,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      mockedApi.get.mockResolvedValue({ data: mockTransformation });

      const result = await getTransformation('trans123');

      expect(mockedApi.get).toHaveBeenCalledWith('/transformations/trans123');
      expect(result).toEqual(mockTransformation);
    });

    it('should handle transformation not found', async () => {
      const error = new Error('Transformation not found');
      mockedApi.get.mockRejectedValue(error);

      await expect(getTransformation('nonexistent')).rejects.toThrow('Transformation not found');
    });
  });

  describe('deleteTransformation', () => {
    it('should delete transformation successfully', async () => {
      mockedApi.delete.mockResolvedValue({ data: {} });

      await deleteTransformation('trans123');

      expect(mockedApi.delete).toHaveBeenCalledWith('/transformations/trans123');
    });

    it('should handle delete errors', async () => {
      const error = new Error('Delete failed');
      mockedApi.delete.mockRejectedValue(error);

      await expect(deleteTransformation('trans123')).rejects.toThrow('Delete failed');
    });
  });

  describe('getTransformationStatus', () => {
    it('should fetch transformation status successfully', async () => {
      const mockStatus = {
        id: 'trans123',
        status: 'processing',
        progress: 50,
        database_status: 'processing'
      };

      mockedApi.get.mockResolvedValue({ data: mockStatus });

      const result = await getTransformationStatus('trans123');

      expect(mockedApi.get).toHaveBeenCalledWith('/transformations/trans123/status');
      expect(result).toEqual(mockStatus);
    });

    it('should handle status fetch errors', async () => {
      const error = new Error('Status fetch failed');
      mockedApi.get.mockRejectedValue(error);

      await expect(getTransformationStatus('trans123')).rejects.toThrow('Status fetch failed');
    });
  });

  describe('cancelTransformation', () => {
    it('should cancel transformation successfully', async () => {
      const mockCancelResponse = {
        id: 'trans123',
        status: 'cancelled',
        message: 'Transformation cancelled successfully'
      };

      mockedApi.post.mockResolvedValue({ data: mockCancelResponse });

      const result = await cancelTransformation('trans123');

      expect(mockedApi.post).toHaveBeenCalledWith('/transformations/trans123/cancel');
      expect(result).toEqual(mockCancelResponse);
    });

    it('should handle cancellation errors', async () => {
      const error = new Error('Cancellation failed');
      mockedApi.post.mockRejectedValue(error);

      await expect(cancelTransformation('trans123')).rejects.toThrow('Cancellation failed');
    });
  });

  describe('pollTransformationStatus', () => {
    it('should poll status and call onUpdate', async () => {
      const mockStatus = {
        id: 'trans123',
        status: 'processing',
        progress: 25,
        database_status: 'processing'
      };

      mockedApi.get.mockResolvedValue({ data: mockStatus });

      const onUpdate = jest.fn();
      const onComplete = jest.fn();

      const stopPolling = pollTransformationStatus('trans123', onUpdate, onComplete, 1000);

      // Fast forward to trigger the first poll
      jest.runOnlyPendingTimers();
      for (let i = 0; i < 10; i += 1) await Promise.resolve();

      expect(mockedApi.get).toHaveBeenCalledWith('/transformations/trans123/status');
      expect(onUpdate).toHaveBeenCalledWith(mockStatus);
      expect(onComplete).not.toHaveBeenCalled();

      stopPolling();
    });

    it('should call onComplete when transformation is completed', async () => {
      const mockCompletedStatus = {
        id: 'trans123',
        status: 'completed',
        progress: 100,
        database_status: 'completed'
      };

      mockedApi.get.mockResolvedValue({ data: mockCompletedStatus });

      const onUpdate = jest.fn();
      const onComplete = jest.fn();

      pollTransformationStatus('trans123', onUpdate, onComplete, 1000);

      // Fast forward to trigger the poll
      jest.runOnlyPendingTimers();
      for (let i = 0; i < 10; i += 1) await Promise.resolve();

      expect(onUpdate).toHaveBeenCalledWith(mockCompletedStatus);
      expect(onComplete).toHaveBeenCalledWith(mockCompletedStatus);
    });

    it('should call onComplete when transformation fails', async () => {
      const mockFailedStatus = {
        id: 'trans123',
        status: 'failed',
        progress: 0,
        database_status: 'failed',
        error: 'Processing error'
      };

      mockedApi.get.mockResolvedValue({ data: mockFailedStatus });

      const onUpdate = jest.fn();
      const onComplete = jest.fn();

      pollTransformationStatus('trans123', onUpdate, onComplete, 1000);

      // Fast forward to trigger the poll
      jest.runOnlyPendingTimers();
      for (let i = 0; i < 10; i += 1) await Promise.resolve();

      expect(onUpdate).toHaveBeenCalledWith(mockFailedStatus);
      expect(onComplete).toHaveBeenCalledWith(mockFailedStatus);
    });

    it('should handle polling errors gracefully', async () => {
      const error = new Error('Network error');
      mockedApi.get.mockRejectedValue(error);

      const onUpdate = jest.fn();
      const onComplete = jest.fn();

      const stopPolling = pollTransformationStatus('trans123', onUpdate, onComplete, 1000);

      // Fast forward to trigger the first poll
      jest.runOnlyPendingTimers();
      await Promise.resolve(); // Allow promises to resolve

      expect(onUpdate).not.toHaveBeenCalled();
      expect(onComplete).not.toHaveBeenCalled();

      stopPolling();
    });

    it('should stop polling when stop function is called', async () => {
      const mockStatus = {
        id: 'trans123',
        status: 'processing',
        progress: 25,
        database_status: 'processing'
      };

      mockedApi.get.mockResolvedValue({ data: mockStatus });

      const onUpdate = jest.fn();
      const onComplete = jest.fn();

      const stopPolling = pollTransformationStatus('trans123', onUpdate, onComplete, 1000);

      // Stop polling immediately
      stopPolling();

      // Fast forward - should not trigger any calls
      jest.runOnlyPendingTimers();
      await Promise.resolve(); // Allow promises to resolve

      expect(mockedApi.get).not.toHaveBeenCalled();
      expect(onUpdate).not.toHaveBeenCalled();
    });

    it('should use correct polling interval', async () => {
      const mockStatus = {
        id: 'trans123',
        status: 'processing',
        progress: 25,
        database_status: 'processing'
      };

      mockedApi.get.mockResolvedValue({ data: mockStatus });

      const onUpdate = jest.fn();
      const onComplete = jest.fn();
      const customInterval = 5000;

      const stopPolling = pollTransformationStatus('trans123', onUpdate, onComplete, customInterval);

      // Fast forward by custom interval
      jest.advanceTimersByTime(customInterval);
      await Promise.resolve(); // Allow promises to resolve

      expect(mockedApi.get).toHaveBeenCalledTimes(1);

      stopPolling();
    });
  });

  describe('edge cases', () => {
    it('should handle network timeouts', async () => {
      const timeoutError = new Error('Network timeout');
      mockedApi.get.mockRejectedValue(timeoutError);

      await expect(getUserTransformations()).rejects.toThrow('Network timeout');
    });

    it('should handle malformed responses', async () => {
      mockedApi.get.mockResolvedValue({ data: null });

      const result = await getUserTransformations();
      expect(result).toBeNull();
    });

    it('should handle invalid transformation types', async () => {
      const mockTransformationData = {
        document_id: 'doc123',
        transformation_type: 'INVALID_TYPE' as any,
        parameters: { wordCount: 500, tone: 'professional' }
      };

      const error = new Error('Invalid transformation type');
      mockedApi.post.mockRejectedValue(error);

      await expect(createTransformation(mockTransformationData)).rejects.toThrow('Invalid transformation type');
    });

    it('should handle empty parameters', async () => {
      const mockTransformationData: TransformationCreate = {
        document_id: 'doc123',
        transformation_type: TransformationType.SUMMARY,
        parameters: {}
      };

      const mockTransformation: Transformation = {
        id: 'trans123',
        user_id: 'user123',
        document_id: 'doc123',
        transformation_type: TransformationType.SUMMARY,
        parameters: {},
        status: TransformationStatus.PENDING,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      mockedApi.post.mockResolvedValue({ data: mockTransformation });

      const result = await createTransformation(mockTransformationData);

      expect(result.parameters).toEqual({});
    });
  });
});

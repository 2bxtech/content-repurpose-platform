/**
 * End-to-end tests for the content repurpose application
 * Tests complete user workflows including upload, transform, and real-time updates
 */

import { test, expect, Page, BrowserContext } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

class ContentRepurposeE2E {
  constructor(private page: Page) {}

  // Authentication helpers
  async login(username: string = 'testuser123', password: string = 'StrongPassword123!@#') {
    await this.page.goto('http://localhost:3000/login');
    
    await this.page.fill('[data-testid="username"]', username);
    await this.page.fill('[data-testid="password"]', password);
    await this.page.click('[data-testid="login-button"]');
    
    // Wait for redirect to dashboard
    await this.page.waitForURL('**/dashboard');
  }

  async register(username: string, email: string, password: string) {
    await this.page.goto('http://localhost:3000/register');
    
    await this.page.fill('[data-testid="username"]', username);
    await this.page.fill('[data-testid="email"]', email);
    await this.page.fill('[data-testid="password"]', password);
    await this.page.click('[data-testid="register-button"]');
    
    // Wait for success or redirect
    await this.page.waitForTimeout(2000);
  }

  // Document upload helpers
  async uploadDocument(filename: string, content: string, title: string, description: string = '') {
    // Create temporary file
    const tempDir = tmpdir();
    const filePath = join(tempDir, filename);
    writeFileSync(filePath, content);

    // Navigate to upload page
    await this.page.goto('http://localhost:3000/documents/upload');
    
    // Fill form
    await this.page.fill('[data-testid="document-title"]', title);
    if (description) {
      await this.page.fill('[data-testid="document-description"]', description);
    }
    
    // Upload file
    await this.page.setInputFiles('[data-testid="file-input"]', filePath);
    
    // Submit
    await this.page.click('[data-testid="upload-button"]');
    
    // Wait for upload completion
    await this.page.waitForSelector('[data-testid="upload-success"]', { timeout: 10000 });
    
    return filePath;
  }

  // Transformation helpers
  async createTransformation(sourceText: string, type: string, wordCount: number = 500, tone: string = 'professional') {
    await this.page.goto('http://localhost:3000/transformations/create');
    
    // Fill transformation form
    await this.page.fill('[data-testid="source-text"]', sourceText);
    await this.page.selectOption('[data-testid="transformation-type"]', type);
    await this.page.fill('[data-testid="word-count"]', wordCount.toString());
    await this.page.selectOption('[data-testid="tone"]', tone);
    
    // Submit transformation
    await this.page.click('[data-testid="create-transformation-button"]');
    
    // Wait for transformation to be created
    await this.page.waitForSelector('[data-testid="transformation-created"]', { timeout: 5000 });
  }

  // WebSocket helpers
  async waitForWebSocketConnection() {
    // Wait for WebSocket status indicator
    await this.page.waitForSelector('[data-testid="websocket-connected"]', { timeout: 10000 });
  }

  async waitForTransformationUpdate(transformationId: string, timeout: number = 30000) {
    // Wait for transformation status update via WebSocket
    await this.page.waitForSelector(`[data-testid="transformation-${transformationId}-status"]`, { timeout });
  }
}

test.describe('Content Repurpose E2E Tests', () => {
  let e2e: ContentRepurposeE2E;

  test.beforeEach(async ({ page }) => {
    e2e = new ContentRepurposeE2E(page);
  });

  test.describe('Authentication Flow', () => {
    test('should register new user successfully', async ({ page }) => {
      const timestamp = Date.now();
      const username = `testuser${timestamp}`;
      const email = `test${timestamp}@example.com`;
      const password = 'StrongPassword123!@#';

      await e2e.register(username, email, password);
      
      // Should show success message or redirect to login
      const successSelector = '[data-testid="registration-success"]';
      const loginRedirect = page.url().includes('/login');
      
      expect(await page.locator(successSelector).isVisible() || loginRedirect).toBeTruthy();
    });

    test('should login existing user successfully', async ({ page }) => {
      await e2e.login();
      
      // Should be redirected to dashboard
      expect(page.url()).toContain('/dashboard');
      
      // Should show user info
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
    });

    test('should handle login with invalid credentials', async ({ page }) => {
      await page.goto('http://localhost:3000/login');
      
      await page.fill('[data-testid="username"]', 'invaliduser');
      await page.fill('[data-testid="password"]', 'wrongpassword');
      await page.click('[data-testid="login-button"]');
      
      // Should show error message
      await expect(page.locator('[data-testid="login-error"]')).toBeVisible();
    });

    test('should logout user successfully', async ({ page }) => {
      await e2e.login();
      
      // Click user menu and logout
      await page.click('[data-testid="user-menu"]');
      await page.click('[data-testid="logout-button"]');
      
      // Should redirect to login page
      await page.waitForURL('**/login');
      expect(page.url()).toContain('/login');
    });
  });

  test.describe('Document Upload Flow', () => {
    test.beforeEach(async ({ page }) => {
      await e2e.login();
    });

    test('should upload PDF document successfully', async ({ page }) => {
      const content = 'This is a test PDF document content for transformation testing.';
      const filename = 'test-document.pdf';
      const title = 'Test PDF Document';
      const description = 'A test document for E2E testing';

      await e2e.uploadDocument(filename, content, title, description);
      
      // Should show success message
      await expect(page.locator('[data-testid="upload-success"]')).toBeVisible();
      
      // Should redirect to documents list
      await page.waitForURL('**/documents');
      
      // Should show uploaded document in list
      await expect(page.locator(`[data-testid="document-title"]:has-text("${title}")`)).toBeVisible();
    });

    test('should handle upload validation errors', async ({ page }) => {
      await page.goto('http://localhost:3000/documents/upload');
      
      // Try to upload without file
      await page.fill('[data-testid="document-title"]', 'Test Document');
      await page.click('[data-testid="upload-button"]');
      
      // Should show validation error
      await expect(page.locator('[data-testid="upload-error"]')).toBeVisible();
    });

    test('should handle unsupported file types', async ({ page }) => {
      const tempDir = tmpdir();
      const executablePath = join(tempDir, 'malicious.exe');
      writeFileSync(executablePath, 'fake executable content');

      await page.goto('http://localhost:3000/documents/upload');
      
      await page.fill('[data-testid="document-title"]', 'Malicious File');
      await page.setInputFiles('[data-testid="file-input"]', executablePath);
      await page.click('[data-testid="upload-button"]');
      
      // Should show file type error
      await expect(page.locator('[data-testid="file-type-error"]')).toBeVisible();
    });

    test('should display document preview after upload', async ({ page }) => {
      const content = 'Document content with preview testing.';
      const filename = 'preview-test.pdf';
      const title = 'Preview Test Document';

      await e2e.uploadDocument(filename, content, title);
      
      // Navigate to documents list
      await page.goto('http://localhost:3000/documents');
      
      // Click on document to view details
      await page.click(`[data-testid="document-${title}"]`);
      
      // Should show document details
      await expect(page.locator('[data-testid="document-content"]')).toBeVisible();
    });
  });

  test.describe('Transformation Flow', () => {
    test.beforeEach(async ({ page }) => {
      await e2e.login();
    });

    test('should create blog post transformation', async ({ page }) => {
      const sourceText = 'This is source content that will be transformed into a professional blog post with engaging headlines and structured paragraphs.';
      
      await e2e.createTransformation(sourceText, 'BLOG_POST', 800, 'professional');
      
      // Should show transformation created
      await expect(page.locator('[data-testid="transformation-created"]')).toBeVisible();
      
      // Should redirect to transformations list
      await page.waitForURL('**/transformations');
      
      // Should show transformation in list
      await expect(page.locator('[data-testid="transformation-type"]:has-text("BLOG_POST")')).toBeVisible();
    });

    test('should create social media transformation', async ({ page }) => {
      const sourceText = 'Quick social media content for engagement and brand awareness.';
      
      await e2e.createTransformation(sourceText, 'SOCIAL_MEDIA', 280, 'casual');
      
      // Should show transformation created
      await expect(page.locator('[data-testid="transformation-created"]')).toBeVisible();
      
      // Verify social media specific parameters
      await page.goto('http://localhost:3000/transformations');
      await expect(page.locator('[data-testid="transformation-type"]:has-text("SOCIAL_MEDIA")')).toBeVisible();
    });

    test('should handle transformation validation errors', async ({ page }) => {
      await page.goto('http://localhost:3000/transformations/create');
      
      // Try to create transformation without source text
      await page.selectOption('[data-testid="transformation-type"]', 'BLOG_POST');
      await page.click('[data-testid="create-transformation-button"]');
      
      // Should show validation error
      await expect(page.locator('[data-testid="source-text-error"]')).toBeVisible();
    });

    test('should show transformation progress', async ({ page }) => {
      const sourceText = 'Content for progress tracking test.';
      
      await e2e.createTransformation(sourceText, 'EMAIL_SEQUENCE', 600, 'persuasive');
      
      // Should show processing status
      await expect(page.locator('[data-testid="transformation-status"]:has-text("processing")')).toBeVisible();
    });
  });

  test.describe('WebSocket Real-time Updates', () => {
    test.beforeEach(async ({ page }) => {
      await e2e.login();
      await e2e.waitForWebSocketConnection();
    });

    test('should receive real-time transformation updates', async ({ page }) => {
      const sourceText = 'Content for real-time update testing.';
      
      // Create transformation
      await e2e.createTransformation(sourceText, 'NEWSLETTER', 1000, 'informative');
      
      // Navigate to transformations list
      await page.goto('http://localhost:3000/transformations');
      
      // Should receive WebSocket updates for transformation progress
      await expect(page.locator('[data-testid="websocket-connected"]')).toBeVisible();
      
      // Wait for status updates (simulated)
      await page.waitForTimeout(2000);
      
      // Should show real-time status
      const statusElements = await page.locator('[data-testid*="transformation-status"]').count();
      expect(statusElements).toBeGreaterThan(0);
    });

    test('should handle WebSocket connection errors gracefully', async ({ page }) => {
      // Navigate to a page that uses WebSocket
      await page.goto('http://localhost:3000/transformations');
      
      // Simulate network interruption
      await page.setOfflineMode(true);
      await page.waitForTimeout(1000);
      await page.setOfflineMode(false);
      
      // Should attempt to reconnect
      await expect(page.locator('[data-testid="websocket-reconnecting"]')).toBeVisible();
      
      // Should eventually reconnect
      await expect(page.locator('[data-testid="websocket-connected"]')).toBeVisible({ timeout: 10000 });
    });

    test('should show workspace presence', async ({ page, context }) => {
      // Open second tab to simulate multiple users
      const secondPage = await context.newPage();
      const secondE2E = new ContentRepurposeE2E(secondPage);
      
      await secondE2E.login();
      await secondE2E.waitForWebSocketConnection();
      
      // Navigate both to same workspace
      await page.goto('http://localhost:3000/transformations');
      await secondPage.goto('http://localhost:3000/transformations');
      
      // Should show presence indicators
      await expect(page.locator('[data-testid="workspace-presence"]')).toBeVisible();
      
      await secondPage.close();
    });
  });

  test.describe('Complete End-to-End Workflow', () => {
    test('should complete full document upload and transformation workflow', async ({ page }) => {
      await e2e.login();
      await e2e.waitForWebSocketConnection();

      // Step 1: Upload document
      const content = 'Comprehensive content for full workflow testing. This document will be uploaded and then transformed into multiple content types to test the complete system functionality.';
      const filename = 'workflow-test.pdf';
      const title = 'Workflow Test Document';

      await e2e.uploadDocument(filename, content, title);
      
      // Verify upload success
      await expect(page.locator('[data-testid="upload-success"]')).toBeVisible();
      
      // Step 2: Navigate to documents and verify
      await page.goto('http://localhost:3000/documents');
      await expect(page.locator(`[data-testid="document-title"]:has-text("${title}")`)).toBeVisible();
      
      // Step 3: Create transformation from uploaded content
      await e2e.createTransformation(content, 'BLOG_POST', 1200, 'professional');
      
      // Verify transformation creation
      await expect(page.locator('[data-testid="transformation-created"]')).toBeVisible();
      
      // Step 4: Monitor transformation progress via WebSocket
      await page.goto('http://localhost:3000/transformations');
      await expect(page.locator('[data-testid="transformation-type"]:has-text("BLOG_POST")')).toBeVisible();
      
      // Step 5: Create additional transformation types
      await e2e.createTransformation(content, 'SOCIAL_MEDIA', 280, 'casual');
      await e2e.createTransformation(content, 'EMAIL_SEQUENCE', 500, 'persuasive');
      
      // Verify multiple transformations
      await page.goto('http://localhost:3000/transformations');
      await expect(page.locator('[data-testid="transformation-type"]:has-text("SOCIAL_MEDIA")')).toBeVisible();
      await expect(page.locator('[data-testid="transformation-type"]:has-text("EMAIL_SEQUENCE")')).toBeVisible();
      
      // Step 6: Verify workspace activity via WebSocket
      await expect(page.locator('[data-testid="websocket-connected"]')).toBeVisible();
    });

    test('should handle error scenarios in complete workflow', async ({ page }) => {
      await e2e.login();

      // Test 1: Invalid file upload
      const tempDir = tmpdir();
      const invalidFile = join(tempDir, 'invalid.txt');
      writeFileSync(invalidFile, 'plain text content');

      await page.goto('http://localhost:3000/documents/upload');
      await page.fill('[data-testid="document-title"]', 'Invalid Document');
      await page.setInputFiles('[data-testid="file-input"]', invalidFile);
      await page.click('[data-testid="upload-button"]');
      
      // Should show file type error
      await expect(page.locator('[data-testid="file-type-error"]')).toBeVisible();
      
      // Test 2: Empty transformation
      await page.goto('http://localhost:3000/transformations/create');
      await page.selectOption('[data-testid="transformation-type"]', 'BLOG_POST');
      await page.click('[data-testid="create-transformation-button"]');
      
      // Should show validation error
      await expect(page.locator('[data-testid="source-text-error"]')).toBeVisible();
      
      // Test 3: Network error handling
      await page.setOfflineMode(true);
      await page.fill('[data-testid="source-text"]', 'Test content');
      await page.click('[data-testid="create-transformation-button"]');
      
      // Should show network error
      await expect(page.locator('[data-testid="network-error"]')).toBeVisible();
      
      await page.setOfflineMode(false);
    });

    test('should maintain state across page refreshes', async ({ page }) => {
      await e2e.login();

      // Upload document
      const content = 'State persistence test content.';
      await e2e.uploadDocument('state-test.pdf', content, 'State Test Document');
      
      // Refresh page
      await page.reload();
      
      // Should still be logged in
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
      
      // Navigate to documents
      await page.goto('http://localhost:3000/documents');
      
      // Document should still be there
      await expect(page.locator('[data-testid="document-title"]:has-text("State Test Document")')).toBeVisible();
      
      // Create transformation
      await e2e.createTransformation(content, 'SUMMARY', 300, 'concise');
      
      // Refresh transformations page
      await page.goto('http://localhost:3000/transformations');
      await page.reload();
      
      // Should still show transformations
      await expect(page.locator('[data-testid="transformation-type"]:has-text("SUMMARY")')).toBeVisible();
    });
  });

  test.describe('Performance and Load Testing', () => {
    test('should handle multiple concurrent uploads', async ({ page, context }) => {
      await e2e.login();

      const uploadPromises = [];
      
      // Create multiple upload promises
      for (let i = 0; i < 3; i++) {
        const content = `Concurrent upload test content ${i + 1}`;
        const title = `Concurrent Document ${i + 1}`;
        
        uploadPromises.push(e2e.uploadDocument(`concurrent-${i}.pdf`, content, title));
      }
      
      // Wait for all uploads to complete
      await Promise.all(uploadPromises);
      
      // Verify all documents are uploaded
      await page.goto('http://localhost:3000/documents');
      
      for (let i = 0; i < 3; i++) {
        await expect(page.locator(`[data-testid="document-title"]:has-text("Concurrent Document ${i + 1}")`)).toBeVisible();
      }
    });

    test('should handle large file upload gracefully', async ({ page }) => {
      await e2e.login();

      // Create large content
      const largeContent = 'Large file content. '.repeat(10000); // ~200KB
      
      await page.goto('http://localhost:3000/documents/upload');
      await page.fill('[data-testid="document-title"]', 'Large Document');
      
      // Create temporary large file
      const tempDir = tmpdir();
      const largeFile = join(tempDir, 'large-document.pdf');
      writeFileSync(largeFile, largeContent);
      
      await page.setInputFiles('[data-testid="file-input"]', largeFile);
      await page.click('[data-testid="upload-button"]');
      
      // Should show upload progress
      await expect(page.locator('[data-testid="upload-progress"]')).toBeVisible();
      
      // Should complete successfully
      await expect(page.locator('[data-testid="upload-success"]')).toBeVisible({ timeout: 30000 });
    });
  });
});

// Test configuration
test.use({
  baseURL: 'http://localhost:3000',
  trace: 'on-first-retry',
  screenshot: 'only-on-failure',
  video: 'retain-on-failure'
});

// Global test setup
test.beforeAll(async () => {
  // Ensure test temp directory exists
  const testTempDir = join(tmpdir(), 'e2e-test-files');
  try {
    mkdirSync(testTempDir, { recursive: true });
  } catch (error) {
    // Directory might already exist
  }
});

test.afterAll(async () => {
  // Cleanup test files if needed
  console.log('E2E tests completed');
});
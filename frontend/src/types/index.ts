// User and Authentication types
export interface User {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface UserRegister extends UserLogin {
  username: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

// Document types
export enum DocumentStatus {
  PENDING = "PENDING",
  PROCESSING = "PROCESSING",
  COMPLETED = "COMPLETED",
  FAILED = "FAILED"
}

export interface Document {
  id: string;
  user_id: string;
  title: string;
  description?: string;
  file_path: string;
  original_filename: string;
  content_type: string;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
}

export interface DocumentList {
  documents: Document[];
  count: number;
}

// Transformation types
export enum TransformationType {
  BLOG_POST = "BLOG_POST",
  SOCIAL_MEDIA = "SOCIAL_MEDIA",
  EMAIL_SEQUENCE = "EMAIL_SEQUENCE",
  NEWSLETTER = "NEWSLETTER",
  SUMMARY = "SUMMARY",
  CUSTOM = "CUSTOM"
}

export enum TransformationStatus {
  PENDING = "PENDING",
  PROCESSING = "PROCESSING",
  COMPLETED = "COMPLETED",
  FAILED = "FAILED"
}

export interface TransformationParameters {
  [key: string]: any;
}

export interface Transformation {
  id: string;
  user_id: string;
  document_id: string;
  transformation_type: TransformationType;
  parameters: TransformationParameters;
  status: TransformationStatus;
  result?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface TransformationList {
  transformations: Transformation[];
  count: number;
}

export interface TransformationCreate {
  document_id: string;
  transformation_type: TransformationType;
  parameters: TransformationParameters;
  preset_id?: string; // Optional preset ID to load parameters from
}

// Transformation Preset types
export interface PresetCreate {
  name: string;
  description?: string;
  transformation_type: TransformationType;
  parameters: TransformationParameters;
  is_shared: boolean;
}

export interface PresetUpdate {
  name?: string;
  description?: string;
  parameters?: TransformationParameters;
  is_shared?: boolean;
}

export interface PresetResponse {
  id: string;
  workspace_id: string;
  user_id: string;
  name: string;
  description?: string;
  transformation_type: TransformationType;
  parameters: TransformationParameters;
  is_shared: boolean;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface PresetList {
  presets: PresetResponse[];
  count: number;
}

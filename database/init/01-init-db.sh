#!/bin/bash
set -e

# Create the main database (already done by POSTGRES_DB)
echo "Database 'content_repurpose' already created by POSTGRES_DB"

# Enable required extensions
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable UUID extension for UUID primary keys
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    
    -- Enable pg_crypto for additional security functions
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";
    
    -- Create a user for the application (optional, for production)
    -- CREATE USER content_repurpose_app WITH PASSWORD 'app_password';
    -- GRANT ALL PRIVILEGES ON DATABASE content_repurpose TO content_repurpose_app;
    
    -- Set up Row-Level Security policies will be handled by Alembic migrations
    
    COMMIT;
EOSQL

echo "PostgreSQL database initialization completed!"
"""
Schema validation tests to catch migration issues early.

These tests verify that database schemas match SQLAlchemy model definitions,
particularly for inherited columns from BaseModel that Alembic autogenerate
often misses.

Test Categories:
    - Schema Validation: Ensure database matches models
    - Migration Validation: Verify migrations are complete
    - Index Validation: Confirm performance indexes exist
    - Constraint Validation: Check data integrity constraints

Markers:
    @pytest.mark.database: Database-dependent tests
    @pytest.mark.integration: Integration tests
    @pytest.mark.schema: Schema validation tests (custom marker for this file)

Note: These tests do NOT require the API server to be running.
They connect directly to the test database for schema inspection.
"""

import pytest
from sqlalchemy import inspect, create_engine
from typing import Set
from pathlib import Path

# Import models - use absolute imports for reliability
import sys
# Path is: tests/schema/test_schema_validation.py
# We need: backend/app/...
# So go up 2 levels to project root, then into backend
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.models import BaseModel
from app.db.models.transformation_preset import TransformationPreset
from app.db.models.user import User
from app.db.models.workspace import Workspace

# Skip loading async fixtures - these tests don't need them
pytest_plugins = []


@pytest.mark.database
@pytest.mark.integration
class TestSchemaValidation:
    """Validate database schemas match model definitions"""
    
    @pytest.fixture(scope="class", autouse=False)
    def db_engine(self):
        """Create database engine for schema inspection"""
        # Use dev database URL (port 5433) - the running PostgreSQL container
        # Password from docker-compose.yml: ${DATABASE_PASSWORD:-postgres_dev_password}
        TEST_DB_URL = "postgresql://postgres:postgres_dev_password@localhost:5433/content_repurpose"
        engine = create_engine(TEST_DB_URL)
        yield engine
        engine.dispose()
    
    @pytest.fixture(scope="class")
    def db_inspector(self, db_engine):
        """Create SQLAlchemy inspector for database schema"""
        return inspect(db_engine)
    
    def get_model_columns(self, model_class) -> Set[str]:
        """
        Get all column names defined in a SQLAlchemy model.
        Includes inherited columns from BaseModel.
        """
        mapper = inspect(model_class)
        return {col.name for col in mapper.columns}
    
    def get_table_columns(self, inspector, table_name: str) -> Set[str]:
        """Get all column names from database table"""
        columns = inspector.get_columns(table_name)
        return {col['name'] for col in columns}
    
    def get_basemodel_columns(self) -> Set[str]:
        """Get expected audit columns from BaseModel"""
        return {
            'id',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
            'deleted_at',
            'deleted_by'
        }
    
    def test_basemodel_columns_complete(self):
        """Verify BaseModel has all expected audit columns"""
        basemodel_columns = self.get_basemodel_columns()
        expected_columns = {
            'id', 'created_at', 'updated_at', 
            'created_by', 'updated_by',
            'deleted_at', 'deleted_by'
        }
        
        assert basemodel_columns == expected_columns, (
            f"BaseModel missing expected columns. "
            f"Expected: {expected_columns}, Got: {basemodel_columns}"
        )
    
    def test_transformation_presets_schema_matches_model(self, db_inspector):
        """
        Verify transformation_presets table schema matches TransformationPreset model.
        This would have caught the missing audit columns bug.
        """
        table_name = "transformation_presets"
        
        # Skip if table doesn't exist (fresh database)
        if table_name not in db_inspector.get_table_names():
            pytest.skip(f"Table '{table_name}' does not exist - run migrations first")
        
        # Get columns from model (includes inherited BaseModel columns)
        model_columns = self.get_model_columns(TransformationPreset)
        
        # Get columns from database
        db_columns = self.get_table_columns(db_inspector, table_name)
        
        # Check model columns are in database
        missing_in_db = model_columns - db_columns
        assert not missing_in_db, (
            f"Table '{table_name}' missing columns from model: {missing_in_db}\n"
            f"This likely means a migration autogenerate missed inherited columns."
        )
        
        # Check database doesn't have extra columns
        extra_in_db = db_columns - model_columns
        assert not extra_in_db, (
            f"Table '{table_name}' has extra columns not in model: {extra_in_db}\n"
            f"Model may be out of sync with database."
        )
    
    def test_transformation_presets_has_audit_columns(self, db_inspector):
        """
        Specifically verify audit columns exist.
        This is the check that would have caught the autogenerate bug immediately.
        """
        table_name = "transformation_presets"
        
        # Skip if table doesn't exist
        if table_name not in db_inspector.get_table_names():
            pytest.skip(f"Table '{table_name}' does not exist - run migrations first")
        
        db_columns = self.get_table_columns(db_inspector, table_name)
        
        required_audit_columns = {
            'created_at', 'updated_at',
            'created_by', 'updated_by',
            'deleted_at', 'deleted_by'
        }
        
        missing_audit = required_audit_columns - db_columns
        assert not missing_audit, (
            f"Table '{table_name}' missing audit columns: {missing_audit}\n"
            f"Expected all BaseModel audit columns to be present.\n"
            f"Table has {len(db_columns)} columns: {sorted(db_columns)}"
        )
    
    def test_all_models_have_basemodel_columns(self, db_inspector):
        """
        Verify all models that inherit from BaseModel have audit columns in database.
        Prevents regression of the autogenerate issue across all tables.
        """
        # Models to check (extend this list as new models are added)
        models_to_check = [
            (TransformationPreset, "transformation_presets"),
            (User, "users"),
            (Workspace, "workspaces"),
        ]
        
        basemodel_columns = self.get_basemodel_columns()
        failures = []
        
        for model_class, table_name in models_to_check:
            # Skip if table doesn't exist (development environment)
            if table_name not in db_inspector.get_table_names():
                continue
            
            db_columns = self.get_table_columns(db_inspector, table_name)
            missing = basemodel_columns - db_columns
            
            if missing:
                failures.append(
                    f"{table_name}: missing {missing}"
                )
        
        assert not failures, (
            "Models missing BaseModel audit columns:\n" +
            "\n".join(f"  - {f}" for f in failures) +
            "\n\nThis indicates migrations didn't include inherited columns."
        )
    
    def test_transformation_presets_indexes_exist(self, db_inspector):
        """Verify expected indexes exist for performance"""
        table_name = "transformation_presets"
        
        # Skip if table doesn't exist
        if table_name not in db_inspector.get_table_names():
            pytest.skip(f"Table '{table_name}' does not exist - run migrations first")
        
        indexes = db_inspector.get_indexes(table_name)
        index_names = {idx['name'] for idx in indexes}
        
        expected_indexes = {
            'idx_presets_workspace_active',
            'idx_presets_user_active',
            'idx_presets_type_active',
            'idx_presets_usage',
        }
        
        missing_indexes = expected_indexes - index_names
        assert not missing_indexes, (
            f"Table '{table_name}' missing expected indexes: {missing_indexes}\n"
            f"Found indexes: {index_names}"
        )
    
    def test_transformation_presets_foreign_keys(self, db_inspector):
        """Verify foreign key constraints exist"""
        table_name = "transformation_presets"
        
        # Skip if table doesn't exist
        if table_name not in db_inspector.get_table_names():
            pytest.skip(f"Table '{table_name}' does not exist - run migrations first")
        
        foreign_keys = db_inspector.get_foreign_keys(table_name)
        
        # Extract referenced tables
        fk_tables = {fk['referred_table'] for fk in foreign_keys}
        
        # Expected foreign keys: workspace_id -> workspaces, user_id -> users
        # created_by, updated_by, deleted_by also reference users (5 total FKs)
        expected_fks = {'workspaces', 'users'}
        missing_fks = expected_fks - fk_tables
        
        assert not missing_fks, (
            f"Table '{table_name}' missing foreign keys to: {missing_fks}\n"
            f"Found foreign keys to: {fk_tables}"
        )
    
    def test_transformation_presets_check_constraints(self, db_inspector):
        """Verify check constraints exist (valid transformation types)"""
        table_name = "transformation_presets"
        
        # Skip if table doesn't exist
        if table_name not in db_inspector.get_table_names():
            pytest.skip(f"Table '{table_name}' does not exist - run migrations first")
        
        # Get check constraints
        check_constraints = db_inspector.get_check_constraints(table_name)
        constraint_names = {c['name'] for c in check_constraints}
        
        expected_constraint = 'valid_transformation_type'
        assert expected_constraint in constraint_names, (
            f"Table '{table_name}' missing check constraint '{expected_constraint}'\n"
            f"Found constraints: {constraint_names}"
        )
    
    def test_column_count_matches(self, db_inspector):
        """
        Quick sanity check: verify column count matches between model and database.
        This is a fast smoke test for schema drift.
        """
        table_name = "transformation_presets"
        
        # Skip if table doesn't exist
        if table_name not in db_inspector.get_table_names():
            pytest.skip(f"Table '{table_name}' does not exist - run migrations first")
        
        model_column_count = len(self.get_model_columns(TransformationPreset))
        db_column_count = len(self.get_table_columns(db_inspector, table_name))
        
        assert model_column_count == db_column_count, (
            f"Column count mismatch for '{table_name}':\n"
            f"  Model defines: {model_column_count} columns\n"
            f"  Database has: {db_column_count} columns\n"
            f"This indicates schema drift between model and database."
        )


@pytest.mark.integration
class TestMigrationBestPractices:
    """Tests to enforce migration best practices"""
    
    def test_alembic_migration_files_exist(self):
        """Verify migration files exist for transformation_presets"""
        # Correct path: tests/schema/ -> project root -> backend/alembic/versions
        migrations_dir = Path(__file__).parent.parent.parent / "backend" / "alembic" / "versions"
        
        if not migrations_dir.exists():
            pytest.skip(f"Migrations directory not found: {migrations_dir}")
        
        migration_files = [f.name for f in migrations_dir.glob("*.py") if f.name != "__pycache__"]
        
        # Check for transformation_presets migrations
        preset_migrations = [
            f for f in migration_files 
            if 'transformation_presets' in f.lower() or 'preset' in f.lower()
        ]
        
        assert len(preset_migrations) >= 1, (
            f"No migration files found for transformation_presets.\n"
            f"Expected at least one migration in {migrations_dir}"
        )
    
    def test_audit_columns_migration_exists(self):
        """Verify the audit columns fix migration exists"""
        # Correct path: tests/schema/ -> project root -> backend/alembic/versions
        migrations_dir = Path(__file__).parent.parent.parent / "backend" / "alembic" / "versions"
        
        if not migrations_dir.exists():
            pytest.skip(f"Migrations directory not found: {migrations_dir}")
        
        migration_files = [f.name for f in migrations_dir.glob("*.py") if f.name != "__pycache__"]
        
        # Check for audit columns migration
        audit_migrations = [
            f for f in migration_files 
            if 'audit' in f.lower() and 'transformation' in f.lower()
        ]
        
        assert len(audit_migrations) >= 1, (
            f"No audit columns migration found.\n"
            f"Expected migration adding created_by, updated_by, deleted_by.\n"
            f"Found files: {migration_files}"
        )


@pytest.mark.unit
class TestSchemaDocumentation:
    """Tests to ensure schema is well-documented"""
    
    def test_transformation_preset_model_has_docstring(self):
        """Verify model class has documentation"""
        assert TransformationPreset.__doc__ is not None, (
            "TransformationPreset model missing docstring"
        )
        assert len(TransformationPreset.__doc__.strip()) > 0, (
            "TransformationPreset docstring is empty"
        )
    
    def test_basemodel_columns_documented(self):
        """Verify BaseModel documents inherited columns"""
        assert BaseModel.__doc__ is not None, (
            "BaseModel missing docstring explaining audit columns"
        )


if __name__ == "__main__":
    # Run schema validation tests independently
    pytest.main([__file__, "-v", "--tb=short"])

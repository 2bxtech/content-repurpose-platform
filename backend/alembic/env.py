import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the app directory to the path
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import the configuration and models
from app.core.config import Settings
from app.core.models import Base

# Create settings instance
settings = Settings()

# Import all models to ensure they're registered with SQLAlchemy

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override the sqlalchemy.url with a sync (psycopg2) URL derived from settings.
#
# IMPORTANT: On managed platforms (Railway, Heroku, etc.) the platform injects
# DATABASE_URL as a real environment variable but does NOT set DATABASE_URL_SYNC.
# We therefore prefer DATABASE_URL as the source of truth and only fall back to
# an explicit DATABASE_URL_SYNC when DATABASE_URL is absent. This avoids a stale
# DATABASE_URL_SYNC (e.g. from a baked-in dev .env) silently pointing migrations
# at the wrong host. get_database_url() also normalises postgres:// / postgresql://
# scheme quirks to a psycopg2-compatible URL.
if settings.DATABASE_URL:
    sync_url = settings.get_database_url(async_driver=False)
elif settings.DATABASE_URL_SYNC:
    sync_url = settings.DATABASE_URL_SYNC
else:
    # Use the constructed sync URL directly
    sync_url = f"postgresql+psycopg2://{settings.DATABASE_USER}:{settings.DATABASE_PASSWORD}@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"

config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

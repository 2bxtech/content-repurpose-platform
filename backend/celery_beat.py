#!/usr/bin/env python3
"""
Celery beat scheduler startup script for periodic tasks.
"""

import os
import sys

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from app.core.celery_app import celery_app

if __name__ == "__main__":
    # Start the Celery beat scheduler
    celery_app.start(argv=["celery", "beat", "--loglevel=info"])

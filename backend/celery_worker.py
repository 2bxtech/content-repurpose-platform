#!/usr/bin/env python3
"""
Celery worker startup script for the content repurposing tool.
"""

import os
import sys

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from app.core.celery_app import celery_app

if __name__ == "__main__":
    # Start the Celery worker
    celery_app.start()

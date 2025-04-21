"""
Database storage module for persisting job summaries - uses SQLite for thread-safe 
concurrent access and provides async methods for operation in FastAPI.
"""

import sqlite3
import os
import json
import aiosqlite
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any

# Path to the SQLite database
DB_PATH = os.path.join(os.environ.get("OUTPUT_DIR", os.path.join(os.getcwd(), "outputs")), "job_summaries.db")

def ensure_db_initialized():
    """Initialize the database if it doesn't exist"""
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create job_summaries table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_summaries (
            job_id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            tool TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            database_path TEXT NOT NULL,
            parameters TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            seq_count INTEGER,
            seq_lengths TEXT,
            cpu_count INTEGER,
            cpu_time_seconds REAL,
            result_files TEXT
        )
        ''')
        
        conn.commit()
        conn.close()

# Initialize DB on module import
ensure_db_initialized()


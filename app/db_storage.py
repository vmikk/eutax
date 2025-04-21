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

async def save_job_summary(
    job_id: str,
    file_id: str,
    tool: str,
    algorithm: str,
    database_path: str,
    parameters: Dict,
    status: str,
    created_at: datetime,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    seq_count: Optional[int] = None,
    seq_lengths: Optional[List[int]] = None,
    cpu_count: Optional[int] = None,
    cpu_time_seconds: Optional[float] = None,
    result_files: Optional[Dict[str, str]] = None
) -> None:
    """Save or update job summary information"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Convert parameters, seq_lengths and result_files to JSON
        parameters_json = json.dumps(parameters)
        seq_lengths_json = json.dumps(seq_lengths) if seq_lengths else None
        result_files_json = json.dumps(result_files) if result_files else None
        
        # Convert datetime objects to ISO format strings
        created_at_str = created_at.isoformat()
        started_at_str = started_at.isoformat() if started_at else None
        completed_at_str = completed_at.isoformat() if completed_at else None
        
        await db.execute('''
        INSERT OR REPLACE INTO job_summaries (
            job_id, file_id, tool, algorithm, database_path, parameters, 
            status, created_at, started_at, completed_at, 
            seq_count, seq_lengths, cpu_count, cpu_time_seconds, result_files
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_id, file_id, tool, algorithm, database_path, parameters_json,
            status, created_at_str, started_at_str, completed_at_str,
            seq_count, seq_lengths_json, cpu_count, cpu_time_seconds, result_files_json
        ))
        await db.commit()

async def get_job_summaries(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Get a list of job summaries"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute('''
        SELECT * FROM job_summaries
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        rows = await cursor.fetchall()
        
        result = []
        for row in rows:
            job_data = dict(row)
            
            # Parse JSON fields
            if job_data.get('parameters'):
                job_data['parameters'] = json.loads(job_data['parameters'])
            
            if job_data.get('seq_lengths'):
                job_data['seq_lengths'] = json.loads(job_data['seq_lengths'])
            
            if job_data.get('result_files'):
                job_data['result_files'] = json.loads(job_data['result_files'])
            
            result.append(job_data)
        
        return result

async def get_job_count() -> int:
    """Get the total number of jobs executed"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM job_summaries")
        row = await cursor.fetchone()
        return row[0] if row else 0


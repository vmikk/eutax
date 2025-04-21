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


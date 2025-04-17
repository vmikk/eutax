"""
Database module for managing data persistence - handles storage of uploaded files,
job information, and provides CRUD operations for the application's data.
"""

from typing import Dict, List, Optional
import os
from datetime import datetime
from app.models.models import JobStatusEnum

# In-memory storage for uploaded files
uploaded_files: Dict[str, str] = {}

# In-memory storage for jobs
jobs: Dict[str, Dict] = {}


def save_upload(file_id: str, filepath: str) -> None:
    """
    Save upload information
    """
    uploaded_files[file_id] = filepath


def get_upload(file_id: str) -> Optional[str]:
    """
    Get the filepath for uploaded sequences
    """
    return uploaded_files.get(file_id)


def save_job(job_id: str, file_id: str, tool: str, algorithm: str, database: str, parameters: Dict) -> None:
    """
    Save job information
    """
    jobs[job_id] = {
        "file_id": file_id,
        "tool": tool,
        "algorithm": algorithm,
        "database": database,
        "parameters": parameters,
        "status": JobStatusEnum.QUEUED,
        "created_at": datetime.now(),
        "started_at": None,
        "completed_at": None,
        "progress": None,
        "output_path": None,
        "result_files": None,
    }


def update_job_status(job_id: str, status: JobStatusEnum, progress: Optional[str] = None) -> bool:
    """
    Update job status
    """
    if job_id not in jobs:
        return False
    
    jobs[job_id]["status"] = status
    
    if progress:
        jobs[job_id]["progress"] = progress
    
    if status == JobStatusEnum.RUNNING and not jobs[job_id]["started_at"]:
        jobs[job_id]["started_at"] = datetime.now()
    
    if status in [JobStatusEnum.FINISHED, JobStatusEnum.FAILED]:
        jobs[job_id]["completed_at"] = datetime.now()
    
    return True


def update_job_results(job_id: str, result_files: Dict[str, str]) -> bool:
    """
    Update job with result file paths
    
    Args:
        job_id: Unique job identifier
        result_files: Dictionary of result file paths (e.g., {"raw": "/path/to/raw.txt", "json": "/path/to/results.json"})
        
    Returns:
        Boolean indicating success or failure
    """
    if job_id not in jobs:
        return False
    
    jobs[job_id]["result_files"] = result_files
    
    # For backward compatibility, also set the output_path
    if "raw" in result_files:
        jobs[job_id]["output_path"] = result_files["raw"]
        
    return True


def get_job(job_id: str) -> Optional[Dict]:
    """
    Get job information
    """
    return jobs.get(job_id)


def list_jobs(status: Optional[str] = None, limit: int = 10, offset: int = 0) -> tuple[List[Dict], int]:
    """
    List jobs with optional filtering by status
    """
    job_list = []
    
    for job_id, job_data in jobs.items():
        if status is None or job_data["status"] == status:
            job_list.append({
                "job_id": job_id,
                "status": job_data["status"],
                "started_at": job_data["started_at"]
            })
    
    total = len(job_list)
    paginated_jobs = job_list[offset:offset + limit]
    
    return paginated_jobs, total

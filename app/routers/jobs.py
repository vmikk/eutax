"""
Jobs router module - provides API endpoints for creating, monitoring, and listing
annotation jobs, including background task handling.
"""

import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Optional

from app.models.models import (
    JobRequest, 
    JobResponse, 
    JobStatusResponse, 
    JobStatusEnum, 
    JobListResponse, 
    PaginationInfo
)
from app import database
from app.runner import run_annotation

router = APIRouter()


@router.post("/jobs", response_model=JobResponse, status_code=202)
async def create_job(job_request: JobRequest, background_tasks: BackgroundTasks):
    """
    Create a new taxonomic annotation job.
    """
    # Validate file_id exists
    if not database.get_upload(job_request.file_id):
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"File ID '{job_request.file_id}' not found. Upload a FASTA file first."
            }
        })
    
    # Generate a unique job ID
    job_id = str(uuid.uuid4())
    
    # Store job in database
    database.save_job(
        job_id=job_id,
        file_id=job_request.file_id,
        tool=job_request.tool.value,
        algorithm=job_request.algorithm,
        database=job_request.database,
        parameters=job_request.parameters or {}
    )
    
    # Start background task for processing
    background_tasks.add_task(run_annotation, job_id)
    
    return JobResponse(
        job_id=job_id,
        status=JobStatusEnum.QUEUED,
        message="Job has been queued for processing."
    )


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get the status of a job.
    """
    job_data = database.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"Job ID '{job_id}' not found."
            }
        })
    
    return JobStatusResponse(
        job_id=job_id,
        status=job_data["status"],
        progress=job_data.get("progress"),
        started_at=job_data.get("started_at"),
        completed_at=job_data.get("completed_at")
    )


@router.get("/jobs/{job_id}/results/json")
async def get_job_results_json(job_id: str):
    """
    Download the job results in JSON format.
    Returns the results.json file created during job processing.
    """
    job_data = database.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"Job ID '{job_id}' not found."
            }
        })
    json_path = job_data["result_files"]["json"]
    
    # Return the file as a download
    return FileResponse(
        path=json_path,
        filename=f"job_{job_id}_results.json",
        media_type="application/json"
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter jobs by status: queued, running, finished, failed"),
    limit: int = Query(10, ge=1, le=100, description="Number of jobs to return"),
    offset: int = Query(0, ge=0, description="Starting position for pagination")
):
    """
    List all jobs with optional filtering by status.
    """
    # Validate status parameter if provided
    if status and status not in [s.value for s in JobStatusEnum]:
        raise HTTPException(status_code=400, detail={
            "error": {
                "code": 400,
                "message": f"Invalid status value: {status}. Valid values are: queued, running, finished, failed."
            }
        })
    
    jobs_list, total = database.list_jobs(status, limit, offset)
    
    return JobListResponse(
        jobs=jobs_list,
        pagination=PaginationInfo(
            limit=limit,
            offset=offset,
            total=total
        )
    )

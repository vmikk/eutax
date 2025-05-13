"""
Jobs router module - provides API endpoints for creating, monitoring, and listing
annotation jobs, including background task handling.
"""

import uuid
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional, List, Dict, Any

from app.models.models import (
    JobRequest, 
    JobResponse, 
    JobStatusResponse, 
    JobStatusEnum, 
    JobListResponse, 
    PaginationInfo
)
from app import database
from app import db_storage
from app.runner import run_annotation
from app.routers.refdbs import get_refdb_path
from app.limiter import limiter, rate_limits
from app.logging_config import get_logger

# Create logger
logger = get_logger("eutax.job_api")

router = APIRouter()


@router.post("/jobs", response_model=JobResponse, status_code=202)
@limiter.limit(rate_limits.get("create_job", "1000/minute"))
async def create_job(request: Request, response: Response, job_request: JobRequest, background_tasks: BackgroundTasks):
    """
    Create a new taxonomic annotation job.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    job_logger = get_logger("eutax.job_api", 
                           request_id=request_id, 
                           client_ip=client_ip,
                           file_id=job_request.file_id)
    
    job_logger.info(
        f"Job creation requested",
        event_type="job_creation_requested",
        tool=job_request.tool.value,
        algorithm=job_request.algorithm,
        database=job_request.database
    )
    
    # Validate file_id exists
    if not database.get_upload(job_request.file_id):
        job_logger.warning(
            f"Job creation failed: File ID '{job_request.file_id}' not found",
            event_type="job_creation_failed",
            error="file_not_found"
        )
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"File ID '{job_request.file_id}' not found. Upload a FASTA file first."
            }
        })
    
    # Resolve database path from the identifier
    try:
        resolved_db_path = get_refdb_path(
            job_request.database, 
            job_request.tool.value, 
            job_request.algorithm
        )
        
        job_logger.info(
            f"Database path resolved: {resolved_db_path}",
            event_type="job_db_resolved",
            database_id=job_request.database,
            resolved_path=resolved_db_path
        )
    except HTTPException as e:
        job_logger.warning(
            f"Job creation failed: Database '{job_request.database}' not found",
            event_type="job_creation_failed",
            error="database_not_found"
        )
        raise e
    except Exception as e:
        job_logger.error(
            f"Job creation failed: Error resolving database '{job_request.database}'",
            event_type="job_creation_failed",
            error="database_resolve_error",
            error_details=str(e)
        )
        raise HTTPException(status_code=400, detail={
            "error": {
                "code": 400,
                "message": f"Error resolving reference database '{job_request.database}': {str(e)}"
            }
        })
    
    # Generate a unique job ID
    job_id = str(uuid.uuid4())
    job_logger = job_logger.bind(job_id=job_id)
    
    # Store job in database
    database.save_job(
        job_id=job_id,
        file_id=job_request.file_id,
        tool=job_request.tool.value,
        algorithm=job_request.algorithm,
        database=resolved_db_path,  # Store the resolved path
        parameters=job_request.parameters or {}
    )
    
    job_logger.info(
        f"Job created and queued",
        event_type="job_created",
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
@limiter.limit(rate_limits.get("get_job_status", "1000/minute"))
async def get_job_status(request: Request, response: Response, job_id: str):
    """
    Get the status of a job.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    job_logger = get_logger("eutax.job_api", 
                           request_id=request_id, 
                           client_ip=client_ip,
                           job_id=job_id)
    
    job_logger.debug(
        f"Job status requested: {job_id}",
        event_type="job_status_requested"
    )
    
    job_data = database.get_job(job_id)
    if not job_data:
        job_logger.warning(
            f"Job status request failed: Job ID '{job_id}' not found",
            event_type="job_status_failed",
            error="job_not_found"
        )
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"Job ID '{job_id}' not found."
            }
        })
    
    job_logger.debug(
        f"Job status returned: {job_data['status']}",
        event_type="job_status_returned",
        status=job_data["status"]
    )
    
    return JobStatusResponse(
        job_id=job_id,
        status=job_data["status"],
        progress=job_data.get("progress"),
        started_at=job_data.get("started_at"),
        completed_at=job_data.get("completed_at")
    )


@router.get("/jobs/{job_id}/results/json")
@limiter.limit(rate_limits.get("get_job_results_json", "1000/minute"))
async def get_job_results_json(request: Request, response: Response, job_id: str):
    """
    Download the job results in JSON format.
    Returns the results.json file created during job processing.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    job_logger = get_logger("eutax.job_api", 
                           request_id=request_id, 
                           client_ip=client_ip,
                           job_id=job_id)
    
    job_logger.info(
        f"Job results requested: {job_id}",
        event_type="job_results_requested",
        format="json"
    )
    
    job_data = database.get_job(job_id)
    if not job_data:
        job_logger.warning(
            f"Job results request failed: Job ID '{job_id}' not found",
            event_type="job_results_failed",
            error="job_not_found"
        )
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"Job ID '{job_id}' not found."
            }
        })
    
    # Check job status
    if job_data["status"] != JobStatusEnum.FINISHED:
        job_logger.warning(
            f"Job results request failed: Job is not finished",
            event_type="job_results_failed",
            error="job_not_finished",
            current_status=job_data["status"]
        )
        raise HTTPException(status_code=400, detail={
            "error": {
                "code": 400,
                "message": f"Job is not finished yet. Current status: {job_data['status']}"
            }
        })
    
    # Check if JSON results exist
    if not job_data.get("result_files") or "json" not in job_data["result_files"]:
        job_logger.warning(
            f"Job results request failed: JSON results not available",
            event_type="job_results_failed",
            error="results_not_available"
        )
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": "JSON results not available for this job"
            }
        })
    
    json_path = job_data["result_files"]["json"]
    if not os.path.exists(json_path):
        job_logger.error(
            f"Job results request failed: JSON file not found",
            event_type="job_results_failed",
            error="results_file_missing",
            expected_path=json_path
        )
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": "JSON results file not found"
            }
        })
    
    # Get file size for logging
    file_size = os.path.getsize(json_path) if os.path.exists(json_path) else 0
    
    job_logger.info(
        f"Serving job results file",
        event_type="job_results_served",
        file_path=json_path,
        file_size=file_size
    )
    
    # Return the file as a download
    return FileResponse(
        path=json_path,
        filename=f"job_{job_id}_results.json",
        media_type="application/json"
    )


@router.get("/jobs", response_model=JobListResponse)
@limiter.limit(rate_limits.get("list_jobs", "1000/minute"))
async def list_jobs(request: Request, response: Response,
    status: Optional[str] = Query(None, description="Filter jobs by status: queued, running, finished, failed"),
    limit: int = Query(10, ge=1, le=100, description="Number of jobs to return"),
    offset: int = Query(0, ge=0, description="Starting position for pagination")
):
    """
    List all jobs with optional filtering by status.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    job_logger = get_logger("eutax.job_api", 
                           request_id=request_id, 
                           client_ip=client_ip)
    
    job_logger.debug(
        f"Listing jobs",
        event_type="jobs_list_requested",
        status_filter=status,
        limit=limit,
        offset=offset
    )
    
    # Validate status parameter if provided
    if status and status not in [s.value for s in JobStatusEnum]:
        job_logger.warning(
            f"List jobs request failed: Invalid status value",
            event_type="jobs_list_failed",
            error="invalid_status",
            invalid_status=status
        )
        raise HTTPException(status_code=400, detail={
            "error": {
                "code": 400,
                "message": f"Invalid status value: {status}. Valid values are: queued, running, finished, failed."
            }
        })
    
    jobs_list, total = database.list_jobs(status, limit, offset)
    
    job_logger.debug(
        f"Jobs list returned",
        event_type="jobs_list_returned",
        count=len(jobs_list),
        total=total
    )
    
    return JobListResponse(
        jobs=jobs_list,
        pagination=PaginationInfo(
            limit=limit,
            offset=offset,
            total=total
        )
    )


@router.get("/jobs/summaries", response_model=List[Dict[str, Any]])
@limiter.limit(rate_limits.get("get_job_summaries", "1000/minute"))
async def get_job_summaries(request: Request, response: Response,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of job summaries to return"),
    offset: int = Query(0, ge=0, description="Starting position for pagination")
):
    """
    Get detailed summaries of all jobs from the persistent SQLite database.
    Includes sequence counts, lengths, CPU metrics, and other job information.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    job_logger = get_logger("eutax.job_api", 
                           request_id=request_id, 
                           client_ip=client_ip)
    
    job_logger.debug(
        f"Job summaries requested",
        event_type="job_summaries_requested",
        limit=limit,
        offset=offset
    )
    
    summaries = await db_storage.get_job_summaries(limit, offset)
    
    job_logger.debug(
        f"Job summaries returned",
        event_type="job_summaries_returned",
        count=len(summaries)
    )
    
    return summaries


@router.get("/jobs/{job_id}/summary", response_model=Dict[str, Any])
@limiter.limit(rate_limits.get("get_job_summary", "1000/minute"))
async def get_job_summary(request: Request, response: Response, job_id: str):
    """
    Get detailed summary of a specific job from the persistent SQLite database.
    Includes sequence counts, lengths, CPU metrics, and other job information.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    job_logger = get_logger("eutax.job_api", 
                           request_id=request_id, 
                           client_ip=client_ip,
                           job_id=job_id)
    
    job_logger.debug(
        f"Job summary requested: {job_id}",
        event_type="job_summary_requested"
    )
    
    summary = await db_storage.get_job_summary(job_id)
    
    if not summary:
        job_logger.warning(
            f"Job summary request failed: Job ID '{job_id}' not found",
            event_type="job_summary_failed",
            error="job_not_found"
        )
        raise HTTPException(status_code=404, detail={
            "error": {
                "code": 404,
                "message": f"Job ID '{job_id}' not found or has no summary information."
            }
        })
    
    job_logger.debug(
        f"Job summary returned: {job_id}",
        event_type="job_summary_returned"
    )
    
    return summary

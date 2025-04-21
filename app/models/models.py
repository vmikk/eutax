"""
Models module - defines Pydantic models and enums for request validation,
response serialization, and data typing throughout the application.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from enum import Enum
from datetime import datetime


class ToolEnum(str, Enum):
    BLAST = "blast"
    VSEARCH = "vsearch"


class AlgorithmEnum(str, Enum):
    BLASTN = "blastn"
    MEGABLAST = "megablast"


class JobStatusEnum(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class SequenceUploadResponse(BaseModel):
    file_id: str
    filename: str
    upload_status: str
    message: str


class JobRequest(BaseModel):
    file_id: str = Field(..., description="Identifier for the uploaded sequence")
    tool: ToolEnum = Field(..., description="Tool to use (blast, vsearch)")
    algorithm: str = Field(..., description="Algorithm variant (blastn, megablast for BLAST)")
    database: str = Field(..., description="Database path or identifier")
    parameters: Optional[Dict[str, Union[str, int, float]]] = Field(
        {}, description="Additional tool-specific parameters"
    )


class JobResponse(BaseModel):
    job_id: str
    status: JobStatusEnum
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatusEnum
    progress: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobSummary(BaseModel):
    job_id: str
    status: JobStatusEnum
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PaginationInfo(BaseModel):
    limit: int
    offset: int
    total: int


class JobListResponse(BaseModel):
    jobs: List[JobSummary]
    pagination: PaginationInfo


class ErrorResponse(BaseModel):
    error: Dict[str, Union[int, str]]

"""
Models module - defines Pydantic models and enums for request validation,
response serialization, and data typing throughout the application.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from enum import Enum
from datetime import datetime
from pydantic import validator
import os
import re


class ToolEnum(str, Enum):
    BLAST = "blast"
    VSEARCH = "vsearch"


class AlgorithmEnum(str, Enum):
    # BLAST algorithms
    BLASTN = "blastn"
    MEGABLAST = "megablast"
    # VSEARCH algorithms
    USEARCH_GLOBAL = "usearch_global"
    SEARCH_EXACT = "search_exact"


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
    algorithm: AlgorithmEnum = Field(..., description="Algorithm variant for the selected tool (blastn, megablast for BLAST; usearch_global, search_exact for VSEARCH)")
    database: str = Field(..., description="Database path or identifier")
    parameters: Optional[Dict[str, Union[str, int, float]]] = Field(
        {}, description="Additional tool-specific parameters"
    )
    
    @validator('algorithm')
    def validate_algorithm_for_tool(cls, v, values):
        if 'tool' in values:
            if values['tool'] == ToolEnum.BLAST and v not in [AlgorithmEnum.BLASTN, AlgorithmEnum.MEGABLAST]:
                raise ValueError(f"Algorithm '{v}' not supported for BLAST. Use 'blastn' or 'megablast'")
            elif values['tool'] == ToolEnum.VSEARCH and v not in [AlgorithmEnum.USEARCH_GLOBAL, AlgorithmEnum.SEARCH_EXACT]:
                raise ValueError(f"Algorithm '{v}' not supported for VSEARCH. Use 'usearch_global' or 'search_exact'")
        return v
    
    @validator('database')
    def validate_database_path(cls, v, values):
        # Normalize path to handle any path traversal attempts
        normalized_path = os.path.normpath(v)
        
        # Check for path traversal patterns after normalization
        if '..' in normalized_path:
            raise ValueError("Path traversal detected in database path")
            
        # # TODO - Validate against allowed directories
        # if normalized_path.startswith('/'):
        #     allowed_db_dirs = [
        #         '/data/Eukaryome',
        #         '/data/DB'
        #     ]
        #     
        #     # Check if the path is within any allowed directory
        #     if not any(normalized_path.startswith(allowed_dir) for allowed_dir in allowed_db_dirs):
        #         raise ValueError(f"Database path must be within allowed directories: {', '.join(allowed_db_dirs)}")
        
        # Additional security: Only allow alphanumeric, underscore, dash, dot, and slashes
        if not re.match(r'^[a-zA-Z0-9_\-./]+$', normalized_path):
            raise ValueError("Database path contains invalid characters")
        
        # Validate file format based on tool and algorithm
        if 'tool' in values and values['tool'] == ToolEnum.VSEARCH:
            if 'algorithm' in values:
                if values['algorithm'] == AlgorithmEnum.USEARCH_GLOBAL:
                    if not normalized_path.endswith('.udb'):
                        raise ValueError("For VSEARCH with usearch_global algorithm, database must be in UDB format (*.udb)")
                elif values['algorithm'] == AlgorithmEnum.SEARCH_EXACT:
                    fasta_extensions = ['.fa', '.fasta', '.fa.gz', '.fasta.gz']
                    if not any(normalized_path.endswith(ext) for ext in fasta_extensions):
                        raise ValueError("For VSEARCH with search_exact algorithm, database must be in FASTA format (*.fa, *.fasta, *.fa.gz, *.fasta.gz)")
            
        return normalized_path
    
    @validator('parameters')
    def sanitize_parameters(cls, v):
        # Sanitize parameter values
        if v and isinstance(v, dict):
            for key, value in v.items():
                if isinstance(value, str) and any(c in value for c in ';&|`$()><'):
                    raise ValueError(f"Parameter '{key}' contains invalid characters")
        return v


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

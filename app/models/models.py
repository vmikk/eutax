"""
Models module - defines Pydantic models and enums for request validation,
response serialization, and data typing throughout the application.
"""

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime
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
    database: str = Field(..., description="Reference database identifier (e.g., 'eukaryome_its')")
    parameters: dict[str, str | int | float] = Field(
        default={}, description="Additional tool-specific parameters"
    )
    
    @field_validator('algorithm')
    @classmethod
    def validate_algorithm_for_tool(cls, v: AlgorithmEnum, info) -> AlgorithmEnum:
        # Access the tool field from the model data
        tool = info.data.get('tool') if info.data else None
        if tool:
            if tool == ToolEnum.BLAST and v not in [AlgorithmEnum.BLASTN, AlgorithmEnum.MEGABLAST]:
                raise ValueError(f"Algorithm '{v}' not supported for BLAST. Use 'blastn' or 'megablast'")
            elif tool == ToolEnum.VSEARCH and v not in [AlgorithmEnum.USEARCH_GLOBAL, AlgorithmEnum.SEARCH_EXACT]:
                raise ValueError(f"Algorithm '{v}' not supported for VSEARCH. Use 'usearch_global' or 'search_exact'")
        return v
    
    @field_validator('database')
    @classmethod
    def validate_database_identifier(cls, v: str) -> str:
        # Only allow alphanumeric characters, underscore, and dash in database identifiers
        if not re.match(r'^[a-zA-Z0-9_\-]+$', v):
            raise ValueError("Database identifier can only contain alphanumeric characters, underscore, and dash")
        
        # If the value contains slashes or dots, it's likely a file path which is not allowed
        if '/' in v or '\\' in v or '.' in v:
            raise ValueError("Custom database paths are not allowed. Use a predefined reference database identifier")
        
        return v
    
    @field_validator('parameters')
    @classmethod
    def sanitize_parameters(cls, v: dict[str, str | int | float]) -> dict[str, str | int | float]:
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
    progress: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobSummary(BaseModel):
    job_id: str
    status: JobStatusEnum
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PaginationInfo(BaseModel):
    limit: int
    offset: int
    total: int


class JobListResponse(BaseModel):
    jobs: list[JobSummary]
    pagination: PaginationInfo


class ErrorResponse(BaseModel):
    error: dict[str, int | str]


# ---- Reference database (refdb.yaml) models ----
class RefDbPaths(BaseModel):
    """
    Paths for a single reference database entry.

    Notes:
    - For BLAST, the config typically stores the *database prefix* (e.g. /data/db/NAME),
      not a single file with an extension.
    """

    blast: str | None = None
    vsearch_global: str | None = None
    vsearch_exact: str | None = None


class RefDbEntry(BaseModel):
    description: str = ""
    version: str = ""
    regions: list[str] = Field(default_factory=list)
    paths: RefDbPaths = Field(default_factory=RefDbPaths)


class RefDbConfig(BaseModel):
    refdbs: dict[str, RefDbEntry] = Field(default_factory=dict)

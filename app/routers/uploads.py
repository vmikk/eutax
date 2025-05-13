"""
Uploads router module - handles file upload endpoints for FASTA sequences,
including validation, storage, and file ID management.
"""

import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse
from typing import Optional
import tempfile

from app.models.models import SequenceUploadResponse
from app import database
from app.limiter import limiter, rate_limits
from app.logging_config import get_logger

# Create logger
logger = get_logger("eutax.uploads")

router = APIRouter()

# Directory for storing uploaded files
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.getcwd(), "wd/uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {".fasta", ".fa", ".fna", ".fa.gz", ".fna.gz", ".txt", ".txt.gz"}


def is_valid_fasta(filepath: str) -> bool:
    """
    Check if a file is a valid FASTA file.
    Very basic check: at least one line should start with '>'.
    """
    try:
        with open(filepath, "r") as f:
            for line in f:
                if line.startswith(">"):
                    return True
        return False
    except Exception:
        return False


@router.post("/upload", response_model=SequenceUploadResponse, status_code=201)
@limiter.limit(rate_limits.get("upload_fasta", "1000/minute"))
async def upload_fasta(request: Request, response: Response, file: UploadFile = File(...)):
    """
    Upload a FASTA file containing DNA sequences.
    Returns a unique file_id that can be used to reference the file in job creation.
    """
    request_id = request.headers.get("X-Request-ID", None)
    client_ip = request.client.host
    
    upload_logger = get_logger("eutax.uploads", 
                              request_id=request_id, 
                              client_ip=client_ip,
                              file_name=file.filename)
    
    upload_logger.info(
        f"Upload started: {file.filename}",
        event_type="upload_started",
        content_type=file.content_type
    )
    
    # Check file size
    MAX_SIZE = 50 * 1024 * 1024   # 50 MB
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        upload_logger.warning(
            f"Upload rejected: file too large ({len(content)} bytes)",
            event_type="upload_rejected",
            error="file_too_large",
            size=len(content),
            max_size=MAX_SIZE
        )
        raise HTTPException(status_code=413, detail={
            "error": {"code": 413, "message": "File too large"}})
    await file.seek(0)  # Reset file position
    
    # Check file extension
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        upload_logger.warning(
            f"Upload rejected: invalid file extension ({ext})",
            event_type="upload_rejected",
            error="invalid_extension",
            extension=ext,
            allowed_extensions=list(ALLOWED_EXTENSIONS)
        )
        raise HTTPException(status_code=400, detail={
            "error": {
                "code": 400,
                "message": f"Invalid file extension. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
            }
        })
    
    # Generate a unique sequence ID
    file_id = str(uuid.uuid4())
    upload_logger = upload_logger.bind(file_id=file_id)
    
    # Create a temporary file for validation
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    try:
        # Save uploaded file to temporary location
        with temp_file:
            shutil.copyfileobj(file.file, temp_file)
        
        upload_logger.info(
            f"File saved to temporary location: {temp_file.name}",
            event_type="upload_temp_saved",
            temp_path=temp_file.name,
            file_size=len(content)
        )
        
        # Check if the file is a valid FASTA file
        if not is_valid_fasta(temp_file.name):
            upload_logger.warning(
                f"Upload rejected: invalid FASTA format",
                event_type="upload_rejected",
                error="invalid_fasta_format"
            )
            raise HTTPException(status_code=400, detail={
                "error": {
                    "code": 400,
                    "message": "Invalid FASTA format. File must contain at least one record starting with '>'."
                }
            })
        
        # Create final filepath and save the file
        final_filepath = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
        shutil.move(temp_file.name, final_filepath)
        
        upload_logger.info(
            f"File moved to permanent location: {final_filepath}",
            event_type="upload_saved",
            path=final_filepath,
            file_size=len(content)
        )
        
        # Store upload info in the database
        database.save_upload(file_id, final_filepath)
        
        upload_logger.info(
            f"Upload successful: {file.filename}",
            event_type="upload_completed",
            file_size=len(content)
        )
        
        return SequenceUploadResponse(
            file_id=file_id,
            filename=file.filename,
            upload_status="success",
            message="File uploaded successfully."
        )
    
    except Exception as e:
        # Clean up temporary file if it exists
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
            
        upload_logger.error(
            f"Upload failed: {str(e)}",
            event_type="upload_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
            
        raise HTTPException(status_code=500, detail={
            "error": {
                "code": 500,
                "message": f"Error processing upload: {str(e)}"
            }
        })
    
    finally:
        # Close the file handle
        file.file.close()

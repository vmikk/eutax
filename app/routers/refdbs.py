"""
Reference database configuration endpoints for the EUTAX API.
Provides information about available reference databases for taxonomic annotation.
"""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import List, Dict, Optional
import yaml
import os
import logging
from app.limiter import limiter, rate_limits

# Configuration
REFDB_CONFIG_PATH = os.getenv("REFDB_CONFIG_PATH", "/app/app/config/refdb.yaml")

# Initialize router
router = APIRouter()

# Define response models
class RefDbInfo(BaseModel):
    id: str
    description: str
    version: str
    regions: List[str]
    tools_supported: List[str]

class RefDbsResponse(BaseModel):
    refdbs: List[RefDbInfo]

# Load reference database configuration
def load_refdb_config():
    """Load reference database configuration from YAML file"""
    try:
        if not os.path.exists(REFDB_CONFIG_PATH):
            logging.warning(f"Reference database configuration file not found: {REFDB_CONFIG_PATH}")
            return {}
        
        with open(REFDB_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        return config.get("refdbs", {})
    except Exception as e:
        logging.error(f"Error loading reference database configuration: {str(e)}")
        return {}

def get_refdb_path(refdb_id: str, tool: str, algorithm: str = None):
    """
    Get the appropriate reference database path for the given tool and algorithm
    
    Args:
        refdb_id: Reference database identifier
        tool: Tool name (blast, vsearch)
        algorithm: Algorithm name (optional)
        
    Returns:
        Path to the reference database file
    """
    config = load_refdb_config()
    
    if refdb_id not in config:
        raise HTTPException(status_code=404, detail=f"Reference database '{refdb_id}' not found")
    
    db_config = config[refdb_id]
    paths = db_config.get("paths", {})
    
    # Determine the appropriate path key
    if tool == "blast":
        path_key = "blast"
    elif tool == "vsearch":
        if algorithm == "usearch_global":
            path_key = "vsearch_global"
        elif algorithm == "search_exact":
            path_key = "vsearch_exact"
        else:
            path_key = "vsearch_global"  # Default for VSEARCH
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool}")
    
    if path_key not in paths:
        raise HTTPException(
            status_code=400, 
            detail=f"Reference database '{refdb_id}' does not support {tool}" + 
                  (f" with algorithm {algorithm}" if algorithm else "")
        )
    
    return paths[path_key]

@router.get("/refdbs", response_model=RefDbsResponse, tags=["Reference Databases"])
@limiter.limit(rate_limits.get("get_reference_databases", "1000/minute"))
async def get_reference_databases(request: Request, response: Response):
    """
    List available reference databases for taxonomic annotation.
    
    Returns information about each reference database including its ID, description,
    version, supported rRNA regions, and compatible tools.
    """
    config = load_refdb_config()
    
    refdbs = []
    for db_id, db_info in config.items():
        # Determine supported tools based on available paths
        paths = db_info.get("paths", {})
        tools_supported = []
        if "blast" in paths:
            tools_supported.append("blast")
        if any(k.startswith("vsearch_") for k in paths):
            tools_supported.append("vsearch")
        
        refdbs.append(
            RefDbInfo(
                id=db_id,
                description=db_info.get("description", ""),
                version=db_info.get("version", ""),
                regions=db_info.get("regions", []),
                tools_supported=tools_supported
            )
        )
    
    return RefDbsResponse(refdbs=refdbs)

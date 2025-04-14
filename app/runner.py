import os
import subprocess
import tempfile
from typing import Dict
import uuid
import logging
from app.models.models import JobStatusEnum
from app import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default output directory
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(os.getcwd(), "outputs"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Default database paths
DEFAULT_BLAST_DB = os.environ.get("BLAST_DB", "/mnt/Data/DB/EUKARYOME/EUKARYOME")
DEFAULT_BLAST_PARAMS = {
    "max_target_seqs": 10,
    "num_threads": 8
}
def run_blast(input_file: str, output_dir: str, algorithm: str, db_path: str, parameters: Dict) -> str:
    """
    Run BLAST command and return output file path.
    """
    # Use provided parameters or defaults
    max_target_seqs = parameters.get("max_target_seqs", DEFAULT_BLAST_PARAMS["max_target_seqs"])
    num_threads = parameters.get("num_threads", DEFAULT_BLAST_PARAMS["num_threads"])
    
    # Set output files
    results_file = os.path.join(output_dir, "res_blast.txt")
    
    # Build command
    cmd = [
        "blastn",
        "-task", algorithm,
        "-query", input_file,
        "-db", db_path,
        "-out", results_file,
        "-strand", "both",
        "-max_target_seqs", str(max_target_seqs),
        "-max_hsps", "1",
        "-outfmt", "6",
        "-num_threads", str(num_threads)
    ]
    
    logger.info(f"Running BLAST command: {' '.join(cmd)}")
    
    # Run command
    process = subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    if process.returncode != 0:
        raise Exception(f"BLAST command failed: {process.stderr}")
    
    return results_file



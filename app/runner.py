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
DEFAULT_UDB_DB = os.environ.get("UDB_DB", "/mnt/Data/DB/EUKARYOME.udb")

# Default parameters
DEFAULT_BLAST_PARAMS = {
    "max_target_seqs": 10,
    "num_threads": 8
}

DEFAULT_VSEARCH_PARAMS = {
    "id": 70,
    "query_cov": 50,
    "maxaccepts": 100,
    "maxrejects": 100,
    "maxhits": 100,
    "threads": 8
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


def run_vsearch(input_file: str, output_dir: str, db_path: str, parameters: Dict) -> str:
    """
    Run VSEARCH command and return output file path.
    """
    # Use provided parameters or defaults
    min_identity = parameters.get("id", DEFAULT_VSEARCH_PARAMS["id"])
    min_coverage = parameters.get("query_cov", DEFAULT_VSEARCH_PARAMS["query_cov"])
    maxaccepts = parameters.get("maxaccepts", DEFAULT_VSEARCH_PARAMS["maxaccepts"])
    maxrejects = parameters.get("maxrejects", DEFAULT_VSEARCH_PARAMS["maxrejects"])
    maxhits = parameters.get("maxhits", DEFAULT_VSEARCH_PARAMS["maxhits"])
    num_threads = parameters.get("threads", DEFAULT_VSEARCH_PARAMS["threads"])
    
    # Set output files
    results_file = os.path.join(output_dir, "res_blast.txt")
    # alignment_output = os.path.join(output_dir, "res_alignment.txt")
    
    # Build command
    cmd = [
        "vsearch",
        "--usearch_global", input_file,
        "--db", db_path,
        "--id", str(min_identity / 100),        # Convert from percentage to decimal
        "--query_cov", str(min_coverage / 100), # Convert from percentage to decimal
        "--blast6out", results_file,
        # "--alnout", alignment_output,
        "--strand", "both",
        "--maxaccepts", str(maxaccepts),
        "--maxrejects", str(maxrejects),
        "--maxhits", str(maxhits),
        "--threads", str(num_threads),
        "--quiet"
    ]
    
    logger.info(f"Running VSEARCH command: {' '.join(cmd)}")
    
    # Run command
    process = subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    if process.returncode != 0:
        raise Exception(f"VSEARCH command failed: {process.stderr}")
    
    return results_file

"""
Runner module for executing taxonomic annotation jobs - handles BLAST and VSEARCH command execution,
manages job output, and provides background task processing functionality.
"""

import os
import subprocess
import tempfile
from typing import Dict
import uuid
import logging
from app.models.models import JobStatusEnum
from app import database
from app.result_parsers import parse_blast_file_to_json

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


async def run_annotation(job_id: str):
    """
    Run the annotation and parse the results.
    """
    job_data = database.get_job(job_id)
    if not job_data:
        logger.error(f"Job {job_id} not found")
        return

    # Update job status to running
    database.update_job_status(job_id, JobStatusEnum.RUNNING)
    
    # Get parameters
    file_id = job_data["file_id"]
    tool = job_data["tool"]
    algorithm = job_data["algorithm"]
    db_path = job_data["database"]
    parameters = job_data["parameters"]
    
    # Get input file path
    input_file = database.get_upload(file_id)
    if not input_file or not os.path.exists(input_file):
        database.update_job_status(job_id, JobStatusEnum.FAILED)
        logger.error(f"Input file {input_file} for job {job_id} not found")
        return

    # Create job output directory
    job_output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_output_dir, exist_ok=True)
    
    try:
        # Run taxonomic annotation
        if tool.lower() == "blast":
            output_path = run_blast(
                input_file, 
                job_output_dir, 
                algorithm, 
                db_path or DEFAULT_BLAST_DB, 
                parameters
            )
            
            # Parse the BLAST results and save as JSON
            json_output_path = os.path.join(job_output_dir, "results.json")
            parse_blast_file_to_json(output_path, json_output_path)
            logger.info(f"Parsed BLAST results saved to {json_output_path}")
            
            # Add the JSON output path to the job data
            result_files = {
                "raw": output_path,
                "json": json_output_path
            }
            
        elif tool.lower() == "vsearch":
            output_path = run_vsearch(
                input_file, 
                job_output_dir, 
                db_path or DEFAULT_UDB_DB, 
                parameters
            )
            
            # For now, just store the raw output path for VSEARCH
            # TODO: Implement VSEARCH result parsing
            result_files = {
                "raw": output_path
            }
            
        else:
            raise ValueError(f"Unsupported tool: {tool}")
        
        # Update job status to finished
        database.update_job_status(job_id, JobStatusEnum.FINISHED)
        
        # Save output paths
        database.update_job_results(job_id, result_files)
        
        logger.info(f"Job {job_id} completed successfully")
    
    except Exception as e:
        database.update_job_status(job_id, JobStatusEnum.FAILED)
        logger.error(f"Error running job {job_id}: {str(e)}")


def run_blast(input_file: str, output_dir: str, algorithm: str, db_path: str, parameters: Dict) -> str:
    """
    Run BLAST command and return output file path.
    """
    # Use provided parameters or defaults
    max_target_seqs = parameters.get("max_target_seqs", DEFAULT_BLAST_PARAMS["max_target_seqs"])
    num_threads = parameters.get("num_threads", DEFAULT_BLAST_PARAMS["num_threads"])
    
    # Set output files
    results_file = os.path.join(output_dir, "res_blast.txt")
    
    # Output format (with extra columns 13+)
    outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore " \
             "qcovs sstrand qlen slen qseq sseq"

    #   1. qseqid      query or source (gene) sequence id
    #   2. sseqid      subject or target (reference genome) sequence id
    #   3. pident      percentage of identical positions
    #   4. length      alignment length (sequence overlap)
    #   5. mismatch    number of mismatches
    #   6. gapopen     number of gap openings
    #   7. qstart      start of alignment in query
    #   8. qend        end of alignment in query
    #   9. sstart      start of alignment in subject
    #  10. send        end of alignment in subject
    #  11. evalue      expect value
    #  12. bitscore    bit score
    #  13. qcovs       Query Coverage Per Subject
    #  14. sstrand     Subject Strand
    #  15. qlen        Query sequence length
    #  16. slen        Subject sequence length
    #  17. qseq        Aligned part of query sequence
    #  18. sseq        Aligned part of subject sequence

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
        "-outfmt", outfmt,
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

"""
Runner module for executing taxonomic annotation jobs - handles BLAST and VSEARCH command execution,
manages job output, and provides background task processing functionality.
"""

import os
import subprocess
import tempfile
from typing import Dict, List
import uuid
import logging
import asyncio
import concurrent.futures
import multiprocessing
import time
from Bio import SeqIO
from app.models.models import JobStatusEnum
from app import database
from app import db_storage
from app.result_parsers import parse_blast_file_to_json

# Configure logging with timestamp format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Determine total available CPUs and create resource management
TOTAL_CPUS = int(os.environ.get("MAX_CPUS", multiprocessing.cpu_count()))
logger.info(f"System has {TOTAL_CPUS} available CPUs")

# Maximum concurrent jobs (can be overridden with environment variable)
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", 2))

# Create a semaphore to limit concurrent jobs
# This ensures we don't exceed available system resources
job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

# Thread pool executor for running blocking operations
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)

# Default output directory
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(os.getcwd(), "outputs"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Default database paths
DEFAULT_BLAST_DB = os.environ.get("BLAST_DB", "/mnt/Data/DB/EUKARYOME/EUKARYOME")
DEFAULT_UDB_DB = os.environ.get("UDB_DB", "/mnt/Data/DB/EUKARYOME.udb")

# Default parameters
DEFAULT_BLAST_PARAMS = {
    "max_target_seqs": 20,
    "num_threads": 4
}

DEFAULT_VSEARCH_PARAMS = {
    "id": 70,
    "query_cov": 50,
    "maxaccepts": 100,
    "maxrejects": 100,
    "maxhits": 20,
    "threads": 4
}


async def run_annotation(job_id: str):
    """
    Run the annotation and parse the results.
    Uses a semaphore to limit concurrent resource usage.
    """
    # Acquire semaphore to limit concurrent jobs
    async with job_semaphore:
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
        
        # Calculate CPU allocation for this job based on total available
        # This ensures we don't oversubscribe CPUs across concurrent jobs
        allocated_cpus = calculate_cpu_allocation(tool, parameters)
        logger.info(f"Job {job_id} allocated {allocated_cpus} CPUs")
        
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
            # Record CPU time
            start_time = time.time()
            
            # Count sequences and get lengths
            seq_lengths = await count_sequence_lengths(input_file)
            sequence_count = len(seq_lengths)
            logger.info(f"Job {job_id} has {sequence_count} sequences")
            
            # Save initial job summary with sequence info to SQLite db
            await db_storage.save_job_summary(
                job_id=job_id,
                file_id=file_id,
                tool=tool,
                algorithm=algorithm,
                database_path=db_path or (DEFAULT_BLAST_DB if tool.lower() == "blast" else DEFAULT_UDB_DB),
                parameters=parameters,
                status=JobStatusEnum.RUNNING,
                created_at=job_data["created_at"],
                started_at=job_data["started_at"],
                seq_count=sequence_count,
                seq_lengths=seq_lengths,
                cpu_count=allocated_cpus
            )
            
            # Run taxonomic annotation in thread pool
            if tool.lower() == "blast":
                # Run BLAST in a non-blocking way using thread pool
                output_path = await run_blast_async(
                    input_file, 
                    job_output_dir, 
                    algorithm, 
                    db_path or DEFAULT_BLAST_DB, 
                    parameters
                )
                
                # Parse the BLAST results and save as JSON (also in thread pool)
                json_output_path = os.path.join(job_output_dir, "results.json")
                await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    parse_blast_file_to_json,
                    output_path, 
                    json_output_path
                )
                logger.info(f"Parsed BLAST results saved to {json_output_path}")
                
                # Add the JSON output path to the job data
                result_files = {
                    "raw": output_path,
                    "json": json_output_path
                }
                
            elif tool.lower() == "vsearch":
                # Run VSEARCH in a non-blocking way using thread pool
                output_path = await run_vsearch_async(
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
            
            # Calculate elapsed CPU time
            end_time = time.time()
            cpu_time_seconds = (end_time - start_time) * allocated_cpus  # Scale by CPU count
            
            # Update job status to finished
            database.update_job_status(job_id, JobStatusEnum.FINISHED)
            
            # Save output paths
            database.update_job_results(job_id, result_files)
            
            # Update job summary in SQLite db with final information
            await db_storage.save_job_summary(
                job_id=job_id,
                file_id=file_id,
                tool=tool,
                algorithm=algorithm,
                database_path=db_path or (DEFAULT_BLAST_DB if tool.lower() == "blast" else DEFAULT_UDB_DB),
                parameters=parameters,
                status=JobStatusEnum.FINISHED,
                created_at=job_data["created_at"],
                started_at=job_data["started_at"],
                completed_at=job_data["completed_at"],
                seq_count=sequence_count,
                seq_lengths=seq_lengths,
                cpu_count=allocated_cpus,
                cpu_time_seconds=round(cpu_time_seconds, 2),
                result_files=result_files
            )
            
            logger.info(f"Job {job_id} completed successfully in {cpu_time_seconds:.2f} CPU seconds")
        
        except Exception as e:
            database.update_job_status(job_id, JobStatusEnum.FAILED)
            
            # Update job summary in SQLite with error status
            await db_storage.save_job_summary(
                job_id=job_id,
                file_id=file_id,
                tool=tool,
                algorithm=algorithm,
                database_path=db_path or (DEFAULT_BLAST_DB if tool.lower() == "blast" else DEFAULT_UDB_DB),
                parameters=parameters,
                status=JobStatusEnum.FAILED,
                created_at=job_data["created_at"],
                started_at=job_data["started_at"],
                completed_at=job_data["completed_at"]
            )
            
            logger.error(f"Error running job {job_id}: {str(e)}")


async def count_sequence_lengths(fasta_path: str) -> List[int]:
    """
    Count sequences and return an array of sequence lengths.
    Returns a list of integers representing the length of each sequence.
    """
    def _count_sequence_lengths(path):
        lengths = []
        for record in SeqIO.parse(path, "fasta"):
            lengths.append(len(record.seq))
        return lengths
    
    # Run in thread pool to avoid blocking
    return await asyncio.get_event_loop().run_in_executor(
        thread_pool,
        _count_sequence_lengths,
        fasta_path
    )


def calculate_cpu_allocation(tool: str, parameters: Dict) -> int:
    """
    Calculate the number of CPU threads to allocate for a specific job
    based on the available system resources and concurrent job limit.
    
    Returns the number of CPUs to use for this job.
    """
    # Get requested number of threads from parameters
    if tool.lower() == "blast":
        requested_threads = parameters.get("num_threads", DEFAULT_BLAST_PARAMS["num_threads"])
    elif tool.lower() == "vsearch":
        requested_threads = parameters.get("threads", DEFAULT_VSEARCH_PARAMS["threads"])
    else:
        requested_threads = 1  # Default for unknown tools
    
    # Calculate a fair share based on available CPUs and max concurrent jobs
    fair_share = max(1, TOTAL_CPUS // MAX_CONCURRENT_JOBS)
    
    # Use the smaller of the requested amount and fair share
    return min(requested_threads, fair_share)


async def run_blast_async(input_file: str, output_dir: str, algorithm: str, db_path: str, parameters: Dict) -> str:
    """
    Asynchronous wrapper around run_blast to execute it in a thread pool.
    """
    # Adjust num_threads parameter based on available resources
    adjusted_parameters = parameters.copy()
    adjusted_parameters["num_threads"] = calculate_cpu_allocation("blast", parameters)
    
    return await asyncio.get_event_loop().run_in_executor(
        thread_pool,
        run_blast,
        input_file, output_dir, algorithm, db_path, adjusted_parameters
    )


async def run_vsearch_async(input_file: str, output_dir: str, db_path: str, parameters: Dict) -> Tuple[str, str]:
    """
    Asynchronous wrapper around run_vsearch to execute it in a thread pool.
    """
    # Adjust threads parameter based on available resources
    adjusted_parameters = parameters.copy()
    adjusted_parameters["threads"] = calculate_cpu_allocation("vsearch", parameters)
    
    return await asyncio.get_event_loop().run_in_executor(
        thread_pool,
        run_vsearch,
        input_file, output_dir, db_path, adjusted_parameters
    )


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


def run_vsearch(input_file: str, output_dir: str, db_path: str, parameters: Dict) -> Tuple[str, str]:
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
    results_file = os.path.join(output_dir, "res_vsearch.txt")
    alignment_output = os.path.join(output_dir, "res_alignment.txt")
    
    outfmt = "query+target+id+alnlen+mism+opens+qlo+qhi+tlo+thi+evalue+bits+qcov+qstrand+ql+tl"

    # query    Query label
    # target   Target label
    # id       The percentage of identity
    # alnlen   The length of the query-target alignment
    # mism     Number of mismatches in the alignment
    # opens    Number of columns containing a gap opening
    # qlo      First nucleotide of the query aligned with the target
    # qhi      Last nucleotide of the query aligned with the target
    # tlo      First nucleotide of the target aligned with the query
    # thi      Last nucleotide of the target aligned with the query
    # evalue   E-value (not computed for nucleotide alignments). Always set to -1.
    # bits     Bit score (not computed for nucleotide alignments). Always set to 0.
    # qcov     Query coverage
    # qstrand  Query strand orientation
    # ql       Query sequence length
    # tl       Target sequence length

    # Build command
    cmd = [
        "vsearch",
        "--usearch_global", input_file,
        "--db", db_path,
        "--id", str(min_identity / 100),        # Convert from percentage to decimal
        "--query_cov", str(min_coverage / 100), # Convert from percentage to decimal
        # "--blast6out", results_file,
        "--userout",  results_file,
        "--userfields", outfmt,
        "--alnout", alignment_output,
        "--rowlen", str(99999),
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
    
    return results_file, alignment_output

"""
Result parser module for processing and interpreting taxonomic annotation outputs from
tools like BLAST and VSEARCH to extract taxonomic information.
"""

import json
import pandas as pd
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path


########################################### Common functions

def parse_sseqid(sseqid: str) -> Dict[str, str]:
    """
    Parse the semicolon-separated sseqid field into its taxonomic components.
    
    Args:
        sseqid: The subject sequence ID with taxonomic information
        
    Returns:
        Dictionary with parsed taxonomic information
    """
    # Define the expected fields
    taxonomy_fields = ["accession", "kingdom", "phylum", "class", "order", "family", "genus", "species"]
    
    # Split the sseqid by semicolon
    parts = sseqid.split(';')
    
    # Create a dictionary, replace "." with None for missing values
    taxonomy = {}
    for i, field in enumerate(taxonomy_fields):
        if i < len(parts):
            taxonomy[field] = None if parts[i] == "." else parts[i]
        else:
            taxonomy[field] = None
            
    return taxonomy


def generate_midline(qseq: str, sseq: str) -> str:
    """
    Generate a midline string for alignment display showing matches and mismatches.
    
    Args:
        qseq: Query sequence (aligned part)
        sseq: Subject sequence (aligned part)
        
    Returns:
        Midline string with '|' for matches and ' ' for mismatches
    """
    midline = []
    for q, s in zip(qseq.upper(), sseq.upper()):
        if q == s:
            midline.append('|')
        else:
            # Gap in either sequences or mismatch
            midline.append(' ')
            
    return ''.join(midline)


def format_alignment(qseq: str, sseq: str) -> Dict[str, Any]:
    """
    Format alignment data for display in the frontend.
    
    Args:
        qseq: Query sequence
        sseq: Subject sequence
    
    Returns:
        Dictionary with formatted alignment information
    """
    midline = generate_midline(qseq, sseq)
    
    return {
        "qseq": qseq,
        "midline": midline,
        "sseq": sseq
    }


def parse_fasta(fasta_file: str) -> Dict[str, int]:
    """
    Extract sequence IDs and their lengths from a FASTA file.
    
    Args:
        fasta_file: Path to the FASTA file
        
    Returns:
        Dictionary mapping sequence IDs to their lengths
    """
    query_info = {}  # Maps query ID to sequence length
    current_id = None
    current_seq = []
    
    try:
        with open(fasta_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('>'):
                    # Save previous sequence if there was one
                    if current_id is not None:
                        query_info[current_id] = len(''.join(current_seq))
                    
                    # Extract ID without the '>' character and trim whitespace
                    current_id = line[1:].split()[0].strip()
                    current_seq = []
                elif current_id is not None:
                    # Append to current sequence
                    current_seq.append(line)
            
            # Save the last sequence
            if current_id is not None:
                query_info[current_id] = len(''.join(current_seq))
    except Exception as e:
        return {}
    
    return query_info


def get_taxonomy_from_sseqid(sseqid: str) -> Dict[str, str]:
    """
    Extract taxonomy information from subject sequence ID based on its format.
    
    Args:
        sseqid: The subject sequence ID
        
    Returns:
        Dictionary with taxonomy information
    """
    if ';' in sseqid:
        try:
            return parse_sseqid(sseqid)
        except:
            # Fallback for malformed identifiers
            return {"accession": sseqid, "species": sseqid}
    else:
        # For non-taxonomy format identifiers
        return {"accession": sseqid, "species": sseqid}


def initialize_results_structure() -> Dict[str, Any]:
    """
    Initialize the standard results structure.
    
    Returns:
        Empty results dictionary with standard structure
    """
    return {"results": [], "summary": {}}


def handle_empty_results(query_info: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Create a properly structured results object for the case when no hits are found.
    
    Args:
        query_info: Optional dictionary mapping query IDs to their sequence lengths
        
    Returns:
        Results dictionary with empty hits but correct query counts
    """
    result = initialize_results_structure()
    
    # If query_info is provided, use it to report the total_queries correctly
    total_queries = len(query_info) if query_info else 0
    
    # Create empty results with correct query count
    result["summary"] = {
        "total_queries": total_queries,
        "total_hits": 0
    }
    
    # If we have query information but no hits, add empty entries for each query
    if query_info:
        for qid, length in query_info.items():
            result["results"].append({
                "query_id": qid,
                "query_length": length,
                "hit_count": 0,
                "hits": []
            })
    
    return result


def add_missing_queries(result: Dict[str, Any], result_query_ids: Set[str], 
                        query_info: Dict[str, int]) -> Dict[str, Any]:
    """
    Add entries for queries that have no hits to the results.
    
    Args:
        result: Current results dictionary
        result_query_ids: Set of query IDs that have hits
        query_info: Dictionary mapping query IDs to their sequence lengths
        
    Returns:
        Updated results dictionary with entries for queries without hits
    """
    # Find query IDs that have no hits
    no_hit_queries = set(query_info.keys()) - result_query_ids
    
    # Add empty result entries for each query with no hits
    for qid in no_hit_queries:
        result["results"].append({
            "query_id": qid,
            "query_length": query_info[qid],
            "hit_count": 0,
            "hits": []
        })
    
    return result


def finalize_results(result: Dict[str, Any], total_queries: int, 
                     total_hits: int) -> Dict[str, Any]:
    """
    Add summary information to the results.
    
    Args:
        result: Current results dictionary
        total_queries: Total number of queries
        total_hits: Total number of hits
        
    Returns:
        Finalized results dictionary with summary information
    """
    result["summary"] = {
        "total_queries": total_queries,
        "total_hits": total_hits
    }
    
    return result


########################################### BLAST results

## Customized format for BLAST results (with extra columns 13+)
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



def parse_blast_results(file_path: str, query_info: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Parse BLAST output file and convert to structured JSON format.
    
    Args:
        file_path: Path to the BLAST output file
        query_info: Optional dictionary mapping query IDs to their sequence lengths
        
    Returns:
        Dictionary with parsed results grouped by query ID
    """
    # Define column names
    columns = [
        "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
        "qstart", "qend", "sstart", "send", "evalue", "bitscore",
        "qcovs", "sstrand", "qlen", "slen", "qseq", "sseq"
    ]
    
    # Read the tab-delimited file
    try:
        df = pd.read_csv(file_path, sep='\t', names=columns, header=None)
    except Exception as e:
        return {"error": f"Failed to parse BLAST results: {str(e)}"}
    
    # Handle empty result case
    if df.empty:
        return handle_empty_results(query_info)
    
    # Initialize result structure
    result = initialize_results_structure()
    
    # Get the set of query IDs from the results
    result_query_ids = set(df["qseqid"].unique())
    
    # Group by query ID
    query_groups = df.groupby("qseqid")
    
    for query_id, group in query_groups:
        # Convert the group to records for easier processing
        hits = []
        
        for _, row in group.iterrows():
            # Parse taxonomy from sseqid
            taxonomy = parse_sseqid(row["sseqid"])
            
            # Format the alignment
            alignment = format_alignment(row["qseq"], row["sseq"])
            
            # Create a hit entry
            hit = {
                "sseqid": row["sseqid"],
                "taxonomy": taxonomy,
                "pident": float(row["pident"]),
                "length": int(row["length"]),
                "mismatch": int(row["mismatch"]),
                "gapopen": int(row["gapopen"]),
                "qstart": int(row["qstart"]),
                "qend": int(row["qend"]),
                "sstart": int(row["sstart"]),
                "send": int(row["send"]),
                "evalue": float(row["evalue"]),
                "bitscore": float(row["bitscore"]),
                "qcovs": float(row["qcovs"]) if not pd.isna(row["qcovs"]) else None,
                "sstrand": row["sstrand"],
                "slen": int(row["slen"]) if not pd.isna(row["slen"]) else None,
                "alignment": alignment
            }
            
            hits.append(hit)
        
        # Sort hits (mainly by bitscore & evalue)
        hits.sort(key=lambda x: (-x["bitscore"], x["evalue"], -x["pident"], -x["length"], -x["qcovs"], x["sseqid"]))
        
        # Get query length from the results or from the provided query_info dictionary
        query_length = int(group["qlen"].iloc[0]) if not pd.isna(group["qlen"].iloc[0]) else None
        if query_length is None and query_info and query_id in query_info:
            query_length = query_info[query_id]
            
        # Add to results
        query_result = {
            "query_id": query_id,
            "query_length": query_length,
            "hit_count": len(hits),
            "hits": hits
        }
        
        result["results"].append(query_result)
    
    # If query_info was provided, add entries for queries with no hits
    if query_info:
        result = add_missing_queries(result, result_query_ids, query_info)
        total_queries = len(query_info)
    else:
        # If no query_info provided, use the count from the results
        total_queries = len(query_groups)
    
    # Add summary information
    return finalize_results(result, total_queries, len(df))


def parse_blast_file_to_json(file_path: str, output_path: Optional[str] = None, query_fasta: Optional[str] = None) -> str:
    """
    Parse a BLAST output file and save the results as JSON.
    
    Args:
        file_path: Path to the BLAST output file
        output_path: Optional path to save the JSON output (if None, JSON is returned as string)
        query_fasta: Optional path to the input FASTA file to extract query IDs
        
    Returns:
        JSON string or file path where JSON was saved
    """
    # Parse query information from FASTA if provided
    query_info = None
    if query_fasta:
        query_info = parse_fasta(query_fasta)
    
    results = parse_blast_results(file_path, query_info)
    
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        return output_path
    else:
        return json.dumps(results, indent=2)



########################################### VSEARCH results

## Customized format for VSEARCH results
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
# bits     Bit score (not computed for nucleotide alignments). Always set to 0. --> use `raw` with raw alignment scores
# qcov     Query coverage
# qstrand  Query strand orientation
# ql       Query sequence length
# tl       Target sequence length


def parse_vsearch_alignments(file_path: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Parse VSEARCH alignment output file and extract aligned sequences.
    
    Args:
        file_path: Path to the VSEARCH alignment output file (results of `--alnout`)
        
    Returns:
        Dictionary with {query_id: {target_id: {"qseq": query_seq, "sseq": subject_seq}}}
    """
    alignments = {}
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Split by query blocks
    query_blocks = content.split("Query >")
    if len(query_blocks) > 1:
        query_blocks = query_blocks[1:]  # Skip header part if exists
    
    for block in query_blocks:
        if not block.strip():
            continue
            
        # Get query ID from first line
        query_id = block.split('\n')[0].strip()
        alignments[query_id] = {}
        
        # Split into alignments
        sections = block.split("Query ")
        alignment_sections = sections[1:]
        
        # Process alignment sections
        for alignment in alignment_sections:
            lines = alignment.strip().split('\n')
            if len(lines) < 5:
                continue
                
            # Get target ID
            target_header = lines[1].strip()
            target_id = target_header.split('>')[1].strip()
            
            # Extract aligned sequences
            qseq = None
            sseq = None
            
            for i in range(2, len(lines)):
                if lines[i].startswith('Qry'):
                    qry_parts = lines[i].split('+')
                    if len(qry_parts) > 1:
                        qseq = ''.join([c for c in qry_parts[1].strip() if c.upper() in 'ACGTN-'])
                elif lines[i].startswith('Tgt'):
                    tgt_parts = lines[i].split('+')
                    if len(tgt_parts) > 1:
                        sseq = ''.join([c for c in tgt_parts[1].strip() if c.upper() in 'ACGTN-'])
            
            # Store the aligned sequences
            if qseq and sseq:
                alignments[query_id][target_id] = {
                    "qseq": qseq,
                    "sseq": sseq
                }
    
    return alignments


def normalize_strand_naming(strand: Optional[str]) -> Optional[str]:
    """
    Normalize strand notation to match BLAST format.
    
    Args:
        strand: Strand notation ('+', '-', or None)
        
    Returns:
        Normalized strand notation ('plus', 'minus', or None)
    """
    if strand == "+":
        return "plus"
    elif strand == "-":
        return "minus"
    return strand


def parse_vsearch_results(userout_file: str, alnout_file: str, query_info: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Parse VSEARCH tabular output and alignment file, combining them into a structured format
    similar to BLAST results.
    
    Args:
        userout_file: Path to the VSEARCH tabular output file (--userout + --userfields)
        alnout_file: Path to the VSEARCH alignment output file (--alnout)
        query_info: Optional dictionary mapping query IDs to their sequence lengths
        
    Returns:
        Dictionary with parsed results grouped by query ID
    """
    # Define column names for VSEARCH userout + custom userfields output
    # Columns are renamed to match BLAST output format
    columns = [
        "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
        "qstart", "qend", "sstart", "send", "evalue", "bitscore",
        "qcovs", "sstrand", "qlen", "slen"
    ]
    
    # Read aligned sequences from alignment output
    sequence_data = parse_vsearch_alignments(alnout_file)
    
    # Read the tab-delimited file
    try:
        df = pd.read_csv(userout_file, sep='\t', names=columns, header=None)
    except Exception as e:
        return {"error": f"Failed to parse VSEARCH results: {str(e)}"}
    
    # Handle empty result case
    if df.empty:
        return handle_empty_results(query_info)
    
    # Initialize result structure
    result = initialize_results_structure()
    
    # Get the set of query IDs from the results
    result_query_ids = set(df["qseqid"].unique())
    
    # Group by query ID
    query_groups = df.groupby("qseqid")
    
    for query_id, group in query_groups:
        # Convert the group to records for easier processing
        hits = []
        
        for _, row in group.iterrows():
            target_id = row["sseqid"]
            
            # Try to get aligned sequences from alignment file
            qseq = sseq = None
            if query_id in sequence_data and target_id in sequence_data[query_id]:
                qseq = sequence_data[query_id][target_id]["qseq"]
                sseq = sequence_data[query_id][target_id]["sseq"]
            
            # Parse taxonomy from sseqid if possible
            taxonomy = get_taxonomy_from_sseqid(target_id)
            
            # Format the alignment if sequences are available
            alignment = format_alignment(qseq, sseq) if qseq and sseq else None

            # Normalize strand naming
            sstrand = normalize_strand_naming(row["sstrand"] if "sstrand" in row else None)

            # Create a hit entry
            hit = {
                "sseqid": row["sseqid"],
                "taxonomy": taxonomy,
                "pident": float(row["pident"]),
                "length": int(row["length"]),
                "mismatch": int(row["mismatch"]),
                "gapopen": int(row["gapopen"]),
                "qstart": int(row["qstart"]),
                "qend": int(row["qend"]),
                "sstart": int(row["sstart"]),
                "send": int(row["send"]),
                "evalue": None,       # NB! evalue is not computed for nucleotide alignments in VSEARCH
                # "bitscore": None,   # NB! bit score is not computed for nucleotide alignments in VSEARCH
                "bitscore": int(row["bitscore"]) if not pd.isna(row["bitscore"]) else None,   # use raw alignment scores
                "qcovs": float(row["qcovs"]) if not pd.isna(row["qcovs"]) else None,
                "sstrand": sstrand,
                "slen": int(row["slen"]) if not pd.isna(row["slen"]) else None
            }
                
            if alignment:
                hit["alignment"] = alignment
                
            hits.append(hit)
        
        # Sort hits by percent identity, length, and query coverage (since bitscore is not available in VSEARCH)
        hits.sort(key=lambda x: (-x["pident"], -x["length"], -x["qcovs"], x["sseqid"]))
        
        # Get query length from the results or from the provided query_info dictionary
        query_length = int(group["qlen"].iloc[0]) if not pd.isna(group["qlen"].iloc[0]) else None
        if query_length is None and query_info and query_id in query_info:
            query_length = query_info[query_id]
            
        # Add to results
        query_result = {
            "query_id": query_id,
            "query_length": query_length,
            "hit_count": len(hits),
            "hits": hits
        }
        
        result["results"].append(query_result)
    
    # If query_info was provided, add entries for queries with no hits
    if query_info:
        result = add_missing_queries(result, result_query_ids, query_info)
        total_queries = len(query_info)
    else:
        # If no query_info provided, use the count from the results
        total_queries = len(query_groups)
    
    # Add summary information
    return finalize_results(result, total_queries, len(df))


def parse_vsearch_file_to_json(userout_file: str, alnout_file: str, output_path: Optional[str] = None, query_fasta: Optional[str] = None) -> str:
    """
    Parse VSEARCH output files and save the results as JSON.
    
    Args:
        userout_file: Path to the VSEARCH tabular output file (--userout + --userfields)
        alnout_file: Path to the VSEARCH alignment output file (--alnout)
        output_path: Optional path to save the JSON output (if None, JSON is returned as string)
        query_fasta: Optional path to the input FASTA file to extract query IDs
        
    Returns:
        JSON string or file path where JSON was saved
    """
    # Parse query information from FASTA if provided
    query_info = None
    if query_fasta:
        query_info = parse_fasta(query_fasta)
        
    results = parse_vsearch_results(userout_file, alnout_file, query_info)
    
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        return output_path
    else:
        return json.dumps(results, indent=2)

"""
Result parser module for processing and interpreting taxonomic annotation outputs from
tools like BLAST and VSEARCH to extract taxonomic information.
"""

import json
import pandas as pd
from typing import Dict, List, Any, Optional
from pathlib import Path


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


def parse_blast_results(file_path: str) -> Dict[str, Any]:
    """
    Parse BLAST output file and convert to structured JSON format.
    
    Args:
        file_path: Path to the BLAST output file
        
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
    
    if df.empty:
        return {"results": [], "summary": {"total_queries": 0, "total_hits": 0}}
    
    # Group by query ID
    result = {"results": [], "summary": {}}
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
                "qlen": int(row["qlen"]) if not pd.isna(row["qlen"]) else None,
                "slen": int(row["slen"]) if not pd.isna(row["slen"]) else None,
                "alignment": alignment
            }
            
            hits.append(hit)
        
        # Sort hits by bitscore (descending) and evalue (ascending)
        hits.sort(key=lambda x: (-x["bitscore"], x["evalue"]))
        
        # Add to results
        query_result = {
            "query_id": query_id,
            "query_length": int(group["qlen"].iloc[0]) if not pd.isna(group["qlen"].iloc[0]) else None,
            "hit_count": len(hits),
            "hits": hits
        }
        
        result["results"].append(query_result)
    
    # Add summary information
    result["summary"] = {
        "total_queries": len(query_groups),
        "total_hits": len(df)
    }
    
    return result



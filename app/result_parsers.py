"""
Result parser module for processing and interpreting taxonomic annotation outputs from
tools like BLAST and VSEARCH to extract taxonomic information.
"""

import json
import pandas as pd
from typing import Dict, List, Any, Optional
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
                "slen": int(row["slen"]) if not pd.isna(row["slen"]) else None,
                "alignment": alignment
            }
            
            hits.append(hit)
        
        # Sort hits (mainly by bitscore & evalue)
        hits.sort(key=lambda x: (-x["bitscore"], x["evalue"], -x["pident"], x["length"], -x["qcovs"], x["sseqid"]))
        
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


def parse_blast_file_to_json(file_path: str, output_path: Optional[str] = None) -> str:
    """
    Parse a BLAST output file and save the results as JSON.
    
    Args:
        file_path: Path to the BLAST output file
        output_path: Optional path to save the JSON output (if None, JSON is returned as string)
        
    Returns:
        JSON string or file path where JSON was saved
    """
    results = parse_blast_results(file_path)
    
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
# bits     Bit score (not computed for nucleotide alignments). Always set to 0.
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


def parse_vsearch_results(userout_file: str, alnout_file: str) -> Dict[str, Any]:
    """
    Parse VSEARCH tabular output and alignment file, combining them into a structured format
    similar to BLAST results.
    
    Args:
        userout_file: Path to the VSEARCH tabular output file (--userout + --userfields)
        alnout_file: Path to the VSEARCH alignment output file (--alnout)
        
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
    
    if df.empty:
        return {"results": [], "summary": {"total_queries": 0, "total_hits": 0}}
    
    # Group by query ID
    result = {"results": [], "summary": {}}
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
            taxonomy = {}
            if ';' in target_id:
                try:
                    taxonomy = parse_sseqid(target_id)
                except:
                    # If parse_sseqid is not available, create a minimal taxonomy dict
                    taxonomy = {"accession": target_id, "species": target_id}
            else:
                taxonomy = {"accession": target_id, "species": target_id}
            
            # Format the alignment if sequences are available
            alignment = None
            if qseq and sseq:
                alignment = format_alignment(qseq, sseq)

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
                # NB! evalue is not computed for nucleotide alignments in VSEARCH
                "evalue": None,
                # NB! bit score is not computed for nucleotide alignments in VSEARCH
                "bitscore": None,
                "qcovs": float(row["qcovs"]) if not pd.isna(row["qcovs"]) else None,
                "sstrand": row["sstrand"] if "sstrand" in row else None,
                "slen": int(row["slen"]) if not pd.isna(row["slen"]) else None
            }
                
            if alignment:
                hit["alignment"] = alignment
                
            hits.append(hit)
        
        # Sort hits by percent identity, length, and query coverage (since bitscore is not available in VSEARCH)
        hits.sort(key=lambda x: (-x["pident"], x["length"], -x["qcovs"], x["sseqid"]))
        
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


def parse_vsearch_file_to_json(userout_file: str, alnout_file: str, output_path: Optional[str] = None) -> str:
    """
    Parse VSEARCH output files and save the results as JSON.
    
    Args:
        userout_file: Path to the VSEARCH tabular output file (--userout + --userfields)
        alnout_file: Path to the VSEARCH alignment output file (--alnout)
        output_path: Optional path to save the JSON output (if None, JSON is returned as string)
        
    Returns:
        JSON string or file path where JSON was saved
    """
    results = parse_vsearch_results(userout_file, alnout_file)
    
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        return output_path
    else:
        return json.dumps(results, indent=2)

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
#  13. qcovhsp     Query Coverage Per HSP
#  14. sstrand     Subject Strand
#  15. slen        Subject sequence length
#  16. qlen        Query sequence length
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



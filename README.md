# Taxonomic Annotation API

A FastAPI-based server for taxonomic annotation of DNA sequences.

## Features

- Upload FASTA files containing DNA sequences
- Run taxonomic annotation using BLAST or VSEARCH
- Track job status and retrieve results
- RESTful API with auto-generated documentation
## Results Format

The `results.json` file contains taxonomic annotation results in a structured format.  
The exact content depends on the tool used (BLAST or VSEARCH), but follows this general structure:

```json
{
  "results": [
    { ... },    # matches for each query sequence
    { ... },
    ...
  ],
  "summary": {
    "total_queries": 4,
    "total_hits": 80
  },
  "metadata": {
    "tool": "blast",
    "algorithm": "megablast",
    "database": {
      "identifier": "eukaryome_its",
      "version": "1.9.4"
    },
    "job_id": "job123"
  }
}
```

For each query sequence, the results are stored in the `results` array. For example:
``` json
{
  "results": [
    {
      "query_id": "query_name",
      "query_length": 553,
      "hit_count": 2,
      "hits": [
        {
          "sseqid": "EUK1101818;Fungi;Basidiomycota;Tremellomycetes;Filobasidiales;Piskurozymaceae;Solicoccozyma;aeria",
          "taxonomy": {
            "accession": "EUK1101818",
            "kingdom": "Fungi",
            "phylum": "Basidiomycota",
            "class": "Tremellomycetes",
            "order": "Filobasidiales",
            "family": "Piskurozymaceae",
            "genus": "Solicoccozyma",
            "species": "aeria"
          },
          "pident": 100.0,
          "length": 553,
          "mismatch": 0,
          "gapopen": 0,
          "qstart": 1,
          "qend": 553,
          "sstart": 1235,
          "send": 1787,
          "evalue": 0.0,
          "bitscore": 998.0,
          "qcovs": 100.0,
          "sstrand": "plus",
          "slen": 4063,
          "alignment": {
            "qseq":    "GTGGGATTAAA...",  # truncated
            "midline": "|||  |||||...",   # truncated
            "sseq":    "GTGAATTAAA..."    # truncated
          }
        },
        { ... },  # other hits
      ]
    },
    { ... },      # other query sequences
    { ... }
  ],
  "summary":  { ... },
  "metadata": { ... }
}
```

Each hit contains the following information:

- **sseqid**: Identifier of the reference sequence
- **taxonomy**: Taxonomic classification object with fields (accession, kingdom, phylum, class, order, family, genus, species)
- **pident**: Sequence identity percentage
- **length**: Length of the alignment in nucleotides
- **mismatch**: Number of mismatched positions
- **gapopen**: Number of gap openings in the alignment
- **qcovs**: Percentage of query covered by alignment
- **evalue**: E-value (not available for VSEARCH output)
- **bitscore**: Bit score (for VSEARCH, raw score is used)
- **qstart** and **qend**: Start and end positions in query
- **sstart** and **send**: Start and end positions in subject/target
- **sstrand**: Alignment strand (e.g., "plus" or "minus")
- **slen**: Length of the subject sequence
- **alignment**: Object containing aligned sequences with fields:
  - **qseq**: Aligned portion of query sequence
  - **midline**: Match representation between sequences
  - **sseq**: Aligned portion of subject sequence




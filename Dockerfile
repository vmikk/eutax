
### --- Builder stage ---

FROM python:3.12.10-slim AS builder

## Install system dependencies
RUN apt-get update \
  && apt-get install -y less wget curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /var/cache/debconf/templates.dat* /tmp/* /var/tmp/*

## Install BLAST
RUN wget -O "blast.tar.gz" 'https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-2.16.0+-x64-linux.tar.gz' \
  && tar -xzf "blast.tar.gz" \
  && rm -f "blast.tar.gz" \
  && mv ncbi-blast-2.16.0+/bin/* /usr/local/bin/ \
  && rm -rf ncbi-blast-2.16.0+

## Install VSEARCH
RUN wget -O "vsearch.tar.gz" 'https://github.com/torognes/vsearch/releases/download/v2.30.0/vsearch-2.30.0-linux-x86_64.tar.gz' \
  && tar -xzf "vsearch.tar.gz" \
  && rm -f "vsearch.tar.gz" \
  && mv vsearch-2.30.0-linux-x86_64/bin/vsearch /usr/local/bin/ \
  && rm -rf vsearch-2.30.0-linux-x86_64

## Add lf
RUN wget https://github.com/gokcehan/lf/releases/download/r34/lf-linux-amd64.tar.gz \
  && tar -xvf lf-linux-amd64.tar.gz \
  && mv lf /usr/local/bin/ \
  && rm -f lf-linux-amd64.tar.gz

## Install Rust (needed for pydantic-core)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal \
  && echo 'source $HOME/.cargo/env' >> $HOME/.bashrc \
  && rm -rf /root/.cargo/registry /root/.cargo/git

ENV PATH="/root/.cargo/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

## Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip cache purge \
    && find /usr/local -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.12/site-packages/pip/_vendor/distlib -name "*-arm.exe" -delete
    # && find /usr/local -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    # && find /usr/local/lib/python3.12/site-packages -name "*.pyc" -delete


### --- Runtime stage ---

FROM python:3.12.10-slim AS runtime

RUN apt-get update \
  && apt-get install -y less wget curl libgomp1 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /var/cache/debconf/templates.dat* /tmp/* /var/tmp/*

## Set working directory
WORKDIR /app

## Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

## Copy application code
COPY app/ /app/app/
COPY run.py /app/

## Create non-root user and set permissions
RUN groupadd -r fastapi && useradd -r -g fastapi fastapi \
    && mkdir -p wd/uploads wd/outputs \
    && chown -R fastapi:fastapi /app \
    && chmod -R 755 /app

## Set environment variables
ENV PYTHONUNBUFFERED=1 \
    UPLOAD_DIR=/app/wd/uploads \
    OUTPUT_DIR=/app/wd/outputs \
    MAX_CPUS=8 \
    MAX_CONCURRENT_JOBS=2 \
    DISABLE_DOCS=false

## Note about API_KEY:
## The `API_KEY` variable should be provided at runtime rather than hardcoded here
## If not set, authentication is skipped (for "protected" endpoints)
## E.g., docker run -e API_KEY=your_secret_key ...

## Note about DISABLE_DOCS:
## If set to true, the API documentation (Swagger UI, ReDoc, and OpenAPI JSON schema) is disabled

## It's possible to set a custom REFDB_CONFIG_PATH at runtime
## REFDB_CONFIG_PATH=/app/app/config/refdb.yaml


## Switch to non-root user
USER fastapi

## Healthcheck to verify the API is up
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD curl --fail http://localhost:8000/api/v1/health || exit 1

## Expose port
EXPOSE 8000

## Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

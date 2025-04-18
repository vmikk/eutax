FROM python:3.12.10

# Install system dependencies, along with BLAST and VSEARCH
RUN apt-get update \
  && apt-get install -y less \
  && wget -O "blast.tar.gz" 'https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-2.16.0+-x64-linux.tar.gz' \
  && tar -xzf "blast.tar.gz" \
  && rm -f "blast.tar.gz" \
  && mv ncbi-blast-2.16.0+/bin/* /usr/bin/ \
  && rm -rf ncbi-blast-2.16.0+ \
  && wget -O "vsearch.tar.gz" 'https://github.com/torognes/vsearch/releases/download/v2.30.0/vsearch-2.30.0-linux-x86_64.tar.gz' \
  && tar -xzf "vsearch.tar.gz" \
  && rm -f "vsearch.tar.gz" \
  && mv vsearch-2.30.0-linux-x86_64/bin/vsearch /usr/bin/ \
  && rm -rf vsearch-2.30.0-linux-x86_64 \
  && curl https://sh.rustup.rs -sSf | sh -s -- -y \
  && echo 'source $HOME/.cargo/env' >> $HOME/.bashrc \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /app/app/
COPY run.py /app/

# Create directories for uploads and outputs
RUN mkdir -p uploads outputs

# Set environment variables
ENV UPLOAD_DIR=/app/uploads
ENV OUTPUT_DIR=/app/outputs
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

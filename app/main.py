from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import uploads, jobs

# Create FastAPI app
app = FastAPI(
    title="EUTAX",
    description="API for taxonomic annotation of DNA sequences",
    version="0.0.1",
    docs_url="/docs",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(uploads.router, prefix="/api/v1", tags=["Uploads"])
app.include_router(jobs.router, prefix="/api/v1", tags=["Jobs"])

@app.get("/", tags=["Root"])
async def root():
    return {"message": "Welcome to the EUTAX. Visit /docs for API documentation."} 

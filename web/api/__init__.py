"""FastAPI backend for Cuttle Web UI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.api.routes import games

app = FastAPI(
    title="Cuttle Game API",
    description="API for playing Cuttle card game with various AI strategies",
    version="0.1.0",
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(games.router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

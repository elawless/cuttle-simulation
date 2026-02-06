"""FastAPI backend for Cuttle Web UI."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.api.routes import games

logger = logging.getLogger(__name__)


def init_database():
    """Initialize the database and inject into session manager."""
    try:
        from db import Database, PlayerRepository, GameRepository
        from core.elo_manager import EloManager
        from web.api.session_manager import session_manager

        # Skip if already initialized
        if session_manager._db is not None:
            logger.info("Database already initialized")
            return

        db = Database("cuttle_tournament.db")
        logger.info(f"Database initialized: cuttle_tournament.db")

        # Update session manager with database
        session_manager._db = db
        session_manager._elo_manager = EloManager(db)
        session_manager._player_repo = PlayerRepository(db)
        session_manager._game_repo = GameRepository(db)
        print(f"Session manager ID: {id(session_manager)}")
        print(f"Session manager _db: {session_manager._db}")
        logger.info(f"Session manager configured with ELO tracking")
        logger.info(f"  _db: {session_manager._db}")
        logger.info(f"  _elo_manager: {session_manager._elo_manager}")
        logger.info(f"  _player_repo: {session_manager._player_repo}")

    except ImportError as e:
        logger.warning(f"Database modules not available: {e}")
        logger.warning("Running without ELO tracking and game persistence")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        logger.warning("Running without ELO tracking and game persistence")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize DB on startup."""
    print("=" * 60)
    print("LIFESPAN STARTUP - Initializing database...")
    print("=" * 60)
    init_database()
    print("=" * 60)
    print("LIFESPAN STARTUP COMPLETE")
    print("=" * 60)
    yield
    print("LIFESPAN SHUTDOWN")


app = FastAPI(
    title="Cuttle Game API",
    description="API for playing Cuttle card game with various AI strategies",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for frontend
cors_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

# Add production frontend URL if set
prod_url = os.environ.get("FRONTEND_URL")
if prod_url:
    cors_origins.append(prod_url)

print(f"CORS origins configured: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
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

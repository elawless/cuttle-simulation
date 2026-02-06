-- Cuttle Tournament Database Schema
-- SQLite database for persistent game logging, ELO ratings, and cost tracking

-- Player/Model identities
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,              -- hash(provider:model:params)
    provider TEXT NOT NULL,           -- 'anthropic', 'openrouter', 'ollama', 'mcts', 'heuristic'
    model_name TEXT NOT NULL,
    params_json TEXT DEFAULT '{}',
    display_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ELO ratings with history
-- Note: player_id is a soft reference to allow ratings without full player records
CREATE TABLE IF NOT EXISTS elo_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    rating REAL DEFAULT 1500.0,
    rating_pool TEXT DEFAULT 'all',   -- 'all', 'llm-only', 'mcts-only'
    games_played INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient rating lookups
CREATE INDEX IF NOT EXISTS idx_elo_player_pool ON elo_ratings(player_id, rating_pool);
CREATE INDEX IF NOT EXISTS idx_elo_timestamp ON elo_ratings(timestamp DESC);

-- Game results with point tracking
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    player0_id TEXT NOT NULL REFERENCES players(id),
    player1_id TEXT NOT NULL REFERENCES players(id),
    winner INTEGER,                   -- 0, 1, NULL (draw)
    win_reason TEXT,
    score_p0 INTEGER NOT NULL,
    score_p1 INTEGER NOT NULL,
    turns INTEGER,
    move_count INTEGER,
    duration_ms REAL,
    seed INTEGER,
    tournament_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for game queries
CREATE INDEX IF NOT EXISTS idx_games_tournament ON games(tournament_id);
CREATE INDEX IF NOT EXISTS idx_games_player0 ON games(player0_id);
CREATE INDEX IF NOT EXISTS idx_games_player1 ON games(player1_id);
CREATE INDEX IF NOT EXISTS idx_games_created ON games(created_at DESC);

-- Move-level logging
CREATE TABLE IF NOT EXISTS game_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES games(id),
    move_number INTEGER NOT NULL,
    turn INTEGER,
    player INTEGER,
    phase TEXT,
    move_description TEXT,
    state_json TEXT,                  -- compressed state
    mcts_stats_json TEXT,             -- NULL for non-MCTS
    llm_thinking_json TEXT,           -- NULL for non-LLM
    UNIQUE(game_id, move_number)
);

-- Index for move retrieval
CREATE INDEX IF NOT EXISTS idx_moves_game ON game_moves(game_id, move_number);

-- API cost tracking
CREATE TABLE IF NOT EXISTS api_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT REFERENCES players(id),
    game_id TEXT,
    tournament_id TEXT,
    provider TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for cost queries
CREATE INDEX IF NOT EXISTS idx_costs_tournament ON api_costs(tournament_id);
CREATE INDEX IF NOT EXISTS idx_costs_player ON api_costs(player_id);
CREATE INDEX IF NOT EXISTS idx_costs_timestamp ON api_costs(timestamp DESC);

-- Tournaments
CREATE TABLE IF NOT EXISTS tournaments (
    id TEXT PRIMARY KEY,
    name TEXT,
    config_json TEXT,
    status TEXT DEFAULT 'pending',    -- pending, running, completed, cancelled
    budget_usd REAL,
    spent_usd REAL DEFAULT 0.0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for tournament status queries
CREATE INDEX IF NOT EXISTS idx_tournaments_status ON tournaments(status);

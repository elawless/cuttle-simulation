# Cuttle Simulation

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen.svg)](https://cuttle-simulation.vercel.app)

A Python simulation of the card game [Cuttle](https://www.cuttle.cards/), featuring multiple AI strategies including Monte Carlo Tree Search (MCTS) that achieves a **94.9% win rate** against heuristic opponents.

**[Live Demo](https://cuttle-simulation.vercel.app)** | **[Play Cuttle Online](https://www.cuttle.cards/)**

---

## What is Cuttle?

Cuttle is a two-player combat card game played with a standard 52-card deck. Players race to accumulate 21 points by playing cards for their point value, while using face cards and one-off effects to disrupt their opponent. It's a game of tempo, card advantage, and knowing when to push for points versus when to control the board.

Learn the rules at [cuttle.cards/rules](https://www.cuttle.cards/rules).

## What is This Project?

This is an AI playground and simulation framework for Cuttle, built entirely through collaborative "vibe coding" with [Claude](https://claude.ai). The project explores optimal Cuttle strategy through:

- **Monte Carlo Tree Search (MCTS)** - Tree search with heuristic-guided rollouts
- **Information Set MCTS (ISMCTS)** - Handles hidden information (opponent's hand)
- **LLM Strategies** - Play against Claude, GPT-4, or local models via Ollama
- **Heuristic Analysis** - Data-driven strategy insights from thousands of simulated games

The MCTS implementation discovered several non-obvious strategic insights, like "8s should almost always be played for points (99.3%), not as the Glasses permanent."

## Features

- **Complete Cuttle Engine** - Full implementation of all Cuttle rules including counters, one-offs, Jacks, Queens, and the Seven card
- **Multiple AI Strategies**
  - Random (baseline)
  - Heuristic (rule-based, 83% vs Random)
  - MCTS (94.9% vs Heuristic)
  - ISMCTS (handles hidden information)
  - LLM (Claude, OpenAI, OpenRouter, Ollama)
- **Web UI** - Real-time gameplay with WebSocket updates
- **AI vs AI Mode** - Watch strategies compete with playback controls
- **ELO Rating System** - Tournament infrastructure with leaderboard
- **Training Data Collection** - Parallel game runner for ML training data
- **103 Passing Tests** - Comprehensive test coverage of game rules

## Live Demo

- **Web UI**: [cuttle-simulation.vercel.app](https://cuttle-simulation.vercel.app)
- **API**: [web-production-41c73.up.railway.app](https://web-production-41c73.up.railway.app)

Play against AI strategies or watch AI vs AI matches in real-time.

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cuttle-simulation.git
cd cuttle-simulation

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with all dependencies
pip install -e ".[dev,api]"
```

### Play via CLI

```bash
# Play against AI
cuttle play

# Watch AI vs AI
cuttle watch

# Run a tournament
cuttle tournament --games 100
```

### Run the Web UI

```bash
# Copy environment file and add your API keys (for LLM strategies)
cp .env.example .env

# Start the backend
python run_server.py

# In another terminal, start the frontend
cd web/frontend && npm install && npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) to play.

### Run Tests

```bash
pytest tests/ -v
```

## AI Strategies

| Strategy | Description | Win Rate vs Random |
|----------|-------------|-------------------|
| **Random** | Selects uniformly from legal moves | 50% (baseline) |
| **Heuristic** | Rule-based with learned weights | 83% |
| **MCTS** | Monte Carlo Tree Search with 1000 iterations | 99%+ |
| **ISMCTS** | Information Set MCTS for imperfect information | ~95% |
| **LLM** | Claude/GPT-4/Ollama with game state prompts | Varies by model |

### MCTS Configuration

```python
from strategies.mcts import MCTSStrategy

# Default: 1000 iterations, exploration constant 1.414
mcts = MCTSStrategy(iterations=1000)

# Parallel MCTS with 4 workers
mcts_parallel = MCTSStrategy(iterations=1000, num_workers=4)
```

### LLM Configuration

```python
from strategies.llm_strategy import LLMStrategy

# Claude (requires ANTHROPIC_API_KEY)
claude = LLMStrategy(model="haiku")  # or "sonnet", "opus"

# OpenRouter (requires OPENROUTER_API_KEY)
openrouter = LLMStrategy(provider="openrouter", model="anthropic/claude-3-haiku")

# Local Ollama
ollama = LLMStrategy(provider="ollama", model="llama3")
```

## Strategic Insights from MCTS

Analysis of 1000+ MCTS games revealed optimal play patterns:

- **8s for points**: 99.3% of 8s should be played for points, not as Glasses
- **Scuttle sparingly**: Only 10% usage when available; better to race for points
- **Ace is a comeback tool**: 94% of Ace plays are when behind 8+ points
- **Queens are traps**: 45% win rate - protection is less valuable than offense
- **Jack Steal is premium**: 79.5% win rate, especially when behind

See `CLAUDE.md` for the complete strategy guide derived from MCTS analysis.

## Project Structure

```
cuttle-simulation/
├── cuttle_engine/     # Core game logic (immutable states, moves, execution)
├── strategies/        # AI strategies (Random, Heuristic, MCTS, LLM)
├── simulation/        # Game runner and tournament infrastructure
├── training/          # Parallel training data collection
├── web/
│   ├── api/          # FastAPI backend with WebSocket
│   └── frontend/     # SvelteKit frontend
├── tests/            # 103 tests covering engine behavior
└── scripts/          # Analysis and debugging tools
```

## Related Projects

- **[cuttle.cards](https://www.cuttle.cards/)** - Play Cuttle online against humans
- **[cuttle-cards/cuttle](https://github.com/cuttle-cards/cuttle)** - The official Cuttle game repository
- **[Cuttle Rules](https://www.cuttle.cards/rules)** - Official game rules

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`pytest tests/ -v`)
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This entire project was built collaboratively with [Claude](https://claude.ai) using [Claude Code](https://docs.anthropic.com/en/docs/claude-code). The MCTS implementation, strategic analysis, web UI, and documentation were all developed through iterative AI-assisted programming.

Special thanks to the team at [cuttle.cards](https://www.cuttle.cards/) for creating and maintaining the definitive online Cuttle experience.

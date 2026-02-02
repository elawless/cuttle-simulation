# Cuttle Simulation

A card game simulator for Cuttle, designed to identify optimal strategies through simulation, MCTS, and LLM vs LLM matches.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### Play against AI
```bash
cuttle play
```

### Watch AI vs AI
```bash
cuttle watch
```

### Run tournament
```bash
cuttle tournament --games 100
```

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=cuttle_engine --cov-report=term-missing
```

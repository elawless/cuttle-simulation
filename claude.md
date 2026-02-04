# Cuttle Simulation - Development Notes

## Project Overview

A Python simulation of the card game Cuttle, with multiple AI strategies including Random, Heuristic, and Monte Carlo Tree Search (MCTS).

## Architecture

- `cuttle_engine/` - Core game logic (immutable states, move generation, execution)
- `strategies/` - AI strategies (RandomStrategy, HeuristicStrategy, MCTSStrategy, LLMStrategy)
- `simulation/` - Game runner and tournament infrastructure
- `web/` - Web UI (FastAPI backend + SvelteKit frontend)
- `tests/` - 103 passing tests covering engine behavior

## Known Edge Cases & Gotchas

### Move Generator / Executor

1. **Queen Protection**: Queens protect the owner from targeted one-offs (Two, Nine) and Jacks. The move generator must check `queens_count > 0` before generating targeted moves against protected players.

2. **Jack Target Validation**: Jacks can only target point cards on opponent's field. Moves generated must verify the target still exists when executed (state may have changed).

3. **Seven Resolution**: When a Seven resolves, the revealed card(s) must be played. If no valid play exists from revealed cards, this is a rules edge case - verify move generator handles it.

4. **Counter Phase Transitions**: The `waiting_for_player` in `CounterState` alternates based on counter chain length. Ensure moves during COUNTER phase are attributed to the correct player.

5. **Empty Deck Win Conditions**: When deck empties, game can end multiple ways:
   - Higher points wins immediately
   - Player with empty hand loses
   - Careful with turn order and win checking

### IllegalMoveError During Execution

**Symptom**: `IllegalMoveError: Target not found`
**Cause**: Move generator produced moves that are invalid by execution time.
**Common scenarios**:
- Stale state reference (state changed between generation and execution)
- Target card removed by another effect
- Queen protection changed mid-resolution

**Prevention**: Always generate moves fresh from current state. Add try/except around move execution in simulations.

## MCTS Implementation Pitfalls

### Error 1: UCB1 Math Domain Error

```
ValueError: math domain error
File: strategies/mcts.py, line 73
Code: math.log(self.parent.visits) / self.visits
```

**Cause**: `parent.visits` was 0 when computing UCB1 formula.
**Fix**: Added guard in `ucb1()`:
```python
if self.parent is None or self.parent.visits == 0:
    return float("inf")
```

### Error 2: Empty Children in best_child

```
ValueError: max() iterable argument is empty
File: strategies/mcts.py, line 89
Code: return max(self.children.values(), ...)
```

**Cause**: `best_child` called when no children existed (after expansion failed for all moves).
**Fix**: Added `and node.children` check to selection loop:
```python
while not node.is_terminal and node.is_fully_expanded and node.children:
    node = node.best_child(self._exploration)
```

### Error 3: IllegalMoveError During Expansion/Simulation

```
IllegalMoveError: Target not found
File: cuttle_engine/executor.py, line 680
```

**Cause**: Move generator edge cases (Queen protection, stale targets).
**Fix**: Wrapped expansion and simulation in try/except:
```python
try:
    new_state = execute_move(node.state, move)
except Exception:
    node.untried_moves.remove(move)  # Skip invalid move
```

### Critical: Backpropagation Perspective

**The most subtle bug**: MCTS backpropagation must flip the result at each tree level because:
- Wins are from the perspective of `player_just_moved`
- Each node's parent made the *opposite* player's move
- If you don't flip, MCTS will prefer moves that help the opponent!

**Important nuance**: Some phases give the same player multiple consecutive actions
(e.g., `RESOLVE_SEVEN`, `DISCARD_FOUR`). In those cases, *do not* flip the
result between parent/child when `player_just_moved` is the same. Only flip
when the acting player actually changes.

**Correct pattern**:
```python
while node is not None:
    if node.player_just_moved is not None:
        node.update(result)
        # Flip only if acting player changes between parent/child
        result = 1.0 - result
    node = node.parent
```

In code, this is now handled by a `_backpropagate(...)` helper that only flips
when `parent.player_just_moved != node.player_just_moved`.

### Error 4: MCTS ~50% Win Rate (Should Be >70%)

**Symptom**: MCTS performs no better than random (~50% win rate vs Random)
**Root causes**:
1. Pure random rollouts give weak signal in high-variance games
2. Random move expansion wastes iterations on bad moves first

**Fixes applied**:
1. **EpsilonGreedyStrategy** for rollouts (80% heuristic, 20% random):
```python
class EpsilonGreedyStrategy(Strategy):
    def select_move(self, state, legal_moves):
        if self._rng.random() < self._epsilon:
            return self._random.select_move(state, legal_moves)
        return self._heuristic.select_move(state, legal_moves)
```

2. **Move ordering heuristic** - sort untried moves by heuristic score:
```python
def __post_init__(self):
    moves = generate_legal_moves(self.state)
    heuristic = HeuristicStrategy()
    scored = [(heuristic._score_move(self.state, m), -i, m) for i, m in enumerate(moves)]
    scored.sort(reverse=True)  # Best moves first
    self.untried_moves = [m for _, _, m in scored]
```

3. **Pick best untried move** instead of random during expansion:
```python
move = node.untried_moves[0]  # Already sorted by heuristic score
```

**Result**: Win rate improved from ~50% to ~78% vs Random.

### Error 5: Root Visits Never Incremented

**Symptom**: After full expansion, selection keeps choosing the same child
because UCB1 still returns `inf` for children whose parent (root) has `visits = 0`.

**Fix**: Backpropagation must increment visits for *all* nodes, including the root.
This ensures UCB1 for depth-1 children becomes finite and selection meaningfully
balances exploration/exploitation.

## Testing Guidelines

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_engine/test_executor.py

# Run with verbose output
pytest -v

# Run MCTS-specific tests
pytest tests/test_strategies/ -k mcts
```

### When Adding New Features

1. Write tests first for expected behavior
2. Test edge cases (empty deck, empty hand, Queen protection)
3. Test win conditions trigger correctly
4. For MCTS: verify win rates against Random exceed 70%

### Tournament Validation

```python
from strategies.random_strategy import RandomStrategy
from strategies.mcts import MCTSStrategy
from simulation.runner import run_batch

# MCTS(1000) should win >70% against Random
results = run_batch(MCTSStrategy(1000), RandomStrategy(), num_games=100)
mcts_wins = sum(1 for r in results if r.winner == 0)
print(f"MCTS win rate: {mcts_wins}%")
```

**Note**: MCTS uses EpsilonGreedyStrategy (80% heuristic, 20% random) for rollouts
and orders moves by heuristic score during expansion. These optimizations are
critical for good performance - pure random rollouts only achieve ~50% win rate.

## Debugging MCTS Performance

### If MCTS win rate is too low (<70% vs Random):

1. **Check backpropagation direction**: Ensure results flip at each level
2. **Verify player_just_moved tracking**: Should match who made the move to reach node
3. **Print move statistics**: High-visit moves should have reasonable win rates
4. **Check simulation outcomes**: Random simulations should be ~50% from any balanced state
5. **Verify heuristic-guided rollouts**: EpsilonGreedyStrategy should be default
6. **Verify move ordering**: untried_moves should be sorted by heuristic score (best first)

### Diagnostic script usage:

```bash
python scripts/debug_mcts.py --games 5 --iterations 500 --verbose
```

This prints each move with MCTS statistics to identify poor move selection.

## Performance Notes

- MCTS(1000) takes ~2-5 seconds per move (depends on game complexity)
- For rapid testing, use MCTS(100-200)
- RandomStrategy is very fast (~1ms per game)
- Tournament of 100 games: Random ~100ms, MCTS(500) ~5-10 minutes

## Web UI

### Running the Web UI

```bash
# Terminal 1: Start backend (loads .env automatically)
python run_server.py

# Terminal 2: Start frontend
cd web/frontend && npm run dev
```

Access at http://localhost:5173

### Architecture

- **Backend**: FastAPI with WebSocket support (`web/api/`)
- **Frontend**: SvelteKit + TypeScript (`web/frontend/`)
- **Real-time**: WebSocket for live game updates, REST fallback
- **Session management**: In-memory game sessions with AI turn automation

### LLM Strategy

The `LLMStrategy` class (`strategies/llm_strategy.py`) uses Claude models for move selection:

```python
from strategies.llm_strategy import LLMStrategy

# Available models: "haiku", "sonnet", "opus"
strategy = LLMStrategy(model="haiku", temperature=0.3)
```

**Requirements**:
- Set `ANTHROPIC_API_KEY` in `.env` file or environment
- Install anthropic package: `pip install anthropic`

**LLMThinking capture**: The strategy captures reasoning in `last_thinking` property for debugging and UI display.

### Web UI Bugs & Fixes

#### 1. ANTHROPIC_API_KEY Not Loading

**Symptom**: `Could not resolve authentication method` error in WebSocket
**Cause**: Server wasn't reading `.env` file when started via uvicorn
**Fix**: Added explicit dotenv loading in `run_server.py`:
```python
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
```

#### 2. LLM Selecting Wrong Moves (Always Drawing)

**Symptom**: LLM would analyze correctly but then just draw a card
**Cause**: `max_tokens=512` was too low, response got cut off before `MOVE: X`
**Fix**: Increased to `max_tokens=1024` and added multiple regex patterns for move parsing

#### 3. Seven Card Only Revealing 1 Card

**Symptom**: Playing a Seven only showed 1 card instead of 2
**Cause**: Code had incorrect comment "some variants reveal 2, but cuttle.cards reveals 1"
**Fix**: Changed `_resolve_seven` to reveal `min(2, len(deck))` cards (standard Cuttle rules)

#### 4. Viewer Perspective Not Applied to Game Over

**Symptom**: Win/loss message wrong when human plays as player 1
**Cause**: Game over overlay hardcoded `winner === 0` as human win
**Fix**: Use `viewer` variable: `winner === viewer ? 'You Won!' : 'AI Won'`

#### 5. Game Felt Laggy

**Symptom**: Noticeable delay between moves even for non-LLM strategies
**Cause**: 300ms delay between AI moves for "dramatic effect"
**Fix**: Reduced to 50ms; added "AI thinking" indicator for LLM strategies

#### 6. MCTS Strategy Crashes Web App

**Symptom**: "Unexpected token 'I', "Internal S"..." JSON parse error when selecting MCTS
**Cause**: Parameter name mismatch in `web/api/session_manager.py`:
```python
# WRONG - MCTSStrategy expects exploration_constant, not exploration
MCTSStrategy(iterations=..., exploration=...)
```
**Fix**: Changed to correct parameter name:
```python
MCTSStrategy(iterations=params.get("iterations", 1000), exploration_constant=params.get("exploration", 1.414))
```
Same fix applied to ISMCTSStrategy.

### WebSocket Protocol

**Server → Client messages**:
- `game_state`: Full state update with legal moves
- `move_made`: Move was executed (includes move details)
- `ai_thinking`: AI is computing (shows strategy name)
- `legal_moves`: Updated move list
- `error`: Error message

**Client → Server messages**:
- `select_move`: `{ type: "select_move", move_index: number }`

### Frontend State Management

Key Svelte stores in `gameStore.ts`:
- `gameState`: Current game state from server
- `legalMoves`: Available moves for human player
- `isHumanTurn`: Whether human can act
- `aiThinking`: Shows which AI strategy is computing
- `moveHistory`: Log of all moves with optional LLM reasoning

### Viewer Perspective Pattern

When human can be either player 0 or 1, use viewer-relative indexing:

```svelte
$: viewer = parseInt($page.url.searchParams.get('viewer') || '0', 10);
$: opponent = 1 - viewer;
$: myState = state?.players[viewer];
$: oppState = state?.players[opponent];
```

This ensures "You" and "Opponent" labels are always correct regardless of which side the human plays.

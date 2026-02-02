# Cuttle Simulation - Development Notes

## Project Overview

A Python simulation of the card game Cuttle, with multiple AI strategies including Random, Heuristic, and Monte Carlo Tree Search (MCTS).

## Architecture

- `cuttle_engine/` - Core game logic (immutable states, move generation, execution)
- `strategies/` - AI strategies (RandomStrategy, HeuristicStrategy, MCTSStrategy)
- `simulation/` - Game runner and tournament infrastructure
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

**Correct pattern**:
```python
while node is not None:
    if node.player_just_moved is not None:
        node.update(result)
        result = 1.0 - result  # Flip for parent's perspective
    node = node.parent
```

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

# MCTS(500) should win >70% against Random
results = run_batch(MCTSStrategy(500), RandomStrategy(), num_games=100)
mcts_wins = sum(1 for r in results if r.winner == 0)
print(f"MCTS win rate: {mcts_wins}%")
```

## Debugging MCTS Performance

### If MCTS win rate is too low (<70% vs Random):

1. **Check backpropagation direction**: Ensure results flip at each level
2. **Verify player_just_moved tracking**: Should match who made the move to reach node
3. **Print move statistics**: High-visit moves should have reasonable win rates
4. **Check simulation outcomes**: Random simulations should be ~50% from any balanced state

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

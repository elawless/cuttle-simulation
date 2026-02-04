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

**Bug we hit**: We were flipping on *every* tree level, even when the same
player takes consecutive actions (Seven resolution, Four discard). That
systematically mis-attributed wins/losses and blunted the signal.

**Fix**: Flip only when the acting player actually changes between parent/child.
This preserves correct perspective during multi-action phases.

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

**Bug we hit**: `root.visits` stayed at 0 because we only updated nodes with
`player_just_moved != None`. After full expansion, UCB1 for every depth-1 child
stayed `inf` (parent visits = 0), so selection collapsed to the first child in
iteration order.

**Fix**: Always increment visits on every node during backprop. Wins should still
only be attributed to nodes that correspond to an actual move.

### MCTS Bug Summary (2026-02)

**Observed symptom**: MCTS(1000) ~50% win rate vs Random, no scaling with iterations.

**Root causes**:
1. **Incorrect perspective flip** during backprop when the same player acts twice.
2. **Root visits never incremented**, leaving UCB1 scores infinite at depth 1.

**Fixes applied**:
1. Added `_backpropagate(...)` to:
   - Always increment `visits` for every node (including root).
   - Flip result only when `player_just_moved` changes between parent/child.
2. Switched both `select_move` and `select_move_with_stats` to use this helper.

**Why it mattered**:
- The flip bug injected systematic noise into win attribution.
- The root visit bug effectively disabled UCB1 selection once the root was fully expanded.

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

## Optimal Cuttle Strategy (MCTS-Learned)

Based on analysis of 1000+ MCTS games achieving 94.9% win rate, these are the
optimal play patterns for Cuttle:

### Core Philosophy

**Cuttle is a RACING game, not a control game.** Get to 21 points first.
Don't try to control the board - just outpace your opponent.

### Card Usage Guidelines

| Card | Optimal Use | Notes |
|------|-------------|-------|
| **10, 9** | Always points | Never scuttle with these (99% points) |
| **8** | Almost always points | Glasses is a trap (93% points vs 5% glasses) |
| **7** | Points or one-off | Use deck play 27% of the time |
| **6** | Usually points | 78% points, only scrap perms if they have many |
| **5** | Points | 93% points, scuttle is rarely worth it |
| **4** | Context-dependent | Points 46%, discard 52% |
| **3** | Revive or points | **Revive 49%** if high-value card in scrap |
| **2** | Points > destroy | 52% points, only destroy key permanents |
| **A** | One-off when behind | Only use when opponent has more points |
| **K** | Always play | Threshold reduction is critical |
| **Q** | Low priority | Protection < offense (only 3.2% of plays) |
| **J** | Steal high-value | Especially when behind (13% when losing big) |

### By Game Phase

**OPENING (Turns 1-3):**
- Play points aggressively (53.5% of moves)
- Draw if no good point card (14.3%)
- Kings are good early (7.7%)
- Avoid: Scuttling (0.9%), Queens (4.4%), 8 as Glasses (0.9%)

**MIDGAME (Turns 4-8):**
- Draw more (34.7%) - card advantage matters
- Points still primary (33%)
- Use Jacks to steal (6.7%)
- Avoid: Scuttling (2.8%)

**LATEGAME (Turn 9+):**
- Close out with points (35.8%)
- Keep drawing to find lethal (41.3%)
- Kings to lower threshold (7.6%)

### By Board State

**When BEHIND 8+ points:**
- Use Ace one-off to reset (11.1%)
- Jacks to steal high-value cards (13.3%)
- Still play points (27.8%)
- Avoid: Scuttling (5.2%), Queens (3.3%)

**When BEHIND 3-7 points:**
- Play points to catch up (36.5%)
- Draw for options (29.6%)
- DON'T scuttle (4.6% vs 23% for old heuristic)

**When EVEN:**
- Points (43.6%) + Draw (29.6%)
- DON'T use 8 as Glasses (0.5% vs 8.1%)

**When AHEAD:**
- Play Kings to close out (+10% when ahead 3-7)
- Keep playing points (50.3% when ahead 8+)
- Never scuttle (0.4%)

### One-Off Usage Guidelines

Based on 300-game analysis, MCTS uses one-offs very strategically:

| One-Off | When MCTS Uses It | Key Pattern |
|---------|-------------------|-------------|
| **ACE** | 94% when behind 8+ pts | ONLY use as comeback mechanic |
| **TWO** | Rarely (play for 2 pts) | Only destroy critical permanents |
| **THREE** | 36% behind 8+, 28% even | Revive high-value cards from scrap |
| **FOUR** | 81% in opening | Tempo play to disrupt opponent early |
| **FIVE** | 65% in opening | Build card advantage early |
| **SIX** | Almost never | 6 points > scrapping permanents |
| **SEVEN** | 70% in opening | Tempo - like draw + play immediately |

**ACE Strategy (Critical):**
- Use ONLY when behind 8+ points (94.3% of Ace plays)
- Never use when even or ahead (0%!)
- Mostly opening phase (83%) - reset if opponent races ahead
- Ace is a COMEBACK tool, not a control tool

**Opening One-Offs (Turns 1-3):**
- FOUR discard (35 plays) - disrupt opponent's hand
- SEVEN deck play (23 plays) - tempo advantage
- FIVE draw two (20 plays) - build hand
- ACE only if already behind

**When Behind 8+ Points:**
- ACE scrap all (50 plays) - primary comeback
- THREE revive (14 plays) - recover value
- FOUR/FIVE/SEVEN - try to catch up

**When Even:**
- FOUR discard (27 plays) - maintain pressure
- SEVEN deck play (17 plays) - tempo
- FIVE draw (16 plays) - build advantage
- NO Ace plays when even!

### Counter Decisions

**Only counter 19% of the time!** Most one-offs aren't worth spending a card.

| Threat | Counter Rate | Reasoning |
|--------|-------------|-----------|
| **Ace** | 36% | Scrap all points is devastating |
| **Five** | 50% | Don't let them draw two |
| Four | 15% | Discard hurts but keep your counter |
| Two | 14% | Losing a permanent isn't worth a card |
| Six | 0% | Let them waste it |
| Three | 0% | Who cares if they revive |
| Seven | 0% | They play from deck? Fine |

### THREE Revival Targeting (MCTS-Learned)

Analysis of 47 THREE revives across 500 games shows clear priorities:

| Card Revived | Percentage | Why |
|--------------|------------|-----|
| **Jack** | 27.7% | Steal opponent's high-value points |
| **10** | 23.4% | Maximum point value |
| **King** | 17.0% | Threshold reduction |
| **9** | 12.8% | High points |
| **8** | 8.5% | Good points |
| **7** | 6.4% | Medium points |
| **4, 5, 6** | 4.3% | Low priority |

**Never revived (0%):** 2, 3, Queen

**Priority order:** Jack > 10 > King > 9 > 8 > 7

**Why Jack is #1:** When behind, stealing a 10 from opponent is a 20-point swing.
When even/ahead, Jack recovers both point-stealing ability and board presence.

**Why Queen is never revived:** Protection doesn't win games. Points do.

### Key Strategic Insights

1. **8s for points is MASSIVE** - 92% difference vs old heuristic
2. **Never scuttle** - 1-for-1 trades don't advance win condition
3. **Threes should revive** - 49% revive rate for high-value recovery
4. **THREE targets: Jack > 10 > King** - Never revive 2, 3, or Queen
5. **Sevens as one-off** - Deck play gives tempo advantage
6. **Ignore opponent threats** - Racing beats reacting
7. **Queens are overrated** - Only 3.2% of plays

### Win Rate Results

- MCTS vs Random: **99-100%**
- MCTS vs Old Heuristic: **94.9%**
- Updated Heuristic should perform close to MCTS

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

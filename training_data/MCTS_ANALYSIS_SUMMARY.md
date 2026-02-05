# MCTS vs Heuristic Comprehensive Analysis Summary

**Data Source**: `mcts2000_vs_heuristic_1000games.json`
- 1000 games, 6139 MCTS moves analyzed
- MCTS win rate: 87.6%

## Key Findings

### Move Type Distribution

| Move Type | Rate | Win Rate | Insight |
|-----------|------|----------|---------|
| Points | 41.3% | 75.9% | Core strategy - play points aggressively |
| Draw | 14.1% | 58.1% | Often a "settle" option |
| Jack Steal | 6.9% | **79.5%** | One of the BEST plays |
| King | 6.7% | 70.2% | Solid threshold reduction |
| Decline Counter | 6.4% | 52.4% | Counter selectively (22% rate) |
| Ace One-off | 3.1% | 58.2% | Mostly opening (74%) |
| Queen | 2.9% | **45.2%** | Correlates with WEAK positions |
| Scuttle | 2.8% | **39.9%** | Almost always wrong |

### Card-Level Action Choices

When MCTS has a card with multiple uses:

| Card | Points Rate | One-off Rate | Insight |
|------|-------------|--------------|---------|
| 4 | 60.2% | 39.8% | Points > Discard |
| 5 | 65.6% | 34.4% | Points > Draw Two |
| 6 | 94.4% | 5.6% | Almost always points |
| 7 | 68.8% | 31.2% | Points > Deck Play |
| 8 | 99.3% | 0.7% | Never use as Glasses |
| A | 26.5% | 73.5% | Usually one-off (context-dependent) |

### Scuttle Analysis

- Available 1667 times, MCTS scuttled only **10.1%**
- When declining scuttle:
  - Selected move avg win rate: 79.5%
  - Best scuttle avg win rate: 60.8%
  - **+18.7% better to NOT scuttle**

### Counter Decisions

- Counter rate: 21.8%
- Counter win rate: 75.6%
- Decline win rate: 52.4%
- **Selective countering is correct**

### Three (Revive) Targets

| Target | Rate | Win Rate |
|--------|------|----------|
| 10 | 25.0% | 54.5% |
| Jack | 23.3% | 52.9% |
| King | 12.9% | 55.3% |
| 9 | 12.1% | 60.3% |
| 7 | 8.6% | 67.2% |
| Ace | 6.9% | 40.2% |

**Priority**: 10 > Jack > King > 9 > 8 > 7 (never revive 2, 3, Queen)

## Heuristic Changes Made

Based on this analysis, the following changes were made to `strategies/heuristic.py`:

### 1. FOUR One-off: REDUCED
- Opening: 450 → **350**
- Midgame: 200 → **150**
- Reason: 60% points rate, 41% win rate when one-off

### 2. FIVE One-off: REDUCED
- Opening: 400 → **300**
- Midgame: 300 → **200**
- Reason: 65.6% points rate

### 3. SEVEN One-off: REDUCED
- Opening: 450 → **350**
- Midgame: 300 → **250**
- Reason: 68.8% points rate

### 4. QUEEN: REDUCED
- Score: 150 → **100**
- Reason: 45% win rate - correlates with weak positions

### 5. JACK Steal: INCREASED
- Base: 300 → **400**
- Per target value: 20 → **25**
- Reason: 79.5% win rate - one of the best plays

### 6. DRAW: REDUCED
- Score: 300 → **250**
- Reason: 58% win rate - prefer point plays

### Unchanged (Already Correct)
- Point card scoring (aligned with MCTS)
- Scuttle scoring (MCTS confirms rarely correct)
- Six one-off scoring (94% for points)
- Counter decision thresholds (selective countering correct)
- Ace one-off (context-sensitive scoring working)
- King scoring (70% win rate appropriate)

## Validation

Updated Heuristic vs Random: **83%** win rate

## Game Stage Insights

### Opening (Turns 1-3)
- Points: 42.9% (67.9% win rate)
- Jack Steal: 7.7% (77.4% win rate)
- King: 7.3% (62.1% win rate)
- Draw: 7.3% (51.6% win rate)
- Ace one-off: 3.9% (56.8% win rate)

### Midgame (Turns 4-8)
- Points: 39.9% (87.2% win rate)
- Draw: 21.6% (61.6% win rate)
- King: 5.7% (86.1% win rate)
- Jack Steal: 5.6% (83.1% win rate)

### Lategame (Turn 9+)
- Points: 35.7% (90.7% win rate)
- Draw: 30.7% (58.9% win rate)
- Jack Steal: 7.2% (83.7% win rate)
- King: 7.2% (75.9% win rate)

## Key Strategic Takeaways

1. **Cuttle is a RACING game** - Points > Control
2. **Jack Steal is premium** - 79.5% win rate, use it!
3. **Queen is a trap** - 45% win rate, low priority
4. **8 for Glasses is WRONG** - 99.3% should be points
5. **Scuttle rarely** - 10% rate, +18.7% better to not scuttle
6. **Counter selectively** - Only 22% counter rate
7. **One-offs overrated** - MCTS prefers points 60-70% of the time for 4,5,7

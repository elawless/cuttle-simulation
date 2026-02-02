# Cuttle Simulation Analysis Findings

## Executive Summary

After analyzing 100,000+ random games, we discovered:
1. **Simple heuristics beat random play by ~79%** - strategy matters significantly
2. **MCTS at 1000 iterations only achieves ~50%** - something is broken
3. **The optimal strategy is surprisingly simple** - play high point cards, avoid one-offs

---

## Game Dynamics (from 100k games)

### Win Rate by Player Position
- **P0 (first player): 48.0%**
- **P1 (second player): 52.0%**
- Slight second-player advantage

### Tempo Matters
- First to score points wins **52.9%**
- Leading at turn 5 wins **58.6%**
- Playing a King (threshold reduction) wins **58.2%**

---

## Optimal Move Priority

### Moves BETTER Than Drawing (in order)

| Rank | Move | Win Rate | vs Draw |
|------|------|----------|---------|
| 1 | Play 10 for points | 67.9% | +18.7% |
| 2 | Play Jack (steal points) | 63.9% | +14.8% |
| 3 | Play 9 for points | 62.6% | +13.4% |
| 4 | Play 8 for points | 61.1% | +11.9% |
| 5 | Play 7 for points | 59.5% | +10.3% |
| 6 | Play King | 59.3% | +10.2% |
| 7 | Play 6 for points | 56.5% | +7.3% |
| 8 | Counter | 54.7% | +5.5% |
| 9 | Play 5 for points | 54.1% | +4.9% |
| 10 | Play 4 for points | 52.8% | +3.7% |
| 11 | 7 one-off (play from deck) | 50.8% | +1.6% |
| 12 | Play 3 for points | 49.4% | +0.2% |

### Moves WORSE Than Drawing (avoid!)

| Move | Win Rate | vs Draw |
|------|----------|---------|
| 5 one-off (draw 2) | 48.5% | -0.6% |
| Play 2 for points | 48.1% | -1.0% |
| Play Ace for points | 47.9% | -1.2% |
| Scuttle | 47.5% | -1.7% |
| Play Queen | 42.6% | -6.5% |
| Play 8 as Glasses | 41.8% | -7.4% |

---

## One-Off Analysis

### Almost All One-Offs Are Bad

| One-Off | Context | Win Rate |
|---------|---------|----------|
| TWO (destroy permanent) | no royal target | 5.7% |
| TWO (destroy permanent) | has royal target | 15.6% |
| SIX (scrap all permanents) | unfavorable | 14.7% |
| SIX (scrap all permanents) | favorable | 26.2% |
| NINE (return permanent) | any | 19-21% |
| ACE (scrap all points) | behind big | 24.0% |
| ACE (scrap all points) | ahead | 19.5% |
| **SEVEN (play from deck)** | any | **50.8%** |
| FIVE (draw 2) | any | 48-49% |

**Only SEVEN one-off is genuinely useful** (50.8% > draw's 49.2%)

### Why One-Offs Fail
- Using high-value cards (8, 9) as one-offs wastes their point value
- The tactical effect rarely compensates for the card loss
- Exception: SEVEN gives card advantage (play from deck, keep your card)

---

## Ace Impact on Strategy

| Situation | Win Rate When Playing High Points |
|-----------|-----------------------------------|
| 4 unknown aces (max threat) | 63.5% |
| 3 unknown aces | 61.5% |
| 2 unknown aces | 63.6% |
| 1 unknown ace | 66.1% |
| All aces accounted for | 69.1% |

**Conclusion**: Ace threat costs ~5-6 percentage points, but playing high points is STILL good even with maximum ace threat.

---

## Scuttling Analysis

| Scuttle Type | Win Rate |
|--------------|----------|
| Favorable (destroy higher) | N/A (rare) |
| Even trade | 47.8% |
| Unfavorable | 47.4% |

**Conclusion**: Scuttling is almost always bad. Trading cards hurts you.

---

## The Simple Optimal Strategy

```
1. Play Jacks to steal opponent's points
2. Play point cards 3+ (higher value = higher priority)
3. Play Kings to reduce win threshold
4. Counter opponent's one-offs
5. Use 7 one-off if no better option
6. Draw if you only have 2s, Aces, Queens, or 8s

NEVER: Play Queens, play 8 as Glasses, Scuttle, use most one-offs
```

---

## MCTS Investigation

### The Problem
- **Heuristic vs Random: 78.6% win rate**
- **MCTS(1000) vs Random: ~50% win rate**
- MCTS does NOT scale with iterations (100, 500, 1000 all ~50%)

### What We Verified Works
- Simulations produce correct game outcomes
- Backpropagation logic appears correct in manual traces
- UCB1 correctly prefers high win-rate nodes
- Games are being played correctly

### Suspected Issues
1. **Perspective bug** - wins may be attributed incorrectly somewhere
2. **Signal too weak** - random rollouts may not discriminate well between moves
3. **Root node handling** - root has `player_just_moved=None`, children perspective may be wrong

### Key Diagnostic
The 100k analysis shows a **26 percentage point spread** between best (PlayPoints_TEN at 68%) and worst (PlayPermanent_EIGHT at 42%) moves. MCTS should easily learn this pattern, but it doesn't.

### Next Steps
1. Test if MCTS can find obvious winning moves (immediate wins)
2. Try MCTS with heuristic rollouts instead of random
3. Deep trace of perspective through entire search tree
4. Consider that for high-variance games, MCTS with random rollouts may fundamentally struggle

---

## Analysis Scripts Created

| Script | Purpose |
|--------|---------|
| `scripts/brute_10k.py` | Run 10k games, save detailed logs |
| `scripts/brute_random_analysis.py` | Pattern analysis from random games |
| `scripts/deep_analysis_100k.py` | Comprehensive 100k game analysis |
| `scripts/analyze_hand_context.py` | Correlate moves with hand quality |
| `scripts/test_threshold_strategy.py` | Find optimal point threshold |
| `scripts/view_game.py` | View specific games by seed |
| `scripts/trace_mcts.py` | Trace MCTS iterations |
| `scripts/trace_mcts_deep.py` | Deep MCTS perspective debugging |

---

## Output Files

| File | Contents |
|------|----------|
| `analysis_output/all_games.json` | All 10k game logs (JSON) |
| `analysis_output/games_first_100.txt` | First 100 games (readable) |
| `analysis_output/games_random_100.txt` | Random sample (readable) |
| `analysis_output/analysis_summary.txt` | 10k statistics |
| `analysis_output/deep_analysis_100k.json` | Full 100k analysis data |

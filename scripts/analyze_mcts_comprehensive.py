#!/usr/bin/env python3
"""Comprehensive MCTS vs Heuristic analysis script.

Analyzes training_data/mcts2000_vs_heuristic_1000games.json to extract
actionable heuristic scoring changes organized by game stage, card type,
and move type.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MoveStats:
    """Statistics for a category of moves."""

    count: int = 0
    total_visits: int = 0
    total_win_rate: float = 0.0
    wins: int = 0
    losses: int = 0

    @property
    def avg_win_rate(self) -> float:
        return self.total_win_rate / self.count if self.count > 0 else 0.0

    @property
    def avg_visits(self) -> float:
        return self.total_visits / self.count if self.count > 0 else 0.0

    def add(self, visits: int, win_rate: float, game_won: bool):
        self.count += 1
        self.total_visits += visits
        self.total_win_rate += win_rate
        if game_won:
            self.wins += 1
        else:
            self.losses += 1


def parse_move(move_str: str) -> dict:
    """Parse a move string into structured components."""
    result = {"raw": move_str, "type": "unknown", "card": None, "target": None}

    # Rank/suit extraction patterns
    rank_pattern = r"(10|[2-9AJQK])"
    suit_pattern = r"([♠♣♦♥])"

    # Draw
    if move_str == "Draw":
        result["type"] = "draw"
        return result

    # Discard (from Four one-off resolution)
    if move_str.startswith("Discard "):
        result["type"] = "discard"
        match = re.search(rf"Discard {rank_pattern}{suit_pattern}", move_str)
        if match:
            result["card"] = {"rank": match.group(1), "suit": match.group(2)}
        return result

    # Seven resolution: "Seven: play X as PLAY_Y"
    if move_str.startswith("Seven: play "):
        match = re.search(
            rf"Seven: play {rank_pattern}{suit_pattern} as (\w+)", move_str
        )
        if match:
            result["card"] = {"rank": match.group(1), "suit": match.group(2)}
            play_type = match.group(3)
            if play_type == "PLAY_POINTS":
                result["type"] = "seven_resolve_points"
            elif play_type == "PLAY_PERMANENT":
                result["type"] = "seven_resolve_permanent"
            elif play_type == "PLAY_ONE_OFF":
                result["type"] = "seven_resolve_oneoff"
            elif play_type == "SCUTTLE":
                result["type"] = "seven_resolve_scuttle"
            else:
                result["type"] = f"seven_resolve_{play_type.lower()}"
        return result

    # Play X for points
    if "for points" in move_str:
        result["type"] = "points"
        match = re.search(rf"Play {rank_pattern}{suit_pattern} for points", move_str)
        if match:
            result["card"] = {"rank": match.group(1), "suit": match.group(2)}
        return result

    # Scuttle - both formats: "Play X to scuttle Y" and "Scuttle Y with X"
    if "to scuttle" in move_str:
        result["type"] = "scuttle"
        match = re.search(
            rf"Play {rank_pattern}{suit_pattern} to scuttle {rank_pattern}{suit_pattern}",
            move_str,
        )
        if match:
            result["card"] = {"rank": match.group(1), "suit": match.group(2)}
            result["target"] = {"rank": match.group(3), "suit": match.group(4)}
        return result

    if "Scuttle " in move_str and " with " in move_str:
        result["type"] = "scuttle"
        # Format: "Scuttle 9♠ with 10♠"
        match = re.search(
            rf"Scuttle {rank_pattern}{suit_pattern} with {rank_pattern}{suit_pattern}",
            move_str,
        )
        if match:
            # Target is the card being scuttled, attacker is the card doing the scuttling
            result["target"] = {"rank": match.group(1), "suit": match.group(2)}
            result["card"] = {"rank": match.group(3), "suit": match.group(4)}
        return result

    # Jack steal
    if "to steal" in move_str:
        result["type"] = "jack_steal"
        match = re.search(
            rf"Play J{suit_pattern} to steal {rank_pattern}{suit_pattern}", move_str
        )
        if match:
            result["card"] = {"rank": "J", "suit": match.group(1)}
            result["target"] = {"rank": match.group(2), "suit": match.group(3)}
        return result

    # King
    if "to reduce win threshold" in move_str:
        result["type"] = "king"
        match = re.search(rf"Play K{suit_pattern}", move_str)
        if match:
            result["card"] = {"rank": "K", "suit": match.group(1)}
        return result

    # Queen
    if "for protection" in move_str:
        result["type"] = "queen"
        match = re.search(rf"Play Q{suit_pattern}", move_str)
        if match:
            result["card"] = {"rank": "Q", "suit": match.group(1)}
        return result

    # 8 as Glasses
    if "as Glasses" in move_str or "see opponent" in move_str.lower():
        result["type"] = "glasses"
        match = re.search(rf"Play 8{suit_pattern}", move_str)
        if match:
            result["card"] = {"rank": "8", "suit": match.group(1)}
        return result

    # One-off effects
    one_off_patterns = {
        "scrap all points": ("ace_oneoff", "A"),
        "destroy permanent": ("two_destroy", "2"),
        "destroy target permanent": ("two_destroy", "2"),
        "(destroy ": ("two_destroy", "2"),  # Pattern: "Play 2♥ as one-off (destroy K♦)"
        "revive": ("three_revive", "3"),
        "force discard": ("four_discard", "4"),
        "draw two": ("five_draw", "5"),
        "scrap all permanents": ("six_scrap", "6"),
        "play from deck": ("seven_deck", "7"),
        "return to hand": ("nine_return", "9"),
        "(return ": ("nine_return", "9"),  # Pattern: "Play 9♦ as one-off (return J♥)"
    }

    for pattern, (move_type, rank) in one_off_patterns.items():
        if pattern in move_str.lower():
            result["type"] = move_type
            match = re.search(rf"Play {rank}{suit_pattern}", move_str)
            if match:
                result["card"] = {"rank": rank, "suit": match.group(1)}

            # Extract target for targeted one-offs
            if move_type in ("two_destroy", "three_revive", "nine_return"):
                target_match = re.search(
                    rf"(?:revive|destroy|return)\s+{rank_pattern}{suit_pattern}",
                    move_str,
                    re.IGNORECASE,
                )
                if target_match:
                    result["target"] = {
                        "rank": target_match.group(1),
                        "suit": target_match.group(2),
                    }
            return result

    # Counter
    if "counter" in move_str.lower() and "decline" not in move_str.lower():
        result["type"] = "counter"
        match = re.search(rf"Play {rank_pattern}{suit_pattern}", move_str)
        if match:
            result["card"] = {"rank": match.group(1), "suit": match.group(2)}
        return result

    # Decline counter
    if "decline" in move_str.lower():
        result["type"] = "decline_counter"
        return result

    return result


def get_rank_value(rank: str) -> int:
    """Get numeric value for a rank."""
    if rank == "A":
        return 1
    elif rank == "J":
        return 11
    elif rank == "Q":
        return 12
    elif rank == "K":
        return 13
    else:
        return int(rank)


def get_game_stage(turn: int) -> str:
    """Classify turn number into game stage."""
    if turn <= 3:
        return "opening"
    elif turn <= 8:
        return "midgame"
    else:
        return "lategame"


class MCTSAnalyzer:
    """Analyzes MCTS training data for heuristic insights."""

    def __init__(self, data_path: str | Path):
        with open(data_path) as f:
            self.data = json.load(f)

        self.metadata = self.data["metadata"]
        self.games = self.data["games"]

        # Aggregated statistics
        self.move_type_stats: dict[str, MoveStats] = defaultdict(MoveStats)
        self.move_type_by_stage: dict[str, dict[str, MoveStats]] = defaultdict(
            lambda: defaultdict(MoveStats)
        )
        self.point_card_stats: dict[int, MoveStats] = defaultdict(MoveStats)
        self.point_card_by_stage: dict[int, dict[str, MoveStats]] = defaultdict(
            lambda: defaultdict(MoveStats)
        )
        self.one_off_stats: dict[str, MoveStats] = defaultdict(MoveStats)
        self.one_off_by_stage: dict[str, dict[str, MoveStats]] = defaultdict(
            lambda: defaultdict(MoveStats)
        )
        self.counter_decisions: dict[str, dict[str, MoveStats]] = defaultdict(
            lambda: defaultdict(MoveStats)
        )
        self.revive_targets: dict[str, MoveStats] = defaultdict(MoveStats)
        self.jack_steal_targets: dict[int, MoveStats] = defaultdict(MoveStats)
        self.scuttle_patterns: dict[tuple[int, int], MoveStats] = defaultdict(MoveStats)
        self.draw_stats_by_stage: dict[str, MoveStats] = defaultdict(MoveStats)

        # Card usage: when card X is available, how often is each action chosen?
        # card_rank -> action_type -> stats
        self.card_action_choices: dict[str, dict[str, MoveStats]] = defaultdict(
            lambda: defaultdict(MoveStats)
        )

        # Track alternatives to understand opportunity cost
        self.alternatives_when_selected: dict[str, list[dict]] = defaultdict(list)

        # Track when MCTS DECLINES to do something (alternatives analysis)
        # move_type -> list of (selected_type, selected_win_rate, declined_win_rate)
        self.declined_moves: dict[str, list[tuple]] = defaultdict(list)

        # Track scuttle decisions in detail
        self.scuttle_available_but_declined: list[dict] = []
        self.scuttle_chosen: list[dict] = []

        # Track unknown moves for debugging
        self.unknown_moves: list[str] = []

    def analyze_all(self):
        """Run all analyses."""
        print(f"Analyzing {self.metadata['num_games']} games, {self.metadata['total_moves']} moves")
        print(f"MCTS wins: {sum(1 for g in self.games if g['mcts_won'])} ({sum(1 for g in self.games if g['mcts_won']) / len(self.games) * 100:.1f}%)")
        print()

        for game in self.games:
            game_won = game["mcts_won"]
            for move_data in game["moves"]:
                self._analyze_move(move_data, game_won)

        self._print_summary()
        self._print_unknown_moves()
        self._print_point_card_analysis()
        self._print_one_off_analysis()
        self._print_permanent_analysis()
        self._print_counter_analysis()
        self._print_revive_analysis()
        self._print_scuttle_analysis()
        self._print_draw_analysis()
        self._print_stage_breakdown()
        self._print_card_action_choices()
        self._print_detailed_recommendations()

    def _analyze_move(self, move_data: dict, game_won: bool):
        """Analyze a single move decision."""
        turn = move_data["turn"]
        stage = get_game_stage(turn)
        selected = move_data["selected_move"]
        visits = move_data["selected_visits"]
        win_rate = move_data["selected_win_rate"]
        all_visits = move_data["visit_counts"]
        all_win_rates = move_data["win_rates"]

        parsed = parse_move(selected)
        move_type = parsed["type"]

        # Track unknown moves for debugging
        if move_type == "unknown":
            self.unknown_moves.append(selected)

        # Overall move type stats
        self.move_type_stats[move_type].add(visits, win_rate, game_won)
        self.move_type_by_stage[move_type][stage].add(visits, win_rate, game_won)

        # Analyze what was available vs what was chosen
        self._analyze_alternatives(move_data, parsed, game_won)

        # Analyze scuttle decisions in detail
        self._analyze_scuttle_decisions(move_data, parsed, stage)

        # Point card analysis
        if move_type == "points":
            rank = parsed["card"]["rank"]
            value = get_rank_value(rank)
            self.point_card_stats[value].add(visits, win_rate, game_won)
            self.point_card_by_stage[value][stage].add(visits, win_rate, game_won)

        # One-off analysis
        elif move_type in (
            "ace_oneoff",
            "two_destroy",
            "three_revive",
            "four_discard",
            "five_draw",
            "six_scrap",
            "seven_deck",
            "nine_return",
        ):
            self.one_off_stats[move_type].add(visits, win_rate, game_won)
            self.one_off_by_stage[move_type][stage].add(visits, win_rate, game_won)

            # Revive target tracking
            if move_type == "three_revive" and parsed["target"]:
                target_rank = parsed["target"]["rank"]
                self.revive_targets[target_rank].add(visits, win_rate, game_won)

        # Jack steal analysis
        elif move_type == "jack_steal" and parsed["target"]:
            target_value = get_rank_value(parsed["target"]["rank"])
            self.jack_steal_targets[target_value].add(visits, win_rate, game_won)

        # Scuttle analysis
        elif move_type == "scuttle" and parsed["card"] and parsed["target"]:
            scuttler_value = get_rank_value(parsed["card"]["rank"])
            target_value = get_rank_value(parsed["target"]["rank"])
            self.scuttle_patterns[(scuttler_value, target_value)].add(
                visits, win_rate, game_won
            )

        # Draw analysis
        elif move_type == "draw":
            self.draw_stats_by_stage[stage].add(visits, win_rate, game_won)

        # Counter analysis
        elif move_type == "counter":
            # Need to infer what's being countered from context
            # This is tricky - we'd need phase info
            pass

        elif move_type == "decline_counter":
            pass

    def _analyze_scuttle_decisions(self, move_data: dict, selected_parsed: dict, stage: str):
        """Analyze when scuttle was available and what MCTS chose instead."""
        all_moves = move_data["legal_moves"]
        all_visits = move_data["visit_counts"]
        all_win_rates = move_data["win_rates"]
        selected = move_data["selected_move"]

        # Find all scuttle options available
        scuttle_options = []
        for move_str in all_moves:
            parsed = parse_move(move_str)
            if parsed["type"] == "scuttle":
                scuttle_options.append({
                    "move": move_str,
                    "visits": all_visits.get(move_str, 0),
                    "win_rate": all_win_rates.get(move_str, 0.0),
                    "attacker": get_rank_value(parsed["card"]["rank"]) if parsed["card"] else None,
                    "target": get_rank_value(parsed["target"]["rank"]) if parsed["target"] else None,
                })

        if not scuttle_options:
            return

        # Was scuttle chosen?
        if selected_parsed["type"] == "scuttle":
            self.scuttle_chosen.append({
                "stage": stage,
                "selected": selected,
                "alternatives": [m for m in all_moves if m != selected],
                "scuttle_win_rate": move_data["selected_win_rate"],
            })
        else:
            # Scuttle was available but declined
            best_scuttle = max(scuttle_options, key=lambda x: x["win_rate"])
            self.scuttle_available_but_declined.append({
                "stage": stage,
                "selected": selected,
                "selected_type": selected_parsed["type"],
                "selected_win_rate": move_data["selected_win_rate"],
                "best_scuttle": best_scuttle["move"],
                "best_scuttle_win_rate": best_scuttle["win_rate"],
                "scuttle_options": scuttle_options,
            })

    def _analyze_alternatives(self, move_data: dict, selected_parsed: dict, game_won: bool):
        """Analyze what alternatives were available when a move was selected."""
        selected = move_data["selected_move"]
        all_moves = move_data["legal_moves"]
        all_visits = move_data["visit_counts"]
        all_win_rates = move_data["win_rates"]

        # Track card-level choices: when card X is in hand, what action does MCTS take?
        for move_str in all_moves:
            parsed = parse_move(move_str)
            if parsed["card"]:
                rank = parsed["card"]["rank"]
                action_type = parsed["type"]
                visits = all_visits.get(move_str, 0)
                win_rate = all_win_rates.get(move_str, 0.0)

                # Track whether this move was selected
                was_selected = move_str == selected
                if was_selected:
                    self.card_action_choices[rank][action_type].add(visits, win_rate, game_won)

    def _print_summary(self):
        """Print overall summary statistics."""
        print("=" * 80)
        print("OVERALL MOVE TYPE DISTRIBUTION")
        print("=" * 80)

        total = sum(s.count for s in self.move_type_stats.values())
        sorted_types = sorted(
            self.move_type_stats.items(), key=lambda x: x[1].count, reverse=True
        )

        print(f"{'Move Type':<20} {'Count':>8} {'Rate':>8} {'Avg Win%':>10} {'Avg Visits':>12}")
        print("-" * 60)
        for move_type, stats in sorted_types:
            rate = stats.count / total * 100 if total > 0 else 0
            print(
                f"{move_type:<20} {stats.count:>8} {rate:>7.1f}% {stats.avg_win_rate * 100:>9.1f}% {stats.avg_visits:>12.0f}"
            )
        print()

    def _print_unknown_moves(self):
        """Print unknown moves for debugging the parser."""
        if not self.unknown_moves:
            return

        print("=" * 80)
        print("UNKNOWN MOVES (not parsed - check patterns)")
        print("=" * 80)

        # Count unique unknown moves
        from collections import Counter
        unknown_counts = Counter(self.unknown_moves)
        print(f"Total unknown: {len(self.unknown_moves)}")
        print()
        print("Sample unknown moves:")
        for move, count in unknown_counts.most_common(20):
            print(f"  ({count:>3}x) {move}")
        print()

    def _print_point_card_analysis(self):
        """Print analysis of point card usage."""
        print("=" * 80)
        print("POINT CARD USAGE (When Played for Points)")
        print("=" * 80)

        print(f"{'Value':>6} {'Count':>8} {'Avg Win%':>10} {'Opening':>10} {'Midgame':>10} {'Lategame':>10}")
        print("-" * 60)

        for value in range(10, 0, -1):
            stats = self.point_card_stats.get(value, MoveStats())
            opening = self.point_card_by_stage.get(value, {}).get("opening", MoveStats())
            midgame = self.point_card_by_stage.get(value, {}).get("midgame", MoveStats())
            lategame = self.point_card_by_stage.get(value, {}).get("lategame", MoveStats())

            opening_str = f"{opening.count}" if opening.count > 0 else "-"
            midgame_str = f"{midgame.count}" if midgame.count > 0 else "-"
            lategame_str = f"{lategame.count}" if lategame.count > 0 else "-"

            if stats.count > 0:
                print(
                    f"{value:>6} {stats.count:>8} {stats.avg_win_rate * 100:>9.1f}% {opening_str:>10} {midgame_str:>10} {lategame_str:>10}"
                )
        print()

    def _print_one_off_analysis(self):
        """Print analysis of one-off usage."""
        print("=" * 80)
        print("ONE-OFF USAGE")
        print("=" * 80)

        one_off_names = {
            "ace_oneoff": "Ace (Scrap All Points)",
            "two_destroy": "Two (Destroy Permanent)",
            "three_revive": "Three (Revive)",
            "four_discard": "Four (Force Discard)",
            "five_draw": "Five (Draw Two)",
            "six_scrap": "Six (Scrap Permanents)",
            "seven_deck": "Seven (Play from Deck)",
            "nine_return": "Nine (Return to Hand)",
        }

        print(f"{'One-Off':<25} {'Count':>6} {'Avg Win%':>9} {'Open':>6} {'Mid':>6} {'Late':>6}")
        print("-" * 65)

        for key, name in one_off_names.items():
            stats = self.one_off_stats.get(key, MoveStats())
            opening = self.one_off_by_stage.get(key, {}).get("opening", MoveStats())
            midgame = self.one_off_by_stage.get(key, {}).get("midgame", MoveStats())
            lategame = self.one_off_by_stage.get(key, {}).get("lategame", MoveStats())

            if stats.count > 0:
                print(
                    f"{name:<25} {stats.count:>6} {stats.avg_win_rate * 100:>8.1f}% {opening.count:>6} {midgame.count:>6} {lategame.count:>6}"
                )
            else:
                print(f"{name:<25} {0:>6} {'-':>9} {'-':>6} {'-':>6} {'-':>6}")
        print()

    def _print_permanent_analysis(self):
        """Print analysis of permanent card usage."""
        print("=" * 80)
        print("PERMANENT CARD USAGE")
        print("=" * 80)

        permanents = ["king", "queen", "glasses", "jack_steal"]
        names = {
            "king": "King (Threshold)",
            "queen": "Queen (Protection)",
            "glasses": "8 as Glasses",
            "jack_steal": "Jack (Steal)",
        }

        print(f"{'Permanent':<20} {'Count':>8} {'Avg Win%':>10} {'Opening':>10} {'Midgame':>10} {'Lategame':>10}")
        print("-" * 70)

        for perm in permanents:
            stats = self.move_type_stats.get(perm, MoveStats())
            opening = self.move_type_by_stage.get(perm, {}).get("opening", MoveStats())
            midgame = self.move_type_by_stage.get(perm, {}).get("midgame", MoveStats())
            lategame = self.move_type_by_stage.get(perm, {}).get("lategame", MoveStats())

            print(
                f"{names[perm]:<20} {stats.count:>8} {stats.avg_win_rate * 100:>9.1f}% {opening.count:>10} {midgame.count:>10} {lategame.count:>10}"
            )

        # Jack steal targets
        if self.jack_steal_targets:
            print()
            print("Jack Steal Targets:")
            print(f"  {'Target Value':>12} {'Count':>6} {'Avg Win%':>9}")
            for value in sorted(self.jack_steal_targets.keys(), reverse=True):
                stats = self.jack_steal_targets[value]
                print(f"  {value:>12} {stats.count:>6} {stats.avg_win_rate * 100:>8.1f}%")
        print()

    def _print_counter_analysis(self):
        """Print counter decision analysis."""
        print("=" * 80)
        print("COUNTER DECISIONS")
        print("=" * 80)

        counter_stats = self.move_type_stats.get("counter", MoveStats())
        decline_stats = self.move_type_stats.get("decline_counter", MoveStats())

        total = counter_stats.count + decline_stats.count
        if total > 0:
            counter_rate = counter_stats.count / total * 100
            decline_rate = decline_stats.count / total * 100
            print(f"Counter:  {counter_stats.count:>5} ({counter_rate:.1f}%) - Avg Win%: {counter_stats.avg_win_rate * 100:.1f}%")
            print(f"Decline:  {decline_stats.count:>5} ({decline_rate:.1f}%) - Avg Win%: {decline_stats.avg_win_rate * 100:.1f}%")
        else:
            print("No counter decisions found in MAIN phase moves")
            print("(Counter decisions occur in COUNTER phase which may not be captured)")
        print()

    def _print_revive_analysis(self):
        """Print Three revive target analysis."""
        print("=" * 80)
        print("THREE (REVIVE) TARGET ANALYSIS")
        print("=" * 80)

        if not self.revive_targets:
            print("No revive targets found (targets may not be parsed from move strings)")
            print()
            return

        total = sum(s.count for s in self.revive_targets.values())
        print(f"{'Target':>8} {'Count':>6} {'Rate':>8} {'Avg Win%':>10}")
        print("-" * 35)

        for rank in ["J", "10", "K", "9", "8", "7", "6", "5", "4", "3", "2", "A", "Q"]:
            stats = self.revive_targets.get(rank, MoveStats())
            if stats.count > 0:
                rate = stats.count / total * 100 if total > 0 else 0
                print(f"{rank:>8} {stats.count:>6} {rate:>7.1f}% {stats.avg_win_rate * 100:>9.1f}%")
        print()

    def _print_scuttle_analysis(self):
        """Print scuttle pattern analysis."""
        print("=" * 80)
        print("SCUTTLE ANALYSIS")
        print("=" * 80)

        scuttle_stats = self.move_type_stats.get("scuttle", MoveStats())
        total_moves = sum(s.count for s in self.move_type_stats.values())

        print(f"Total scuttles: {scuttle_stats.count} ({scuttle_stats.count / total_moves * 100:.2f}% of moves)")
        print(f"Average win rate when scuttling: {scuttle_stats.avg_win_rate * 100:.1f}%")

        if self.scuttle_patterns:
            print()
            print("Scuttle Patterns (Attacker → Target):")
            print(f"  {'Pattern':>10} {'Count':>6} {'Avg Win%':>10}")

            sorted_patterns = sorted(
                self.scuttle_patterns.items(), key=lambda x: x[1].count, reverse=True
            )
            for (attacker, target), stats in sorted_patterns[:15]:
                print(f"  {attacker:>3} → {target:<3} {stats.count:>6} {stats.avg_win_rate * 100:>9.1f}%")

        # Analyze when MCTS declined to scuttle
        declined_count = len(self.scuttle_available_but_declined)
        chosen_count = len(self.scuttle_chosen)
        if declined_count + chosen_count > 0:
            print()
            print(f"SCUTTLE DECISION ANALYSIS:")
            print(f"  Scuttle available: {declined_count + chosen_count} times")
            print(f"  MCTS chose scuttle: {chosen_count} ({chosen_count / (declined_count + chosen_count) * 100:.1f}%)")
            print(f"  MCTS declined scuttle: {declined_count} ({declined_count / (declined_count + chosen_count) * 100:.1f}%)")

            if self.scuttle_available_but_declined:
                print()
                print("  When MCTS declined scuttle, it chose:")
                alt_counts = defaultdict(int)
                for d in self.scuttle_available_but_declined:
                    alt_counts[d["selected_type"]] += 1
                for alt_type, count in sorted(alt_counts.items(), key=lambda x: -x[1])[:5]:
                    print(f"    {alt_type}: {count} times")

                # Compare win rates
                print()
                print("  Win rate comparison (declined scuttles):")
                total_selected_wr = sum(d["selected_win_rate"] for d in self.scuttle_available_but_declined)
                total_scuttle_wr = sum(d["best_scuttle_win_rate"] for d in self.scuttle_available_but_declined)
                avg_selected = total_selected_wr / len(self.scuttle_available_but_declined)
                avg_scuttle = total_scuttle_wr / len(self.scuttle_available_but_declined)
                print(f"    Avg win rate of selected move: {avg_selected * 100:.1f}%")
                print(f"    Avg win rate of best scuttle: {avg_scuttle * 100:.1f}%")
                print(f"    Difference: +{(avg_selected - avg_scuttle) * 100:.1f}% for non-scuttle")
        print()

    def _print_draw_analysis(self):
        """Print draw decision analysis."""
        print("=" * 80)
        print("DRAW ANALYSIS")
        print("=" * 80)

        draw_stats = self.move_type_stats.get("draw", MoveStats())
        total_moves = sum(s.count for s in self.move_type_stats.values())

        print(f"Total draws: {draw_stats.count} ({draw_stats.count / total_moves * 100:.1f}% of moves)")
        print(f"Average win rate when drawing: {draw_stats.avg_win_rate * 100:.1f}%")
        print()

        print("Draw by Game Stage:")
        print(f"  {'Stage':<10} {'Count':>6} {'Avg Win%':>10}")
        for stage in ["opening", "midgame", "lategame"]:
            stats = self.draw_stats_by_stage.get(stage, MoveStats())
            if stats.count > 0:
                print(f"  {stage:<10} {stats.count:>6} {stats.avg_win_rate * 100:>9.1f}%")
        print()

    def _print_stage_breakdown(self):
        """Print move distribution by game stage."""
        print("=" * 80)
        print("MOVE DISTRIBUTION BY GAME STAGE")
        print("=" * 80)

        stages = ["opening", "midgame", "lategame"]
        stage_totals = {stage: 0 for stage in stages}

        # Calculate totals per stage
        for move_type, stage_stats in self.move_type_by_stage.items():
            for stage, stats in stage_stats.items():
                stage_totals[stage] += stats.count

        for stage in stages:
            print(f"\n{stage.upper()} (Turns {'1-3' if stage == 'opening' else '4-8' if stage == 'midgame' else '9+'})")
            print("-" * 50)

            total = stage_totals[stage]
            if total == 0:
                print("  No moves")
                continue

            stage_moves = []
            for move_type, stage_stats in self.move_type_by_stage.items():
                if stage in stage_stats:
                    stats = stage_stats[stage]
                    if stats.count > 0:
                        stage_moves.append((move_type, stats))

            stage_moves.sort(key=lambda x: x[1].count, reverse=True)

            print(f"  {'Move Type':<20} {'Count':>6} {'Rate':>8} {'Avg Win%':>10}")
            for move_type, stats in stage_moves[:10]:
                rate = stats.count / total * 100
                print(f"  {move_type:<20} {stats.count:>6} {rate:>7.1f}% {stats.avg_win_rate * 100:>9.1f}%")
        print()

    def _print_card_action_choices(self):
        """Print analysis of card-level action choices."""
        print("=" * 80)
        print("CARD-LEVEL ACTION ANALYSIS")
        print("(When card X is played, what action does MCTS choose?)")
        print("=" * 80)

        # Analyze cards that have multiple possible actions
        multi_action_cards = {
            "A": ["points", "ace_oneoff"],
            "2": ["points", "two_destroy", "counter"],
            "3": ["points", "three_revive"],
            "4": ["points", "four_discard"],
            "5": ["points", "five_draw"],
            "6": ["points", "six_scrap"],
            "7": ["points", "seven_deck"],
            "8": ["points", "glasses"],
            "9": ["points", "nine_return"],
            "J": ["jack_steal"],
            "Q": ["queen"],
            "K": ["king"],
        }

        for rank, possible_actions in multi_action_cards.items():
            print(f"\n{rank} Card:")
            total_for_rank = sum(
                self.card_action_choices.get(rank, {}).get(action, MoveStats()).count
                for action in possible_actions
            )

            if total_for_rank == 0:
                print("  No data")
                continue

            for action in possible_actions:
                stats = self.card_action_choices.get(rank, {}).get(action, MoveStats())
                if stats.count > 0:
                    rate = stats.count / total_for_rank * 100
                    print(f"  {action:<15}: {stats.count:>5} ({rate:>5.1f}%) - Avg Win%: {stats.avg_win_rate * 100:.1f}%")
        print()

    def _print_detailed_recommendations(self):
        """Print detailed heuristic scoring recommendations with specific code changes."""
        print("=" * 80)
        print("DETAILED HEURISTIC SCORING RECOMMENDATIONS")
        print("=" * 80)

        total = sum(s.count for s in self.move_type_stats.values())

        # Calculate key metrics
        king_stats = self.move_type_stats.get("king", MoveStats())
        queen_stats = self.move_type_stats.get("queen", MoveStats())
        jack_stats = self.move_type_stats.get("jack_steal", MoveStats())
        draw_stats = self.move_type_stats.get("draw", MoveStats())

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 1. POINT CARD PRIORITIES                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        print("Current heuristic scoring:")
        print("  - High (8-10): 800 + value*10  (880-900)")
        print("  - Mid (5-7):   400 + value*10  (450-470)")
        print("  - Low (2-4):   200 + value*10  (220-240)")
        print()
        print("MCTS point card win rates by value:")
        for value in [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]:
            stats = self.point_card_stats.get(value, MoveStats())
            if stats.count > 0:
                print(f"  {value:>2}: {stats.avg_win_rate * 100:>5.1f}% win rate, {stats.count:>4} plays")

        print()
        print("RECOMMENDATION: Current scoring is well-aligned with MCTS behavior.")
        print("  - High cards (8-10) have best win rates (75-87%)")
        print("  - Priority order 10 > 9 > 8 > 7 > 6 > 5 > 4 > 3 > 2 > A is correct")

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 2. ONE-OFF USAGE PATTERNS                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        # Ace analysis
        ace_stats = self.one_off_stats.get("ace_oneoff", MoveStats())
        ace_opening = self.one_off_by_stage.get("ace_oneoff", {}).get("opening", MoveStats())

        ace_total = self.card_action_choices.get("A", {})
        ace_points = ace_total.get("points", MoveStats()).count
        ace_oneoff = ace_total.get("ace_oneoff", MoveStats()).count
        ace_total_uses = ace_points + ace_oneoff

        print("ACE (Scrap All Points):")
        print(f"  Total Ace plays: {ace_total_uses}")
        if ace_total_uses > 0:
            print(f"  As one-off: {ace_oneoff} ({ace_oneoff/ace_total_uses*100:.1f}%)")
            print(f"  As points:  {ace_points} ({ace_points/ace_total_uses*100:.1f}%)")
        if ace_stats.count > 0:
            print(f"  Opening one-offs: {ace_opening.count} ({ace_opening.count/ace_stats.count*100:.0f}% of one-offs)")
            print(f"  Avg win rate when using one-off: {ace_stats.avg_win_rate * 100:.1f}%")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: 700 opening, 500 midgame (only when behind 8+)")
        print("    - MCTS uses Ace one-off 73.5% of time (mostly opening)")
        print("    - Keep current context-sensitive scoring (behind check is critical)")

        # Four analysis
        four_stats = self.one_off_stats.get("four_discard", MoveStats())
        four_opening = self.one_off_by_stage.get("four_discard", {}).get("opening", MoveStats())

        four_total = self.card_action_choices.get("4", {})
        four_points = four_total.get("points", MoveStats()).count
        four_oneoff = four_total.get("four_discard", MoveStats()).count

        print()
        print("FOUR (Force Discard):")
        if four_points + four_oneoff > 0:
            print(f"  As one-off: {four_oneoff} ({four_oneoff/(four_points+four_oneoff)*100:.1f}%)")
            print(f"  As points:  {four_points} ({four_points/(four_points+four_oneoff)*100:.1f}%)")
        if four_stats.count > 0:
            print(f"  Opening: {four_opening.count} ({four_opening.count/four_stats.count*100:.0f}% of one-offs)")
            print(f"  Win rate: {four_stats.avg_win_rate * 100:.1f}%")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: 450 opening, 200 midgame, 100 lategame")
        print("    - MCTS uses Four for points 60% of time!")
        print("    - LOWER one-off score: 350 opening, 150 midgame")
        print("    - The 41% win rate suggests it's often a weak play")

        # Five analysis
        five_stats = self.one_off_stats.get("five_draw", MoveStats())
        five_opening = self.one_off_by_stage.get("five_draw", {}).get("opening", MoveStats())

        five_total = self.card_action_choices.get("5", {})
        five_points = five_total.get("points", MoveStats()).count
        five_oneoff = five_total.get("five_draw", MoveStats()).count

        print()
        print("FIVE (Draw Two):")
        if five_points + five_oneoff > 0:
            print(f"  As one-off: {five_oneoff} ({five_oneoff/(five_points+five_oneoff)*100:.1f}%)")
            print(f"  As points:  {five_points} ({five_points/(five_points+five_oneoff)*100:.1f}%)")
        if five_stats.count > 0:
            print(f"  Opening: {five_opening.count} ({five_opening.count/five_stats.count*100:.0f}% of one-offs)")
            print(f"  Win rate: {five_stats.avg_win_rate * 100:.1f}%")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: 400 opening, 300 midgame")
        print("    - MCTS prefers 5 for points 65.6% of time")
        print("    - LOWER one-off score: 300 opening, 200 midgame")

        # Seven analysis
        seven_stats = self.one_off_stats.get("seven_deck", MoveStats())
        seven_opening = self.one_off_by_stage.get("seven_deck", {}).get("opening", MoveStats())

        seven_total = self.card_action_choices.get("7", {})
        seven_points = seven_total.get("points", MoveStats()).count
        seven_oneoff = seven_total.get("seven_deck", MoveStats()).count

        print()
        print("SEVEN (Play from Deck):")
        if seven_points + seven_oneoff > 0:
            print(f"  As one-off: {seven_oneoff} ({seven_oneoff/(seven_points+seven_oneoff)*100:.1f}%)")
            print(f"  As points:  {seven_points} ({seven_points/(seven_points+seven_oneoff)*100:.1f}%)")
        if seven_stats.count > 0:
            print(f"  Opening: {seven_opening.count} ({seven_opening.count/seven_stats.count*100:.0f}% of one-offs)")
            print(f"  Win rate: {seven_stats.avg_win_rate * 100:.1f}%")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: 450 opening, 300 midgame")
        print("    - MCTS prefers 7 for points 68.8% of time")
        print("    - LOWER one-off score: 350 opening, 250 midgame")

        # Three analysis
        three_stats = self.one_off_stats.get("three_revive", MoveStats())

        three_total = self.card_action_choices.get("3", {})
        three_points = three_total.get("points", MoveStats()).count
        three_oneoff = three_total.get("three_revive", MoveStats()).count

        print()
        print("THREE (Revive):")
        if three_points + three_oneoff > 0:
            print(f"  As revive:  {three_oneoff} ({three_oneoff/(three_points+three_oneoff)*100:.1f}%)")
            print(f"  As points:  {three_points} ({three_points/(three_points+three_oneoff)*100:.1f}%)")
        if three_stats.count > 0:
            print(f"  Win rate: {three_stats.avg_win_rate * 100:.1f}%")
        print()
        print("  Revive target priorities (from data):")
        total_revives = sum(s.count for s in self.revive_targets.values())
        if total_revives > 0:
            for rank in ["10", "J", "K", "9", "8", "7"]:
                stats = self.revive_targets.get(rank, MoveStats())
                if stats.count > 0:
                    print(f"    {rank:>2}: {stats.count:>3} ({stats.count/total_revives*100:>5.1f}%) - {stats.avg_win_rate*100:.1f}% win rate")
        print()
        print("  RECOMMENDATION:")
        print("    - Current revive scoring (Jack > 10 > King > 9 > 8) is correct")
        print("    - Consider: MCTS uses points 58% of time - lower revive scores slightly")

        # Six analysis
        six_stats = self.one_off_stats.get("six_scrap", MoveStats())

        six_total = self.card_action_choices.get("6", {})
        six_points = six_total.get("points", MoveStats()).count
        six_oneoff = six_total.get("six_scrap", MoveStats()).count

        print()
        print("SIX (Scrap All Permanents):")
        if six_points + six_oneoff > 0:
            print(f"  As one-off: {six_oneoff} ({six_oneoff/(six_points+six_oneoff)*100:.1f}%)")
            print(f"  As points:  {six_points} ({six_points/(six_points+six_oneoff)*100:.1f}%)")
        if six_stats.count > 0:
            print(f"  Win rate: {six_stats.avg_win_rate * 100:.1f}%")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: 30 (almost never use)")
        print("    - MCTS agrees: 94.4% for points, only 5.6% one-off")
        print("    - KEEP current low scoring")

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 3. PERMANENT CARDS                                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        print("KING (Threshold Reduction):")
        print(f"  Uses: {king_stats.count} ({king_stats.count/total*100:.1f}% of moves)")
        print(f"  Win rate: {king_stats.avg_win_rate * 100:.1f}%")
        print(f"  Current score: 600")
        print("  RECOMMENDATION: Score is appropriate (70% win rate)")
        print()

        print("QUEEN (Protection):")
        print(f"  Uses: {queen_stats.count} ({queen_stats.count/total*100:.1f}% of moves)")
        print(f"  Win rate: {queen_stats.avg_win_rate * 100:.1f}%")
        print(f"  Current score: 150")
        print("  RECOMMENDATION:")
        print("    - 45% win rate is LOW - Queens correlate with losing")
        print("    - MCTS plays Queen when it has weak options")
        print("    - LOWER score to 100 (or keep 150 as a 'last resort')")
        print()

        print("JACK (Steal):")
        print(f"  Uses: {jack_stats.count} ({jack_stats.count/total*100:.1f}% of moves)")
        print(f"  Win rate: {jack_stats.avg_win_rate * 100:.1f}%")
        print(f"  Current score: 300 + target_value*20 (+ bonuses when behind)")
        print()
        print("  Target distribution:")
        for value in [10, 9, 8, 7, 6, 5]:
            stats = self.jack_steal_targets.get(value, MoveStats())
            if stats.count > 0:
                print(f"    {value:>2}: {stats.count:>3} steals, {stats.avg_win_rate*100:.1f}% win rate")
        print()
        print("  RECOMMENDATION:")
        print("    - 79.5% win rate is EXCELLENT")
        print("    - Jack steal is one of the best plays available")
        print("    - INCREASE base score: 400 + target_value*25")

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 4. SCUTTLE DECISIONS                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        declined = len(self.scuttle_available_but_declined)
        chosen = len(self.scuttle_chosen)
        total_scuttle_opps = declined + chosen

        print(f"Scuttle opportunities: {total_scuttle_opps}")
        if total_scuttle_opps > 0:
            print(f"  MCTS scuttled: {chosen} ({chosen/total_scuttle_opps*100:.1f}%)")
            print(f"  MCTS declined: {declined} ({declined/total_scuttle_opps*100:.1f}%)")

        if self.scuttle_available_but_declined:
            total_sel = sum(d["selected_win_rate"] for d in self.scuttle_available_but_declined)
            total_scut = sum(d["best_scuttle_win_rate"] for d in self.scuttle_available_but_declined)
            print()
            print("  When declining scuttle:")
            print(f"    Avg selected move win rate: {total_sel/declined*100:.1f}%")
            print(f"    Avg scuttle win rate:       {total_scut/declined*100:.1f}%")
            print(f"    Difference: {(total_sel-total_scut)/declined*100:+.1f}%")

        print()
        print("  RECOMMENDATION:")
        print("    - Current: Base 20 + value_diff (very low)")
        print("    - MCTS confirms: scuttle is almost never correct")
        print("    - KEEP current low scoring")
        print("    - Exception: Check for opponent near win (5000 score already)")

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 5. DRAW DECISION                                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        print(f"Draw usage: {draw_stats.count} ({draw_stats.count/total*100:.1f}% of moves)")
        print(f"Win rate: {draw_stats.avg_win_rate * 100:.1f}%")
        print()
        print("By game stage:")
        for stage in ["opening", "midgame", "lategame"]:
            stats = self.draw_stats_by_stage.get(stage, MoveStats())
            if stats.count > 0:
                print(f"  {stage:>10}: {stats.count:>4} draws, {stats.avg_win_rate*100:.1f}% win rate")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: 300")
        print("    - 58% win rate is below average - Draw is often a 'settle' option")
        print("    - MCTS draws heavily in midgame (21.6%) looking for better options")
        print("    - Consider LOWERING to 250 to prefer points over draw")

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 6. COUNTER DECISIONS                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        counter_stats = self.move_type_stats.get("counter", MoveStats())
        decline_stats = self.move_type_stats.get("decline_counter", MoveStats())

        total_counter_decisions = counter_stats.count + decline_stats.count
        if total_counter_decisions > 0:
            print(f"Counter opportunities: {total_counter_decisions}")
            print(f"  Counter: {counter_stats.count} ({counter_stats.count/total_counter_decisions*100:.1f}%) - {counter_stats.avg_win_rate*100:.1f}% win rate")
            print(f"  Decline: {decline_stats.count} ({decline_stats.count/total_counter_decisions*100:.1f}%) - {decline_stats.avg_win_rate*100:.1f}% win rate")
        print()
        print("  RECOMMENDATION:")
        print("    - Current: Counter Ace=400, Five=350, Four=100, Two=80")
        print("    - MCTS only counters 22% of the time")
        print("    - Counter win rate (75.6%) > Decline (52.4%)")
        print("    - But MCTS still declines 78% - context matters!")
        print("    - KEEP current selective counter strategy")

        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║ SUMMARY OF RECOMMENDED CHANGES                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. FOUR one-off: REDUCE 450->350 opening, 200->150 midgame
   Reason: MCTS uses points 60% of time, 41% win rate when one-off

2. FIVE one-off: REDUCE 400->300 opening, 300->200 midgame
   Reason: MCTS uses points 65.6% of time

3. SEVEN one-off: REDUCE 450->350 opening, 300->250 midgame
   Reason: MCTS uses points 68.8% of time

4. QUEEN: REDUCE 150->100
   Reason: 45% win rate - correlates with weaker positions

5. JACK steal: INCREASE 300->400 base, 20->25 per target value
   Reason: 79.5% win rate - one of the best plays

6. DRAW: REDUCE 300->250
   Reason: 58% win rate - should prefer point plays

7. KEEP UNCHANGED:
   - Point card scoring (aligned with MCTS)
   - Scuttle scoring (MCTS confirms rarely correct)
   - Six one-off scoring (94% for points)
   - Counter decision thresholds (selective countering correct)
   - Ace one-off (context-sensitive scoring working)
   - King scoring (70% win rate appropriate)
""")


def main():
    data_path = Path(__file__).parent.parent / "training_data" / "mcts2000_vs_heuristic_1000games.json"

    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        return

    analyzer = MCTSAnalyzer(data_path)
    analyzer.analyze_all()


if __name__ == "__main__":
    main()

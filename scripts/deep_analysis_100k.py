"""Deep analysis of 100k games - looking for nuanced patterns."""

import json
from collections import defaultdict
from pathlib import Path
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.cards import Rank, Card
from cuttle_engine.moves import (
    PlayPoints, PlayPermanent, PlayOneOff, Scuttle, Draw,
    Counter, DeclineCounter, Discard, Pass, ResolveSeven, OneOffEffect
)
from strategies.random_strategy import RandomStrategy


OUTPUT_DIR = Path("analysis_output")


def get_move_info(move):
    """Extract detailed info about a move."""
    info = {"type": None, "rank": None, "effect": None}

    match move:
        case PlayPoints(card=card):
            info["type"] = "PlayPoints"
            info["rank"] = card.rank.name
        case PlayPermanent(card=card):
            info["type"] = "PlayPermanent"
            info["rank"] = card.rank.name
        case PlayOneOff(card=card, effect=effect):
            info["type"] = "PlayOneOff"
            info["rank"] = card.rank.name
            info["effect"] = effect.name if effect else None
        case Scuttle():
            info["type"] = "Scuttle"
        case Draw():
            info["type"] = "Draw"
        case Counter():
            info["type"] = "Counter"
        case DeclineCounter():
            info["type"] = "DeclineCounter"
        case Discard():
            info["type"] = "Discard"
        case Pass():
            info["type"] = "Pass"
        case ResolveSeven():
            info["type"] = "ResolveSeven"

    return info


def count_aces_in_location(state, location):
    """Count aces in a specific location."""
    count = 0
    if location == "deck":
        count = sum(1 for c in state.deck if c.rank == Rank.ACE)
    elif location == "scrap":
        count = sum(1 for c in state.scrap if c.rank == Rank.ACE)
    elif location == "p0_hand":
        count = sum(1 for c in state.players[0].hand if c.rank == Rank.ACE)
    elif location == "p1_hand":
        count = sum(1 for c in state.players[1].hand if c.rank == Rank.ACE)
    elif location == "p0_points":
        count = sum(1 for c in state.players[0].points_field if c.rank == Rank.ACE)
    elif location == "p1_points":
        count = sum(1 for c in state.players[1].points_field if c.rank == Rank.ACE)
    return count


def get_ace_state(state, player):
    """Get ace-related state info for a player."""
    opponent = 1 - player

    # Aces in own hand
    my_aces = sum(1 for c in state.players[player].hand if c.rank == Rank.ACE)

    # Known aces (in scrap, on field)
    aces_in_scrap = sum(1 for c in state.scrap if c.rank == Rank.ACE)
    aces_on_my_field = sum(1 for c in state.players[player].points_field if c.rank == Rank.ACE)
    aces_on_opp_field = sum(1 for c in state.players[opponent].points_field if c.rank == Rank.ACE)

    # Unknown aces (in deck or opponent hand) - there are 4 total
    known_aces = my_aces + aces_in_scrap + aces_on_my_field + aces_on_opp_field
    unknown_aces = 4 - known_aces

    return {
        "my_aces": my_aces,
        "aces_scrapped": aces_in_scrap,
        "unknown_aces": unknown_aces,  # Could threaten my points
        "total_known_safe": aces_in_scrap + aces_on_my_field + aces_on_opp_field  # Can't hurt me
    }


def analyze_games(num_games=100000):
    """Run comprehensive analysis."""

    print(f"Running {num_games} games for deep analysis...")

    # === TRACKING STRUCTURES ===

    # Basic move stats
    move_stats = defaultdict(lambda: {"count": 0, "wins": 0})

    # One-off effectiveness by context
    oneoff_by_context = defaultdict(lambda: {"count": 0, "wins": 0})

    # Ace-related tracking
    ace_stats = {
        "played_ace_oneoff": {"count": 0, "wins": 0},
        "played_high_points_with_unknown_aces": defaultdict(lambda: {"count": 0, "wins": 0}),
        "played_high_points_aces_safe": defaultdict(lambda: {"count": 0, "wins": 0}),
        "got_aced": {"count": 0, "wins": 0},  # Had points scrapped by ace
    }

    # Tempo tracking - points accumulated by turn
    tempo_stats = {
        "early_points_leader": {"count": 0, "wins": 0},  # Leading by turn 5
        "early_points_trailer": {"count": 0, "wins": 0},
    }

    # One-off value: was the effect actually useful?
    oneoff_impact = defaultdict(lambda: {
        "destroyed_high_value": {"count": 0, "wins": 0},  # Destroyed 7+ point card or royal
        "destroyed_low_value": {"count": 0, "wins": 0},
        "no_target": {"count": 0, "wins": 0},
    })

    # Scuttle analysis
    scuttle_stats = {
        "favorable": {"count": 0, "wins": 0},  # Destroyed higher value than lost
        "even": {"count": 0, "wins": 0},
        "unfavorable": {"count": 0, "wins": 0},
    }

    # Game length correlation
    game_length_wins = defaultdict(lambda: {"p0": 0, "p1": 0, "total": 0})

    # First blood - who scores first
    first_blood = {"scorer_wins": 0, "scorer_loses": 0}

    # Point threshold tracking (Kings played)
    threshold_stats = {
        "played_king": {"count": 0, "wins": 0},
        "opponent_played_king": {"count": 0, "wins": 0},
    }

    errors = 0

    for seed in range(num_games):
        if seed % 10000 == 0:
            print(f"  Progress: {seed}/{num_games}")

        state = create_initial_state(seed=seed)
        strategy = RandomStrategy(seed=seed * 2)

        game_moves = []  # Track all moves for post-game analysis
        first_scorer = None
        points_at_turn_5 = {0: 0, 1: 0}
        kings_played_by = {0: False, 1: False}
        got_aced = {0: False, 1: False}

        turn = 0
        while not state.is_game_over and turn < 500:
            if state.phase == GamePhase.COUNTER:
                acting = state.counter_state.waiting_for_player
            elif state.phase == GamePhase.DISCARD_FOUR:
                acting = state.four_state.player
            elif state.phase == GamePhase.RESOLVE_SEVEN:
                acting = state.seven_state.player
            else:
                acting = state.current_player

            opponent = 1 - acting

            legal_moves = generate_legal_moves(state)
            if not legal_moves:
                break

            move = strategy.select_move(state, legal_moves)
            move_info = get_move_info(move)

            # Get context before move
            ace_state = get_ace_state(state, acting)
            my_points_before = state.players[acting].point_total
            opp_points_before = state.players[opponent].point_total
            opp_permanents_before = len(state.players[opponent].permanents)

            # Record move context
            move_record = {
                "turn": turn,
                "player": acting,
                "move_info": move_info,
                "ace_state": ace_state,
                "my_points": my_points_before,
                "opp_points": opp_points_before,
            }

            # Track specific patterns

            # High points with ace threat
            if move_info["type"] == "PlayPoints" and move_info["rank"] in ["TEN", "NINE", "EIGHT", "SEVEN"]:
                if ace_state["unknown_aces"] > 0:
                    key = f"{ace_state['unknown_aces']}_unknown"
                    ace_stats["played_high_points_with_unknown_aces"][key]["count"] += 1
                    move_record["high_points_ace_context"] = key
                else:
                    ace_stats["played_high_points_aces_safe"]["safe"]["count"] += 1
                    move_record["high_points_ace_context"] = "safe"

            # King plays
            if move_info["type"] == "PlayPermanent" and move_info["rank"] == "KING":
                kings_played_by[acting] = True

            # One-off context
            if move_info["type"] == "PlayOneOff":
                effect = move_info.get("effect", "")

                # TWO destroys permanent
                if "TWO" in str(effect) or move_info["rank"] == "TWO":
                    # Check if opponent has high-value permanents
                    has_royal = any(c.rank in [Rank.KING, Rank.QUEEN, Rank.JACK]
                                   for c in state.players[opponent].permanents)
                    context = "has_royal" if has_royal else "no_royal"
                    oneoff_by_context[f"TWO_{context}"]["count"] += 1
                    move_record["oneoff_context"] = context

                # SIX scraps all permanents
                if "SIX" in str(effect) or move_info["rank"] == "SIX":
                    opp_perm_count = len(state.players[opponent].permanents)
                    my_perm_count = len(state.players[acting].permanents)
                    advantage = opp_perm_count - my_perm_count
                    if advantage > 0:
                        context = "favorable"
                    elif advantage < 0:
                        context = "unfavorable"
                    else:
                        context = "even"
                    oneoff_by_context[f"SIX_{context}"]["count"] += 1
                    move_record["oneoff_context"] = context

                # NINE returns permanent to hand
                if "NINE" in str(effect) or move_info["rank"] == "NINE":
                    has_royal = any(c.rank in [Rank.KING, Rank.QUEEN, Rank.JACK]
                                   for c in state.players[opponent].permanents)
                    context = "has_royal" if has_royal else "no_royal"
                    oneoff_by_context[f"NINE_{context}"]["count"] += 1
                    move_record["oneoff_context"] = context

                # ACE scraps all points
                if "ACE" in str(effect) or move_info["rank"] == "ACE":
                    point_diff = opp_points_before - my_points_before
                    if point_diff > 5:
                        context = "behind_big"
                    elif point_diff > 0:
                        context = "behind_small"
                    elif point_diff < -5:
                        context = "ahead_big"
                    elif point_diff < 0:
                        context = "ahead_small"
                    else:
                        context = "even"
                    oneoff_by_context[f"ACE_{context}"]["count"] += 1
                    move_record["oneoff_context"] = context
                    ace_stats["played_ace_oneoff"]["count"] += 1

            # Scuttle analysis
            if move_info["type"] == "Scuttle" and hasattr(move, 'card') and hasattr(move, 'target'):
                my_value = move.card.point_value
                target_value = move.target.point_value
                if my_value < target_value:
                    scuttle_stats["favorable"]["count"] += 1
                    move_record["scuttle_type"] = "favorable"
                elif my_value > target_value:
                    scuttle_stats["unfavorable"]["count"] += 1
                    move_record["scuttle_type"] = "unfavorable"
                else:
                    scuttle_stats["even"]["count"] += 1
                    move_record["scuttle_type"] = "even"

            game_moves.append(move_record)

            try:
                new_state = execute_move(state, move)
            except IllegalMoveError:
                errors += 1
                break

            # Post-move tracking

            # Check if opponent's points got wiped (aced)
            if state.players[opponent].point_total > 0 and new_state.players[opponent].point_total == 0:
                if move_info["type"] == "PlayOneOff" and move_info["rank"] == "ACE":
                    got_aced[opponent] = True

            # First blood tracking
            if first_scorer is None:
                if new_state.players[acting].point_total > state.players[acting].point_total:
                    first_scorer = acting

            # Turn 5 snapshot
            if turn == 5:
                points_at_turn_5[0] = new_state.players[0].point_total
                points_at_turn_5[1] = new_state.players[1].point_total

            state = new_state
            turn += 1

        if state.winner is None:
            continue

        winner = state.winner
        loser = 1 - winner

        # === POST-GAME ANALYSIS ===

        # Game length
        length_bucket = (turn // 10) * 10
        game_length_wins[length_bucket]["total"] += 1
        game_length_wins[length_bucket][f"p{winner}"] += 1

        # First blood
        if first_scorer is not None:
            if first_scorer == winner:
                first_blood["scorer_wins"] += 1
            else:
                first_blood["scorer_loses"] += 1

        # Turn 5 leader
        if points_at_turn_5[0] > points_at_turn_5[1]:
            tempo_stats["early_points_leader"]["count"] += 1
            if winner == 0:
                tempo_stats["early_points_leader"]["wins"] += 1
        elif points_at_turn_5[1] > points_at_turn_5[0]:
            tempo_stats["early_points_leader"]["count"] += 1
            if winner == 1:
                tempo_stats["early_points_leader"]["wins"] += 1

        # King impact
        for p in [0, 1]:
            if kings_played_by[p]:
                threshold_stats["played_king"]["count"] += 1
                if winner == p:
                    threshold_stats["played_king"]["wins"] += 1

        # Got aced impact
        for p in [0, 1]:
            if got_aced[p]:
                ace_stats["got_aced"]["count"] += 1
                if winner == p:
                    ace_stats["got_aced"]["wins"] += 1

        # Update all move records with win/loss
        for record in game_moves:
            player = record["player"]
            won = (winner == player)
            move_info = record["move_info"]

            # Basic stats
            key = f"{move_info['type']}_{move_info['rank']}" if move_info['rank'] else move_info['type']
            move_stats[key]["count"] += 1
            if won:
                move_stats[key]["wins"] += 1

            # One-off context
            if "oneoff_context" in record:
                ctx_key = f"{move_info['rank']}_{record['oneoff_context']}"
                oneoff_by_context[ctx_key]["count"] += 1
                if won:
                    oneoff_by_context[ctx_key]["wins"] += 1

            # High points with ace context
            if "high_points_ace_context" in record:
                ctx = record["high_points_ace_context"]
                if ctx == "safe":
                    if won:
                        ace_stats["played_high_points_aces_safe"]["safe"]["wins"] += 1
                else:
                    if won:
                        ace_stats["played_high_points_with_unknown_aces"][ctx]["wins"] += 1

            # Scuttle type
            if "scuttle_type" in record:
                if won:
                    scuttle_stats[record["scuttle_type"]]["wins"] += 1

            # Ace oneoff
            if move_info["type"] == "PlayOneOff" and move_info["rank"] == "ACE":
                if won:
                    ace_stats["played_ace_oneoff"]["wins"] += 1

    # === PRINT RESULTS ===

    print(f"\n{'='*80}")
    print(f"DEEP ANALYSIS RESULTS - {num_games} GAMES")
    print(f"{'='*80}")
    print(f"Errors: {errors}")

    # One-off effectiveness by context
    print(f"\n{'='*80}")
    print("ONE-OFF EFFECTIVENESS BY CONTEXT")
    print(f"{'='*80}")
    print(f"{'Context':<35} {'Count':>10} {'Win Rate':>10}")
    print("-" * 60)

    for key, stats in sorted(oneoff_by_context.items(), key=lambda x: x[1]["count"], reverse=True):
        if stats["count"] >= 100:
            rate = stats["wins"] / stats["count"]
            print(f"{key:<35} {stats['count']:>10} {rate:>10.1%}")

    # Ace impact
    print(f"\n{'='*80}")
    print("ACE IMPACT ON STRATEGY")
    print(f"{'='*80}")

    print("\nPlaying high points (7-10) with ace threat:")
    print(f"{'Ace Situation':<25} {'Count':>10} {'Win Rate':>10}")
    print("-" * 50)
    for key, stats in sorted(ace_stats["played_high_points_with_unknown_aces"].items()):
        if stats["count"] >= 100:
            rate = stats["wins"] / stats["count"]
            print(f"{key:<25} {stats['count']:>10} {rate:>10.1%}")

    safe = ace_stats["played_high_points_aces_safe"]["safe"]
    if safe["count"] > 0:
        print(f"{'All aces accounted for':<25} {safe['count']:>10} {safe['wins']/safe['count']:>10.1%}")

    print(f"\nUsing Ace as one-off (scrap all points):")
    ao = ace_stats["played_ace_oneoff"]
    if ao["count"] > 0:
        print(f"  Count: {ao['count']}, Win rate: {ao['wins']/ao['count']:.1%}")

    print(f"\nGetting 'Aced' (your points scrapped):")
    ga = ace_stats["got_aced"]
    if ga["count"] > 0:
        print(f"  Count: {ga['count']}, Win rate after being aced: {ga['wins']/ga['count']:.1%}")

    # Tempo/Speed analysis
    print(f"\n{'='*80}")
    print("TEMPO / SPEED ANALYSIS")
    print(f"{'='*80}")

    fb_total = first_blood["scorer_wins"] + first_blood["scorer_loses"]
    if fb_total > 0:
        print(f"\nFirst to score points:")
        print(f"  First scorer wins: {first_blood['scorer_wins']}/{fb_total} ({100*first_blood['scorer_wins']/fb_total:.1f}%)")

    el = tempo_stats["early_points_leader"]
    if el["count"] > 0:
        print(f"\nLeading in points at turn 5:")
        print(f"  Leader wins: {el['wins']}/{el['count']} ({100*el['wins']/el['count']:.1f}%)")

    # Scuttle analysis
    print(f"\n{'='*80}")
    print("SCUTTLE EFFECTIVENESS")
    print(f"{'='*80}")
    print(f"{'Type':<20} {'Count':>10} {'Win Rate':>10}")
    print("-" * 45)
    for stype in ["favorable", "even", "unfavorable"]:
        stats = scuttle_stats[stype]
        if stats["count"] > 0:
            rate = stats["wins"] / stats["count"]
            print(f"{stype:<20} {stats['count']:>10} {rate:>10.1%}")

    # King impact
    print(f"\n{'='*80}")
    print("KING (THRESHOLD REDUCTION) IMPACT")
    print(f"{'='*80}")
    pk = threshold_stats["played_king"]
    if pk["count"] > 0:
        print(f"Player who played King wins: {pk['wins']}/{pk['count']} ({100*pk['wins']/pk['count']:.1f}%)")

    # Game length
    print(f"\n{'='*80}")
    print("GAME LENGTH ANALYSIS")
    print(f"{'='*80}")
    print(f"{'Length (turns)':<15} {'Games':>10} {'P0 Wins':>10} {'P1 Wins':>10}")
    print("-" * 50)
    for length in sorted(game_length_wins.keys()):
        stats = game_length_wins[length]
        if stats["total"] >= 100:
            print(f"{length}-{length+9:<10} {stats['total']:>10} {stats['p0']:>10} {stats['p1']:>10}")

    # Save to file
    OUTPUT_DIR.mkdir(exist_ok=True)

    results = {
        "move_stats": {k: dict(v) for k, v in move_stats.items()},
        "oneoff_by_context": {k: dict(v) for k, v in oneoff_by_context.items()},
        "ace_stats": {
            "played_ace_oneoff": dict(ace_stats["played_ace_oneoff"]),
            "played_high_points_with_unknown_aces": {k: dict(v) for k, v in ace_stats["played_high_points_with_unknown_aces"].items()},
            "played_high_points_aces_safe": {k: dict(v) for k, v in ace_stats["played_high_points_aces_safe"].items()},
            "got_aced": dict(ace_stats["got_aced"]),
        },
        "tempo_stats": {k: dict(v) for k, v in tempo_stats.items()},
        "scuttle_stats": {k: dict(v) for k, v in scuttle_stats.items()},
        "first_blood": first_blood,
        "threshold_stats": {k: dict(v) for k, v in threshold_stats.items()},
        "game_length_wins": {k: dict(v) for k, v in game_length_wins.items()},
    }

    with open(OUTPUT_DIR / "deep_analysis_100k.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nDetailed results saved to {OUTPUT_DIR}/deep_analysis_100k.json")


if __name__ == "__main__":
    analyze_games(100000)

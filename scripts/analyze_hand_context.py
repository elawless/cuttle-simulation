"""Analyze whether bad moves correlate with weak hands."""

import json
from collections import defaultdict
from pathlib import Path
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.cards import Rank
from cuttle_engine.moves import (
    PlayPoints, PlayPermanent, PlayOneOff, Scuttle, Draw,
    Counter, DeclineCounter, Discard, Pass, ResolveSeven
)
from strategies.random_strategy import RandomStrategy


def hand_quality_score(hand):
    """Score a hand's quality (higher = better).

    Based on 10k analysis:
    - High point cards (10, 9, 8, 7) are valuable
    - Jacks and Kings are valuable
    - Queens and 8-permanents are less valuable
    """
    score = 0
    for card in hand:
        if card.rank == Rank.TEN:
            score += 10
        elif card.rank == Rank.NINE:
            score += 9
        elif card.rank == Rank.EIGHT:
            score += 8
        elif card.rank == Rank.SEVEN:
            score += 7
        elif card.rank == Rank.SIX:
            score += 6
        elif card.rank == Rank.FIVE:
            score += 5
        elif card.rank == Rank.FOUR:
            score += 4
        elif card.rank == Rank.THREE:
            score += 3
        elif card.rank == Rank.TWO:
            score += 2
        elif card.rank == Rank.ACE:
            score += 1
        elif card.rank == Rank.JACK:
            score += 8  # Jacks are very good
        elif card.rank == Rank.KING:
            score += 7  # Kings are good
        elif card.rank == Rank.QUEEN:
            score += 3  # Queens are mediocre
    return score


def count_high_cards(hand):
    """Count cards with point value >= 7."""
    return sum(1 for c in hand if c.rank in [Rank.TEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN])


def count_royals(hand):
    """Count J, Q, K in hand."""
    return sum(1 for c in hand if c.rank in [Rank.JACK, Rank.QUEEN, Rank.KING])


def get_move_category(move):
    """Categorize a move."""
    match move:
        case PlayPoints(card=card):
            return f"PlayPoints_{card.rank.name}"
        case PlayPermanent(card=card):
            return f"PlayPermanent_{card.rank.name}"
        case PlayOneOff(card=card):
            return f"PlayOneOff_{card.rank.name}"
        case Scuttle():
            return "Scuttle"
        case Draw():
            return "Draw"
        case Counter():
            return "Counter"
        case DeclineCounter():
            return "DeclineCounter"
        case Discard():
            return "Discard"
        case Pass():
            return "Pass"
        case ResolveSeven():
            return "ResolveSeven"
        case _:
            return "Unknown"


def analyze_hand_context(num_games=5000):
    """Analyze hand quality when different moves are made."""

    # Track: move category -> list of (hand_quality, hand_size, high_cards, won)
    move_contexts = defaultdict(list)

    # Track: same card, different uses
    card_usage = defaultdict(lambda: {"points": [], "oneoff": [], "permanent": []})

    # Track: alternative moves available
    move_alternatives = defaultdict(lambda: {"had_better": 0, "no_better": 0, "won_had_better": 0, "won_no_better": 0})

    print(f"Analyzing {num_games} games for hand context...")

    for seed in range(num_games):
        if seed % 1000 == 0:
            print(f"  Progress: {seed}/{num_games}")

        state = create_initial_state(seed=seed)
        strategy = RandomStrategy(seed=seed * 2)

        moves_this_game = []  # (player, category, hand_quality, high_cards, hand_size)
        winner = None

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

            legal_moves = generate_legal_moves(state)
            if not legal_moves:
                break

            move = strategy.select_move(state, legal_moves)
            category = get_move_category(move)

            hand = state.players[acting].hand
            hq = hand_quality_score(hand)
            hc = count_high_cards(hand)
            hs = len(hand)

            moves_this_game.append((acting, category, hq, hc, hs, move, legal_moves))

            try:
                state = execute_move(state, move)
            except IllegalMoveError:
                break

            turn += 1

        winner = state.winner

        # Now record all moves with win/loss info
        for acting, category, hq, hc, hs, move, legal_moves in moves_this_game:
            won = (winner == acting)
            move_contexts[category].append({
                "hand_quality": hq,
                "hand_size": hs,
                "high_cards": hc,
                "won": won
            })

            # Track card-specific usage
            if isinstance(move, (PlayPoints, PlayOneOff, PlayPermanent)):
                card_rank = move.card.rank.name
                if isinstance(move, PlayPoints):
                    card_usage[card_rank]["points"].append({"hq": hq, "won": won})
                elif isinstance(move, PlayOneOff):
                    card_usage[card_rank]["oneoff"].append({"hq": hq, "won": won})
                elif isinstance(move, PlayPermanent):
                    card_usage[card_rank]["permanent"].append({"hq": hq, "won": won})

            # Track if better alternatives existed
            # "Better" = could have played a high point card for points
            could_play_high_points = any(
                isinstance(m, PlayPoints) and m.card.rank in [Rank.TEN, Rank.NINE, Rank.EIGHT]
                for m in legal_moves
            )

            is_suboptimal = category in ["PlayOneOff_NINE", "PlayOneOff_SIX", "PlayPermanent_QUEEN",
                                          "PlayPermanent_EIGHT", "PlayOneOff_THREE", "Draw"]

            if is_suboptimal:
                if could_play_high_points:
                    move_alternatives[category]["had_better"] += 1
                    if won:
                        move_alternatives[category]["won_had_better"] += 1
                else:
                    move_alternatives[category]["no_better"] += 1
                    if won:
                        move_alternatives[category]["won_no_better"] += 1

    # Print analysis
    print("\n" + "=" * 80)
    print("HAND QUALITY WHEN MAKING DIFFERENT MOVES")
    print("=" * 80)
    print(f"{'Move Category':<25} {'Avg Hand Q':>10} {'Avg Size':>10} {'High Cards':>10} {'Win Rate':>10} {'Count':>8}")
    print("-" * 80)

    sorted_cats = sorted(move_contexts.items(), key=lambda x: len(x[1]), reverse=True)
    for cat, contexts in sorted_cats:
        if len(contexts) >= 100:
            avg_hq = sum(c["hand_quality"] for c in contexts) / len(contexts)
            avg_size = sum(c["hand_size"] for c in contexts) / len(contexts)
            avg_hc = sum(c["high_cards"] for c in contexts) / len(contexts)
            win_rate = sum(1 for c in contexts if c["won"]) / len(contexts)
            print(f"{cat:<25} {avg_hq:>10.1f} {avg_size:>10.1f} {avg_hc:>10.2f} {win_rate:>10.1%} {len(contexts):>8}")

    print("\n" + "=" * 80)
    print("SAME CARD, DIFFERENT USES (Points vs One-Off)")
    print("=" * 80)
    print(f"{'Card':<10} {'As Points':>20} {'As One-Off':>20} {'Hand Q Diff':>12}")
    print(f"{'':10} {'Win% (n)':>20} {'Win% (n)':>20} {'':>12}")
    print("-" * 65)

    for rank in ["NINE", "SEVEN", "SIX", "FIVE", "FOUR", "THREE", "TWO", "ACE"]:
        points_data = card_usage[rank]["points"]
        oneoff_data = card_usage[rank]["oneoff"]

        if len(points_data) >= 50 and len(oneoff_data) >= 50:
            pts_win = sum(1 for d in points_data if d["won"]) / len(points_data)
            pts_hq = sum(d["hq"] for d in points_data) / len(points_data)

            oo_win = sum(1 for d in oneoff_data if d["won"]) / len(oneoff_data)
            oo_hq = sum(d["hq"] for d in oneoff_data) / len(oneoff_data)

            hq_diff = pts_hq - oo_hq

            print(f"{rank:<10} {pts_win:>6.1%} ({len(points_data):>5}) {oo_win:>11.1%} ({len(oneoff_data):>5}) {hq_diff:>+12.1f}")

    print("\n" + "=" * 80)
    print("DID PLAYERS HAVE BETTER OPTIONS?")
    print("(When making 'bad' moves, could they have played high points instead?)")
    print("=" * 80)
    print(f"{'Move':<25} {'Had Better':>15} {'Win%':>8} {'No Better':>15} {'Win%':>8}")
    print("-" * 75)

    for cat, data in sorted(move_alternatives.items(), key=lambda x: x[1]["had_better"] + x[1]["no_better"], reverse=True):
        hb = data["had_better"]
        nb = data["no_better"]
        if hb + nb >= 100:
            hb_win = data["won_had_better"] / hb if hb > 0 else 0
            nb_win = data["won_no_better"] / nb if nb > 0 else 0
            print(f"{cat:<25} {hb:>15} {hb_win:>8.1%} {nb:>15} {nb_win:>8.1%}")


if __name__ == "__main__":
    analyze_hand_context(5000)

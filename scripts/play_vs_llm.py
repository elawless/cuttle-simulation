#!/usr/bin/env python3
"""Play Cuttle against an LLM (Claude or GPT-4o).

The LLM is given the full rules, game state, and asked to choose a move.
"""

import os
import sys
import json

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on environment variables
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.cards import Rank, Suit
from strategies.heuristic import HeuristicStrategy


CUTTLE_RULES = """
# Cuttle Rules

Cuttle is a 2-player combat card game played with a standard 52-card deck.

## Objective
Be the first to reach 21 points (or lower if Kings are in play).

## Card Values for Points
- Ace = 1 point
- 2-10 = face value (2=2, 3=3, ..., 10=10)
- Face cards (J, Q, K) cannot be played for points

## On Your Turn
You may do ONE of the following:
1. **Draw** a card from the deck
2. **Play a card for points** (A-10 only) - place in your point pile
3. **Play a permanent** (J, Q, K, 8) - stays on field with ongoing effect
4. **Play a one-off** (A-7, 9) - immediate effect, then goes to scrap
5. **Scuttle** - use a point card from hand to destroy opponent's lower point card

## Permanent Effects
- **Jack**: Steal one of opponent's point cards (attach Jack to it)
- **Queen**: Protects you from opponent's targeted effects (2, 9, Jack)
- **King**: Reduces YOUR win threshold by 7 (21→14→7→0 with multiple Kings)
- **8**: "Glasses" - lets you see opponent's hand (weak effect)

## One-Off Effects
- **Ace**: Destroy ALL point cards on BOTH sides
- **2**: Destroy one of opponent's permanents (J, Q, K, 8)
- **3**: Revive a card from the scrap pile to your hand
- **4**: Opponent must discard 2 cards
- **5**: Draw 2 cards
- **6**: Destroy ALL permanents on BOTH sides
- **7**: Reveal top card of deck and play it immediately (free card!)
- **9**: Return one of opponent's permanents to their hand

## Scuttling
You can use a point card (A-10) from your hand to destroy an opponent's point card
of EQUAL OR LOWER value. Both cards go to scrap. (e.g., your 7 can scuttle their 7, 6, 5...)

## Countering
When opponent plays a one-off, you may play a 2 to counter it (cancel the effect).
They can counter your counter with another 2, etc.

## Winning
- Reach the point threshold (21, or less with Kings)
- Opponent cannot draw when deck is empty and has no cards in hand
"""


def format_card(card):
    """Format a card for display."""
    suit_symbols = {Suit.HEARTS: '♥', Suit.DIAMONDS: '♦', Suit.CLUBS: '♣', Suit.SPADES: '♠'}
    rank_names = {
        Rank.ACE: 'A', Rank.TWO: '2', Rank.THREE: '3', Rank.FOUR: '4',
        Rank.FIVE: '5', Rank.SIX: '6', Rank.SEVEN: '7', Rank.EIGHT: '8',
        Rank.NINE: '9', Rank.TEN: '10', Rank.JACK: 'J', Rank.QUEEN: 'Q', Rank.KING: 'K'
    }
    return f"{rank_names[card.rank]}{suit_symbols[card.suit]}"


def format_game_state(state, player, show_opponent_hand=False):
    """Format the game state for the LLM."""
    opponent = 1 - player

    lines = []
    lines.append(f"## Current Game State (You are Player {player})")
    lines.append("")

    # Point thresholds
    my_threshold = state.point_threshold(player)
    opp_threshold = state.point_threshold(opponent)
    lines.append(f"**Win Thresholds**: You need {my_threshold} points, Opponent needs {opp_threshold} points")
    lines.append("")

    # Your info
    lines.append(f"### Your Side (Player {player})")
    my_hand = [format_card(c) for c in state.players[player].hand]
    lines.append(f"- **Your Hand**: {', '.join(my_hand) if my_hand else '(empty)'}")

    my_points = [format_card(c) for c in state.players[player].points_field]
    my_point_total = state.players[player].point_total
    lines.append(f"- **Your Points**: {', '.join(my_points) if my_points else '(none)'} = {my_point_total} points")

    my_permanents = [format_card(c) for c in state.players[player].permanents]
    lines.append(f"- **Your Permanents**: {', '.join(my_permanents) if my_permanents else '(none)'}")

    if state.players[player].jacks:
        jacks = [f"{format_card(j)} stealing {format_card(s)}" for j, s in state.players[player].jacks]
        lines.append(f"- **Your Jacks**: {', '.join(jacks)}")

    lines.append("")

    # Opponent info
    lines.append(f"### Opponent's Side (Player {opponent})")
    if show_opponent_hand:
        opp_hand = [format_card(c) for c in state.players[opponent].hand]
        lines.append(f"- **Opponent's Hand**: {', '.join(opp_hand) if opp_hand else '(empty)'}")
    else:
        lines.append(f"- **Opponent's Hand**: {len(state.players[opponent].hand)} cards (hidden)")

    opp_points = [format_card(c) for c in state.players[opponent].points_field]
    opp_point_total = state.players[opponent].point_total
    lines.append(f"- **Opponent's Points**: {', '.join(opp_points) if opp_points else '(none)'} = {opp_point_total} points")

    opp_permanents = [format_card(c) for c in state.players[opponent].permanents]
    lines.append(f"- **Opponent's Permanents**: {', '.join(opp_permanents) if opp_permanents else '(none)'}")

    if state.players[opponent].jacks:
        jacks = [f"{format_card(j)} stealing {format_card(s)}" for j, s in state.players[opponent].jacks]
        lines.append(f"- **Opponent's Jacks**: {', '.join(jacks)}")

    lines.append("")
    lines.append(f"**Deck**: {len(state.deck)} cards remaining")
    lines.append(f"**Scrap pile**: {len(state.scrap)} cards")

    return "\n".join(lines)


def format_legal_moves(moves):
    """Format legal moves as numbered options."""
    lines = ["## Your Legal Moves", ""]

    for i, move in enumerate(moves, 1):
        lines.append(f"{i}. {move}")

    return "\n".join(lines)


def get_llm_move_claude(state, player, moves, api_key):
    """Get a move from Claude."""
    import anthropic

    # If no api_key provided, let SDK find it from environment/config
    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = anthropic.Anthropic()

    game_state = format_game_state(state, player)
    legal_moves = format_legal_moves(moves)

    prompt = f"""{CUTTLE_RULES}

{game_state}

{legal_moves}

Based on the rules and current game state, which move do you choose?

IMPORTANT: Respond with ONLY the number of your chosen move (e.g., "3"). No explanation needed."""

    # Use model from environment or default to sonnet
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    response = client.messages.create(
        model=model,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        choice = int(response.content[0].text.strip())
        if 1 <= choice <= len(moves):
            return moves[choice - 1], choice
    except (ValueError, IndexError):
        pass

    # If parsing failed, return first move
    print(f"  [LLM response couldn't be parsed: {response.content[0].text}]")
    return moves[0], 1


def get_llm_move_openai(state, player, moves, api_key):
    """Get a move from GPT-4o."""
    import openai

    client = openai.OpenAI(api_key=api_key)

    game_state = format_game_state(state, player)
    legal_moves = format_legal_moves(moves)

    prompt = f"""{CUTTLE_RULES}

{game_state}

{legal_moves}

Based on the rules and current game state, which move do you choose?

IMPORTANT: Respond with ONLY the number of your chosen move (e.g., "3"). No explanation needed."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        choice = int(response.choices[0].message.content.strip())
        if 1 <= choice <= len(moves):
            return moves[choice - 1], choice
    except (ValueError, IndexError):
        pass

    print(f"  [LLM response couldn't be parsed: {response.choices[0].message.content}]")
    return moves[0], 1


def play_game(llm_provider="claude", llm_player=1, seed=42, verbose=True):
    """Play a game between Heuristic and LLM.

    Args:
        llm_provider: "claude" or "openai"
        llm_player: Which player the LLM controls (0 or 1)
        seed: Random seed for game
        verbose: Print detailed output
    """
    # Get API key - try environment first, then let SDK handle defaults
    if llm_provider == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        # SDK will also check ~/.anthropic/api_key and other default locations
        get_llm_move = lambda s, p, m: get_llm_move_claude(s, p, m, api_key)
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("Error: OPENAI_API_KEY environment variable not set")
            sys.exit(1)
        get_llm_move = lambda s, p, m: get_llm_move_openai(s, p, m, api_key)

    heuristic = HeuristicStrategy(seed=seed)
    heuristic_player = 1 - llm_player

    state = create_initial_state(seed=seed)

    print("=" * 70)
    print(f"CUTTLE: Heuristic (P{heuristic_player}) vs {llm_provider.upper()} (P{llm_player})")
    print(f"Seed: {seed}")
    print("=" * 70)

    if verbose:
        print("\nInitial hands:")
        print(f"  P0: {', '.join(format_card(c) for c in state.players[0].hand)}")
        print(f"  P1: {', '.join(format_card(c) for c in state.players[1].hand)}")
        print()

    turn = 0
    while not state.is_game_over and turn < 200:
        # Determine acting player
        if state.phase == GamePhase.COUNTER:
            acting = state.counter_state.waiting_for_player
        elif state.phase == GamePhase.DISCARD_FOUR:
            acting = state.four_state.player
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            acting = state.seven_state.player
        else:
            acting = state.current_player

        moves = generate_legal_moves(state)
        if not moves:
            print("No legal moves - game stuck")
            break

        # Get move
        if acting == llm_player:
            player_name = llm_provider.upper()
            move, choice_num = get_llm_move(state, acting, moves)
        else:
            player_name = "Heuristic"
            move = heuristic.select_move(state, moves)
            choice_num = moves.index(move) + 1 if move in moves else "?"

        # Display
        p0_pts = state.players[0].point_total
        p1_pts = state.players[1].point_total

        if verbose:
            print(f"T{turn:02d} P{acting} ({player_name}): {str(move):<50} [{p0_pts}-{p1_pts}]")
            if acting == llm_player:
                print(f"     (chose option {choice_num} from {len(moves)} legal moves)")

        try:
            state = execute_move(state, move)
        except IllegalMoveError as e:
            print(f"  ERROR: {e}")
            break

        turn += 1

    # Game over
    print()
    print("=" * 70)
    print("GAME OVER")
    print("=" * 70)
    print(f"Winner: Player {state.winner} ({'Heuristic' if state.winner == heuristic_player else llm_provider.upper()})")
    print(f"Final score: {state.players[0].point_total} - {state.players[1].point_total}")
    print(f"Reason: {state.win_reason}")
    print(f"Turns: {turn}")

    return state.winner, heuristic_player, llm_player


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Play Cuttle: Heuristic vs LLM")
    parser.add_argument("--provider", choices=["claude", "openai"], default="claude",
                        help="LLM provider (default: claude)")
    parser.add_argument("--llm-player", type=int, choices=[0, 1], default=1,
                        help="Which player the LLM controls (default: 1)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--games", type=int, default=1,
                        help="Number of games to play (default: 1)")
    parser.add_argument("--quiet", action="store_true",
                        help="Less verbose output")

    args = parser.parse_args()

    results = {"heuristic": 0, "llm": 0}

    for i in range(args.games):
        if args.games > 1:
            print(f"\n{'='*70}")
            print(f"GAME {i+1} of {args.games}")
            print(f"{'='*70}\n")

        winner, heuristic_player, llm_player = play_game(
            llm_provider=args.provider,
            llm_player=args.llm_player,
            seed=args.seed + i,
            verbose=not args.quiet
        )

        if winner == heuristic_player:
            results["heuristic"] += 1
        else:
            results["llm"] += 1

    if args.games > 1:
        print(f"\n{'='*70}")
        print(f"FINAL RESULTS ({args.games} games)")
        print(f"{'='*70}")
        print(f"Heuristic: {results['heuristic']} wins")
        print(f"{args.provider.upper()}: {results['llm']} wins")


if __name__ == "__main__":
    main()

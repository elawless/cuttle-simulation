"""Legal move generation for Cuttle."""

from __future__ import annotations

from cuttle_engine.cards import Card, Rank
from cuttle_engine.moves import (
    Counter,
    DeclineCounter,
    Discard,
    Draw,
    Move,
    MoveType,
    OneOffEffect,
    Pass,
    PlayOneOff,
    PlayPermanent,
    PlayPoints,
    ResolveSeven,
    Scuttle,
)
from cuttle_engine.state import GamePhase, GameState


def generate_legal_moves(state: GameState) -> list[Move]:
    """Generate all legal moves for the current game state.

    Args:
        state: Current game state.

    Returns:
        List of all legal moves for the current player/phase.
    """
    if state.is_game_over:
        return []

    match state.phase:
        case GamePhase.MAIN:
            return _generate_main_phase_moves(state)
        case GamePhase.COUNTER:
            return _generate_counter_phase_moves(state)
        case GamePhase.RESOLVE_SEVEN:
            return _generate_seven_phase_moves(state)
        case GamePhase.DISCARD_FOUR:
            return _generate_discard_phase_moves(state)
        case GamePhase.GAME_OVER:
            return []

    return []


def _generate_main_phase_moves(state: GameState) -> list[Move]:
    """Generate moves for the main phase of a turn."""
    moves: list[Move] = []
    player = state.current_player_state
    opponent = state.opponent_state

    # Draw (if deck is not empty)
    if len(state.deck) > 0:
        moves.append(Draw())

    # Pass (only if deck is empty)
    if len(state.deck) == 0:
        moves.append(Pass())

    # For each card in hand, generate possible plays
    for card in player.hand:
        # Play for points (A-10)
        if card.can_play_for_points:
            moves.append(PlayPoints(card=card))

        # Scuttle opponent's point cards (A-10 can scuttle lower cards)
        if card.can_play_for_points:
            for target in _get_scuttleable_targets(opponent, card):
                moves.append(Scuttle(card=card, target=target))

        # One-off effects
        moves.extend(_generate_one_off_moves(state, card))

        # Permanent effects (8, J, Q, K)
        moves.extend(_generate_permanent_moves(state, card))

    return moves


def _get_scuttleable_targets(opponent: "PlayerState", card: Card) -> list[Card]:
    """Get opponent point cards that can be scuttled by the given card."""
    targets = []

    # Check opponent's direct point cards
    for target in opponent.points_field:
        if card.can_scuttle(target):
            # Check if target is protected by Queen
            if not _is_card_protected_by_queen(opponent, target):
                targets.append(target)

    # Check cards stolen by opponent's Jacks (these are also "their" points)
    for jack, stolen in opponent.jacks:
        if card.can_scuttle(stolen):
            if not _is_card_protected_by_queen(opponent, stolen):
                targets.append(stolen)

    return targets


def _is_card_protected_by_queen(player: "PlayerState", card: Card) -> bool:
    """Check if a card is protected by a Queen.

    In Cuttle, Queens protect all of a player's OTHER cards from being targeted.
    Point cards and other permanents are protected if the player has a Queen.
    """
    # Queens protect point cards and other permanents from targeting
    # But the Queen itself can still be targeted
    if card.rank == Rank.QUEEN:
        return False

    return player.queens_count > 0


def _generate_one_off_moves(state: GameState, card: Card) -> list[Move]:
    """Generate one-off moves for a card."""
    moves: list[Move] = []
    opponent = state.opponent_state

    if not card.can_play_as_one_off:
        return moves

    match card.rank:
        case Rank.ACE:
            # Scrap all point cards on the field (both players)
            # Only useful if there are point cards
            has_points = (
                len(state.players[0].points_field) > 0
                or len(state.players[1].points_field) > 0
                or len(state.players[0].jacks) > 0
                or len(state.players[1].jacks) > 0
            )
            if has_points:
                moves.append(
                    PlayOneOff(card=card, effect=OneOffEffect.ACE_SCRAP_ALL_POINTS)
                )

        case Rank.TWO:
            # Two as one-off: destroy a permanent (8, J, Q, K)
            for target in opponent.permanents:
                if not _is_card_protected_by_queen(opponent, target):
                    moves.append(
                        PlayOneOff(
                            card=card,
                            effect=OneOffEffect.TWO_DESTROY_PERMANENT,
                            target_card=target,
                            target_player=state.opponent,
                        )
                    )
            # Also can target Jacks (they are permanents)
            for jack, _ in opponent.jacks:
                if not _is_card_protected_by_queen(opponent, jack):
                    moves.append(
                        PlayOneOff(
                            card=card,
                            effect=OneOffEffect.TWO_DESTROY_PERMANENT,
                            target_card=jack,
                            target_player=state.opponent,
                        )
                    )

        case Rank.THREE:
            # Take any card from the scrap pile to hand
            for target in state.scrap:
                moves.append(
                    PlayOneOff(
                        card=card, effect=OneOffEffect.THREE_REVIVE, target_card=target
                    )
                )

        case Rank.FOUR:
            # Force opponent to discard 2 cards (if they have cards)
            if len(opponent.hand) > 0:
                moves.append(
                    PlayOneOff(
                        card=card,
                        effect=OneOffEffect.FOUR_DISCARD,
                        target_player=state.opponent,
                    )
                )

        case Rank.FIVE:
            # Draw 2 cards (if deck has cards)
            if len(state.deck) >= 1:  # At least 1 card to draw
                moves.append(PlayOneOff(card=card, effect=OneOffEffect.FIVE_DRAW_TWO))

        case Rank.SIX:
            # Scrap all permanents (both players)
            has_permanents = (
                len(state.players[0].permanents) > 0
                or len(state.players[1].permanents) > 0
                or len(state.players[0].jacks) > 0
                or len(state.players[1].jacks) > 0
            )
            if has_permanents:
                moves.append(
                    PlayOneOff(card=card, effect=OneOffEffect.SIX_SCRAP_ALL_PERMANENTS)
                )

        case Rank.SEVEN:
            # Play top card(s) of deck
            if len(state.deck) >= 1:
                moves.append(
                    PlayOneOff(card=card, effect=OneOffEffect.SEVEN_PLAY_FROM_DECK)
                )

        case Rank.NINE:
            # Return a permanent to its owner's hand
            # Can target opponent's permanents
            for target in opponent.permanents:
                if not _is_card_protected_by_queen(opponent, target):
                    moves.append(
                        PlayOneOff(
                            card=card,
                            effect=OneOffEffect.NINE_RETURN_PERMANENT,
                            target_card=target,
                            target_player=state.opponent,
                        )
                    )
            # Can also target opponent's Jacks
            for jack, _ in opponent.jacks:
                if not _is_card_protected_by_queen(opponent, jack):
                    moves.append(
                        PlayOneOff(
                            card=card,
                            effect=OneOffEffect.NINE_RETURN_PERMANENT,
                            target_card=jack,
                            target_player=state.opponent,
                        )
                    )
            # Can also target own permanents (strategic retreat)
            current = state.current_player_state
            for target in current.permanents:
                moves.append(
                    PlayOneOff(
                        card=card,
                        effect=OneOffEffect.NINE_RETURN_PERMANENT,
                        target_card=target,
                        target_player=state.current_player,
                    )
                )
            for jack, _ in current.jacks:
                moves.append(
                    PlayOneOff(
                        card=card,
                        effect=OneOffEffect.NINE_RETURN_PERMANENT,
                        target_card=jack,
                        target_player=state.current_player,
                    )
                )

    return moves


def _generate_permanent_moves(state: GameState, card: Card) -> list[Move]:
    """Generate permanent (8, J, Q, K) moves for a card."""
    moves: list[Move] = []
    opponent = state.opponent_state

    if not card.can_play_as_permanent:
        return moves

    match card.rank:
        case Rank.EIGHT:
            # Play as "glasses" - see opponent's hand
            moves.append(PlayPermanent(card=card))

        case Rank.JACK:
            # Steal an opponent's point card
            for target in opponent.points_field:
                if not _is_card_protected_by_queen(opponent, target):
                    moves.append(PlayPermanent(card=card, target_card=target))
            # Can also steal cards that opponent stole with their Jacks
            for _, stolen in opponent.jacks:
                if not _is_card_protected_by_queen(opponent, stolen):
                    moves.append(PlayPermanent(card=card, target_card=stolen))

        case Rank.QUEEN:
            # Play for protection
            moves.append(PlayPermanent(card=card))

        case Rank.KING:
            # Reduce win threshold
            moves.append(PlayPermanent(card=card))

    return moves


def _generate_counter_phase_moves(state: GameState) -> list[Move]:
    """Generate moves for the counter phase (can counter with Two or decline)."""
    moves: list[Move] = []

    if state.counter_state is None:
        return moves

    # Find whose turn it is to counter
    waiting_player = state.counter_state.waiting_for_player
    player_state = state.players[waiting_player]

    # Can counter with any Two in hand
    for card in player_state.hand:
        if card.rank == Rank.TWO:
            moves.append(Counter(card=card))

    # Can always decline to counter
    moves.append(DeclineCounter())

    return moves


def _generate_seven_phase_moves(state: GameState) -> list[Move]:
    """Generate moves for resolving a Seven (must play one of the revealed cards)."""
    moves: list[Move] = []

    if state.seven_state is None:
        return moves

    player = state.seven_state.player
    opponent_idx = 1 - player
    opponent = state.players[opponent_idx]

    for card in state.seven_state.revealed_cards:
        card_moves: list[Move] = []

        # Can play for points
        if card.can_play_for_points:
            card_moves.append(
                ResolveSeven(card=card, play_as=MoveType.PLAY_POINTS)
            )

            # Can scuttle
            for target in opponent.points_field:
                if card.can_scuttle(target):
                    if not _is_card_protected_by_queen(opponent, target):
                        card_moves.append(
                            ResolveSeven(
                                card=card,
                                play_as=MoveType.SCUTTLE,
                                target_card=target,
                            )
                        )

        # Can play as one-off (generates all valid one-off options)
        if card.can_play_as_one_off:
            one_off_moves = _generate_seven_one_off_options(state, card, player)
            card_moves.extend(one_off_moves)

        # Can play as permanent
        if card.can_play_as_permanent:
            perm_moves = _generate_seven_permanent_options(state, card, player)
            card_moves.extend(perm_moves)

        # If no valid plays for this card, it must be discarded to scrap
        # (e.g., Jack with no targets, Nine with no permanents)
        if not card_moves:
            card_moves.append(
                ResolveSeven(card=card, play_as=MoveType.DISCARD)
            )

        moves.extend(card_moves)

    return moves


def _generate_seven_one_off_options(
    state: GameState, card: Card, player: int
) -> list[ResolveSeven]:
    """Generate one-off options when playing from Seven."""
    moves: list[ResolveSeven] = []
    opponent_idx = 1 - player
    opponent = state.players[opponent_idx]
    current = state.players[player]

    match card.rank:
        case Rank.ACE:
            has_points = any(
                len(p.points_field) > 0 or len(p.jacks) > 0 for p in state.players
            )
            if has_points:
                moves.append(
                    ResolveSeven(card=card, play_as=MoveType.PLAY_ONE_OFF)
                )

        case Rank.TWO:
            # Destroy opponent's permanent
            for target in opponent.permanents:
                if not _is_card_protected_by_queen(opponent, target):
                    moves.append(
                        ResolveSeven(
                            card=card,
                            play_as=MoveType.PLAY_ONE_OFF,
                            target_card=target,
                        )
                    )
            for jack, _ in opponent.jacks:
                if not _is_card_protected_by_queen(opponent, jack):
                    moves.append(
                        ResolveSeven(
                            card=card,
                            play_as=MoveType.PLAY_ONE_OFF,
                            target_card=jack,
                        )
                    )

        case Rank.THREE:
            for target in state.scrap:
                moves.append(
                    ResolveSeven(
                        card=card, play_as=MoveType.PLAY_ONE_OFF, target_card=target
                    )
                )

        case Rank.FOUR:
            if len(opponent.hand) > 0:
                moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_ONE_OFF))

        case Rank.FIVE:
            if len(state.deck) >= 1:
                moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_ONE_OFF))

        case Rank.SIX:
            has_permanents = any(
                len(p.permanents) > 0 or len(p.jacks) > 0 for p in state.players
            )
            if has_permanents:
                moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_ONE_OFF))

        case Rank.SEVEN:
            # Seven from Seven - draw and play again
            if len(state.deck) >= 1:
                moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_ONE_OFF))

        case Rank.NINE:
            # Return a permanent to hand
            for target in opponent.permanents:
                if not _is_card_protected_by_queen(opponent, target):
                    moves.append(
                        ResolveSeven(
                            card=card,
                            play_as=MoveType.PLAY_ONE_OFF,
                            target_card=target,
                        )
                    )
            for jack, _ in opponent.jacks:
                if not _is_card_protected_by_queen(opponent, jack):
                    moves.append(
                        ResolveSeven(
                            card=card,
                            play_as=MoveType.PLAY_ONE_OFF,
                            target_card=jack,
                        )
                    )
            # Own permanents too
            for target in current.permanents:
                moves.append(
                    ResolveSeven(
                        card=card, play_as=MoveType.PLAY_ONE_OFF, target_card=target
                    )
                )
            for jack, _ in current.jacks:
                moves.append(
                    ResolveSeven(
                        card=card, play_as=MoveType.PLAY_ONE_OFF, target_card=jack
                    )
                )

    return moves


def _generate_seven_permanent_options(
    state: GameState, card: Card, player: int
) -> list[ResolveSeven]:
    """Generate permanent options when playing from Seven."""
    moves: list[ResolveSeven] = []
    opponent_idx = 1 - player
    opponent = state.players[opponent_idx]

    match card.rank:
        case Rank.EIGHT:
            moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_PERMANENT))

        case Rank.JACK:
            for target in opponent.points_field:
                if not _is_card_protected_by_queen(opponent, target):
                    moves.append(
                        ResolveSeven(
                            card=card,
                            play_as=MoveType.PLAY_PERMANENT,
                            target_card=target,
                        )
                    )
            for _, stolen in opponent.jacks:
                if not _is_card_protected_by_queen(opponent, stolen):
                    moves.append(
                        ResolveSeven(
                            card=card,
                            play_as=MoveType.PLAY_PERMANENT,
                            target_card=stolen,
                        )
                    )

        case Rank.QUEEN:
            moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_PERMANENT))

        case Rank.KING:
            moves.append(ResolveSeven(card=card, play_as=MoveType.PLAY_PERMANENT))

    return moves


def _generate_discard_phase_moves(state: GameState) -> list[Move]:
    """Generate moves for the discard phase (Four's effect)."""
    moves: list[Move] = []

    if state.four_state is None:
        return moves

    player_state = state.players[state.four_state.player]

    # Must discard any card from hand
    for card in player_state.hand:
        moves.append(Discard(card=card))

    return moves

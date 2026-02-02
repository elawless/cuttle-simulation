"""Move execution for Cuttle."""

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
from cuttle_engine.state import (
    CounterState,
    FourState,
    GamePhase,
    GameState,
    PlayerState,
    SevenState,
)


class IllegalMoveError(Exception):
    """Raised when an illegal move is attempted."""

    pass


def execute_move(state: GameState, move: Move) -> GameState:
    """Execute a move and return the new game state.

    Args:
        state: Current game state.
        move: Move to execute.

    Returns:
        New game state after the move.

    Raises:
        IllegalMoveError: If the move is not legal.
    """
    if state.is_game_over:
        raise IllegalMoveError("Game is already over")

    match move:
        case Draw():
            return _execute_draw(state)
        case PlayPoints():
            return _execute_play_points(state, move)
        case Scuttle():
            return _execute_scuttle(state, move)
        case PlayOneOff():
            return _execute_play_one_off(state, move)
        case PlayPermanent():
            return _execute_play_permanent(state, move)
        case Counter():
            return _execute_counter(state, move)
        case DeclineCounter():
            return _execute_decline_counter(state)
        case ResolveSeven():
            return _execute_resolve_seven(state, move)
        case Discard():
            return _execute_discard(state, move)
        case Pass():
            return _execute_pass(state)
        case _:
            raise IllegalMoveError(f"Unknown move type: {type(move)}")


def _execute_draw(state: GameState) -> GameState:
    """Execute a draw action."""
    if state.phase != GamePhase.MAIN:
        raise IllegalMoveError("Can only draw during main phase")
    if len(state.deck) == 0:
        raise IllegalMoveError("Deck is empty")

    # Draw top card from deck
    drawn_card = state.deck[0]
    new_deck = state.deck[1:]

    # Add to current player's hand
    player = state.current_player_state
    new_hand = player.hand + (drawn_card,)
    new_player = player.with_hand(new_hand)

    # Update players tuple
    players = list(state.players)
    players[state.current_player] = new_player
    new_players = (players[0], players[1])

    # End turn
    return _end_turn(
        state.with_players(new_players).with_deck(new_deck).with_consecutive_passes(0)
    )


def _execute_play_points(state: GameState, move: PlayPoints) -> GameState:
    """Execute playing a card for points."""
    if state.phase != GamePhase.MAIN:
        raise IllegalMoveError("Can only play for points during main phase")

    player = state.current_player_state
    if move.card not in player.hand:
        raise IllegalMoveError(f"Card {move.card} not in hand")
    if not move.card.can_play_for_points:
        raise IllegalMoveError(f"Card {move.card} cannot be played for points")

    # Remove from hand, add to points field
    new_hand = tuple(c for c in player.hand if c != move.card)
    new_points = player.points_field + (move.card,)
    new_player = player.with_hand(new_hand).with_points_field(new_points)

    # Update players
    players = list(state.players)
    players[state.current_player] = new_player
    new_state = state.with_players((players[0], players[1])).with_consecutive_passes(0)

    # Check for win
    new_state = _check_win(new_state)
    if new_state.is_game_over:
        return new_state

    return _end_turn(new_state)


def _execute_scuttle(state: GameState, move: Scuttle) -> GameState:
    """Execute scuttling an opponent's point card."""
    if state.phase != GamePhase.MAIN:
        raise IllegalMoveError("Can only scuttle during main phase")

    player = state.current_player_state
    opponent = state.opponent_state

    if move.card not in player.hand:
        raise IllegalMoveError(f"Card {move.card} not in hand")
    if not move.card.can_scuttle(move.target):
        raise IllegalMoveError(f"Card {move.card} cannot scuttle {move.target}")

    # Find target in opponent's field or jacks
    target_in_field = move.target in opponent.points_field
    target_in_jacks = any(stolen == move.target for _, stolen in opponent.jacks)

    if not target_in_field and not target_in_jacks:
        raise IllegalMoveError(f"Target {move.target} not in opponent's points")

    # Remove attacker from hand
    new_hand = tuple(c for c in player.hand if c != move.card)
    new_player = player.with_hand(new_hand)

    # Remove target from opponent
    if target_in_field:
        new_opponent_points = tuple(c for c in opponent.points_field if c != move.target)
        new_opponent = opponent.with_points_field(new_opponent_points)
    else:
        # Target was stolen by a Jack - remove the Jack and the stolen card
        new_jacks = tuple((j, s) for j, s in opponent.jacks if s != move.target)
        # Find which jack had this card
        jack_card = next(j for j, s in opponent.jacks if s == move.target)
        new_opponent = opponent.with_jacks(new_jacks)
        # Both Jack and stolen card go to scrap
        new_scrap = state.scrap + (move.card, move.target, jack_card)

        players = list(state.players)
        players[state.current_player] = new_player
        players[state.opponent] = new_opponent
        new_state = (
            state.with_players((players[0], players[1]))
            .with_scrap(new_scrap)
            .with_consecutive_passes(0)
        )
        return _end_turn(new_state)

    # Both cards go to scrap
    new_scrap = state.scrap + (move.card, move.target)

    players = list(state.players)
    players[state.current_player] = new_player
    players[state.opponent] = new_opponent
    new_state = (
        state.with_players((players[0], players[1]))
        .with_scrap(new_scrap)
        .with_consecutive_passes(0)
    )

    return _end_turn(new_state)


def _execute_play_one_off(state: GameState, move: PlayOneOff) -> GameState:
    """Execute playing a card as a one-off effect."""
    if state.phase != GamePhase.MAIN:
        raise IllegalMoveError("Can only play one-off during main phase")

    player = state.current_player_state
    if move.card not in player.hand:
        raise IllegalMoveError(f"Card {move.card} not in hand")

    # Remove card from hand
    new_hand = tuple(c for c in player.hand if c != move.card)
    new_player = player.with_hand(new_hand)

    players = list(state.players)
    players[state.current_player] = new_player

    # Create counter state (opponent can counter with Two)
    counter_state = CounterState(
        one_off_card=move.card,
        one_off_player=state.current_player,
        target_card=move.target_card,
        target_player=move.target_player,
    )

    new_state = (
        state.with_players((players[0], players[1]))
        .with_phase(GamePhase.COUNTER)
        .with_counter_state(counter_state)
        .with_consecutive_passes(0)
    )

    # Note: current_player doesn't change during counter phase
    # The counter_state tracks who should respond
    return new_state


def _execute_play_permanent(state: GameState, move: PlayPermanent) -> GameState:
    """Execute playing a permanent card (8, J, Q, K)."""
    if state.phase != GamePhase.MAIN:
        raise IllegalMoveError("Can only play permanent during main phase")

    player = state.current_player_state
    opponent = state.opponent_state

    if move.card not in player.hand:
        raise IllegalMoveError(f"Card {move.card} not in hand")

    # Remove from hand
    new_hand = tuple(c for c in player.hand if c != move.card)

    if move.card.rank == Rank.JACK:
        # Jack steals a point card
        if move.target_card is None:
            raise IllegalMoveError("Jack requires a target card")

        # Find and remove target from opponent
        target_in_field = move.target_card in opponent.points_field
        target_in_jacks = any(
            stolen == move.target_card for _, stolen in opponent.jacks
        )

        if not target_in_field and not target_in_jacks:
            raise IllegalMoveError(f"Target {move.target_card} not in opponent's points")

        if target_in_field:
            new_opponent_points = tuple(
                c for c in opponent.points_field if c != move.target_card
            )
            new_opponent = opponent.with_points_field(new_opponent_points)
        else:
            # Stealing from opponent's jack - remove their jack
            old_jack = next(j for j, s in opponent.jacks if s == move.target_card)
            new_opponent_jacks = tuple(
                (j, s) for j, s in opponent.jacks if s != move.target_card
            )
            new_opponent = opponent.with_jacks(new_opponent_jacks)
            # Old jack goes to scrap
            new_scrap = state.scrap + (old_jack,)
            state = state.with_scrap(new_scrap)

        # Add Jack and stolen card to our jacks
        new_jacks = player.jacks + ((move.card, move.target_card),)
        new_player = player.with_hand(new_hand).with_jacks(new_jacks)

        players = list(state.players)
        players[state.current_player] = new_player
        players[state.opponent] = new_opponent

    else:
        # 8, Q, K just add to permanents
        new_permanents = player.permanents + (move.card,)
        new_player = player.with_hand(new_hand).with_permanents(new_permanents)

        players = list(state.players)
        players[state.current_player] = new_player

    new_state = state.with_players((players[0], players[1])).with_consecutive_passes(0)

    # Check for win (King might lower threshold)
    new_state = _check_win(new_state)
    if new_state.is_game_over:
        return new_state

    return _end_turn(new_state)


def _execute_counter(state: GameState, move: Counter) -> GameState:
    """Execute countering with a Two."""
    if state.phase != GamePhase.COUNTER:
        raise IllegalMoveError("Can only counter during counter phase")
    if state.counter_state is None:
        raise IllegalMoveError("No counter state")

    waiting_player = state.counter_state.waiting_for_player
    player = state.players[waiting_player]

    if move.card not in player.hand:
        raise IllegalMoveError(f"Card {move.card} not in hand")
    if move.card.rank != Rank.TWO:
        raise IllegalMoveError("Can only counter with a Two")

    # Remove Two from hand
    new_hand = tuple(c for c in player.hand if c != move.card)
    new_player = player.with_hand(new_hand)

    players = list(state.players)
    players[waiting_player] = new_player

    # Add Two to counter chain
    new_chain = state.counter_state.counter_chain + (move.card,)
    new_counter_state = CounterState(
        one_off_card=state.counter_state.one_off_card,
        one_off_player=state.counter_state.one_off_player,
        target_card=state.counter_state.target_card,
        target_player=state.counter_state.target_player,
        counter_chain=new_chain,
    )

    # Stay in counter phase, but now the other player can counter
    return state.with_players((players[0], players[1])).with_counter_state(
        new_counter_state
    )


def _execute_decline_counter(state: GameState) -> GameState:
    """Execute declining to counter."""
    if state.phase != GamePhase.COUNTER:
        raise IllegalMoveError("Can only decline counter during counter phase")
    if state.counter_state is None:
        raise IllegalMoveError("No counter state")

    counter_state = state.counter_state

    # All counters and the original card go to scrap
    cards_to_scrap = [counter_state.one_off_card] + list(counter_state.counter_chain)
    new_scrap = state.scrap + tuple(cards_to_scrap)
    new_state = state.with_scrap(new_scrap)

    if counter_state.resolves:
        # Odd number of declines means effect happens
        new_state = _resolve_one_off(new_state, counter_state)
    # else: Even number of counters means effect is cancelled

    # Clear counter state and return to main phase (or handle phase transitions)
    new_state = new_state.with_counter_state(None)

    # If not in a special phase, end turn
    if new_state.phase == GamePhase.COUNTER:
        new_state = new_state.with_phase(GamePhase.MAIN)
        new_state = _check_win(new_state)
        if not new_state.is_game_over:
            new_state = _end_turn(new_state)

    return new_state


def _resolve_one_off(state: GameState, counter_state: CounterState) -> GameState:
    """Resolve a one-off effect."""
    card = counter_state.one_off_card
    caster = counter_state.one_off_player
    target_card = counter_state.target_card
    target_player = counter_state.target_player

    match card.rank:
        case Rank.ACE:
            return _resolve_ace(state)
        case Rank.TWO:
            return _resolve_two(state, target_card, target_player)
        case Rank.THREE:
            return _resolve_three(state, caster, target_card)
        case Rank.FOUR:
            return _resolve_four(state, target_player)
        case Rank.FIVE:
            return _resolve_five(state, caster)
        case Rank.SIX:
            return _resolve_six(state)
        case Rank.SEVEN:
            return _resolve_seven(state, caster)
        case Rank.NINE:
            return _resolve_nine(state, target_card, target_player)
        case _:
            raise IllegalMoveError(f"Invalid one-off card: {card}")


def _resolve_ace(state: GameState) -> GameState:
    """Ace: Scrap all point cards on the field."""
    cards_to_scrap: list[Card] = []
    new_players = list(state.players)

    for i in range(2):
        player = new_players[i]
        # Scrap all point cards
        cards_to_scrap.extend(player.points_field)
        # Scrap all jacks and stolen cards
        for jack, stolen in player.jacks:
            cards_to_scrap.append(jack)
            cards_to_scrap.append(stolen)

        new_players[i] = player.with_points_field(()).with_jacks(())

    new_scrap = state.scrap + tuple(cards_to_scrap)
    return state.with_players((new_players[0], new_players[1])).with_scrap(new_scrap)


def _resolve_two(
    state: GameState, target_card: Card | None, target_player: int | None
) -> GameState:
    """Two as one-off: Destroy target permanent."""
    if target_card is None or target_player is None:
        raise IllegalMoveError("Two requires a target")

    player = state.players[target_player]

    # Find and remove the target permanent
    if target_card in player.permanents:
        new_permanents = tuple(c for c in player.permanents if c != target_card)
        new_player = player.with_permanents(new_permanents)
    elif any(j == target_card for j, _ in player.jacks):
        # Removing a Jack - the stolen card goes to scrap too
        stolen = next(s for j, s in player.jacks if j == target_card)
        new_jacks = tuple((j, s) for j, s in player.jacks if j != target_card)
        new_player = player.with_jacks(new_jacks)
        new_scrap = state.scrap + (stolen,)
        state = state.with_scrap(new_scrap)
    else:
        raise IllegalMoveError(f"Target {target_card} not found")

    players = list(state.players)
    players[target_player] = new_player
    new_scrap = state.scrap + (target_card,)

    return state.with_players((players[0], players[1])).with_scrap(new_scrap)


def _resolve_three(state: GameState, caster: int, target_card: Card | None) -> GameState:
    """Three: Take a card from the scrap pile to hand."""
    if target_card is None:
        raise IllegalMoveError("Three requires a target card from scrap")
    if target_card not in state.scrap:
        raise IllegalMoveError(f"Card {target_card} not in scrap")

    # Remove from scrap, add to caster's hand
    new_scrap = tuple(c for c in state.scrap if c != target_card)
    player = state.players[caster]
    new_hand = player.hand + (target_card,)
    new_player = player.with_hand(new_hand)

    players = list(state.players)
    players[caster] = new_player

    return state.with_players((players[0], players[1])).with_scrap(new_scrap)


def _resolve_four(state: GameState, target_player: int | None) -> GameState:
    """Four: Opponent must discard 2 cards."""
    if target_player is None:
        raise IllegalMoveError("Four requires a target player")

    player = state.players[target_player]
    cards_to_discard = min(2, len(player.hand))

    if cards_to_discard == 0:
        # Nothing to discard
        return state

    # Enter discard phase
    four_state = FourState(player=target_player, cards_to_discard=cards_to_discard)
    return state.with_phase(GamePhase.DISCARD_FOUR).with_four_state(four_state)


def _resolve_five(state: GameState, caster: int) -> GameState:
    """Five: Draw 2 cards."""
    cards_to_draw = min(2, len(state.deck))

    if cards_to_draw == 0:
        return state

    drawn = state.deck[:cards_to_draw]
    new_deck = state.deck[cards_to_draw:]

    player = state.players[caster]
    new_hand = player.hand + drawn
    new_player = player.with_hand(new_hand)

    players = list(state.players)
    players[caster] = new_player

    return state.with_players((players[0], players[1])).with_deck(new_deck)


def _resolve_six(state: GameState) -> GameState:
    """Six: Scrap all permanents (both players)."""
    cards_to_scrap: list[Card] = []
    new_players = list(state.players)

    for i in range(2):
        player = new_players[i]
        # Scrap all permanents (8, Q, K)
        cards_to_scrap.extend(player.permanents)
        # Scrap all jacks and their stolen cards
        for jack, stolen in player.jacks:
            cards_to_scrap.append(jack)
            cards_to_scrap.append(stolen)

        new_players[i] = player.with_permanents(()).with_jacks(())

    new_scrap = state.scrap + tuple(cards_to_scrap)
    return state.with_players((new_players[0], new_players[1])).with_scrap(new_scrap)


def _resolve_seven(state: GameState, caster: int) -> GameState:
    """Seven: Reveal top card(s) and play one immediately."""
    if len(state.deck) == 0:
        raise IllegalMoveError("Deck is empty")

    # Reveal top 1 card (some variants reveal 2, but cuttle.cards reveals 1)
    revealed = (state.deck[0],)
    new_deck = state.deck[1:]

    seven_state = SevenState(revealed_cards=revealed, player=caster)
    return (
        state.with_deck(new_deck)
        .with_phase(GamePhase.RESOLVE_SEVEN)
        .with_seven_state(seven_state)
    )


def _resolve_nine(
    state: GameState, target_card: Card | None, target_player: int | None
) -> GameState:
    """Nine: Return target permanent to its owner's hand."""
    if target_card is None or target_player is None:
        raise IllegalMoveError("Nine requires a target")

    player = state.players[target_player]

    # Find and remove the target
    if target_card in player.permanents:
        new_permanents = tuple(c for c in player.permanents if c != target_card)
        new_hand = player.hand + (target_card,)
        new_player = player.with_permanents(new_permanents).with_hand(new_hand)
    elif any(j == target_card for j, _ in player.jacks):
        # Returning a Jack - stolen card goes back to original owner's points
        stolen = next(s for j, s in player.jacks if j == target_card)
        new_jacks = tuple((j, s) for j, s in player.jacks if j != target_card)
        new_hand = player.hand + (target_card,)
        new_player = player.with_jacks(new_jacks).with_hand(new_hand)

        # Return stolen card to opponent
        opponent_idx = 1 - target_player
        opponent = state.players[opponent_idx]
        new_opponent_points = opponent.points_field + (stolen,)
        new_opponent = opponent.with_points_field(new_opponent_points)

        players = list(state.players)
        players[target_player] = new_player
        players[opponent_idx] = new_opponent
        return state.with_players((players[0], players[1]))
    else:
        raise IllegalMoveError(f"Target {target_card} not found")

    players = list(state.players)
    players[target_player] = new_player
    return state.with_players((players[0], players[1]))


def _execute_resolve_seven(state: GameState, move: ResolveSeven) -> GameState:
    """Execute the resolution of a Seven."""
    if state.phase != GamePhase.RESOLVE_SEVEN:
        raise IllegalMoveError("Not in Seven resolution phase")
    if state.seven_state is None:
        raise IllegalMoveError("No Seven state")

    if move.card not in state.seven_state.revealed_cards:
        raise IllegalMoveError(f"Card {move.card} not in revealed cards")

    player_idx = state.seven_state.player
    opponent_idx = 1 - player_idx

    # Remove card from revealed (put other back on deck if any)
    other_cards = tuple(c for c in state.seven_state.revealed_cards if c != move.card)
    new_deck = other_cards + state.deck  # Put unused back on top

    # Clear seven state
    new_state = (
        state.with_deck(new_deck)
        .with_seven_state(None)
        .with_phase(GamePhase.MAIN)
        .with_current_player(player_idx)
    )

    # Now execute the chosen play
    match move.play_as:
        case MoveType.PLAY_POINTS:
            player = new_state.players[player_idx]
            new_points = player.points_field + (move.card,)
            new_player = player.with_points_field(new_points)
            players = list(new_state.players)
            players[player_idx] = new_player
            new_state = new_state.with_players((players[0], players[1]))

        case MoveType.SCUTTLE:
            if move.target_card is None:
                raise IllegalMoveError("Scuttle requires target")
            opponent = new_state.players[opponent_idx]

            if move.target_card in opponent.points_field:
                new_opponent_points = tuple(
                    c for c in opponent.points_field if c != move.target_card
                )
                new_opponent = opponent.with_points_field(new_opponent_points)
            else:
                raise IllegalMoveError("Target not found")

            new_scrap = new_state.scrap + (move.card, move.target_card)
            players = list(new_state.players)
            players[opponent_idx] = new_opponent
            new_state = new_state.with_players((players[0], players[1])).with_scrap(
                new_scrap
            )

        case MoveType.PLAY_ONE_OFF:
            # Trigger the one-off (may enter counter phase)
            effect = _determine_one_off_effect(move.card, move.target_card)
            counter_state = CounterState(
                one_off_card=move.card,
                one_off_player=player_idx,
                target_card=move.target_card,
                target_player=opponent_idx if move.target_card else None,
            )
            new_state = new_state.with_phase(GamePhase.COUNTER).with_counter_state(
                counter_state
            )
            return new_state

        case MoveType.PLAY_PERMANENT:
            if move.card.rank == Rank.JACK:
                if move.target_card is None:
                    raise IllegalMoveError("Jack requires target")
                opponent = new_state.players[opponent_idx]
                player = new_state.players[player_idx]

                if move.target_card in opponent.points_field:
                    new_opponent_points = tuple(
                        c for c in opponent.points_field if c != move.target_card
                    )
                    new_opponent = opponent.with_points_field(new_opponent_points)
                else:
                    raise IllegalMoveError("Target not found")

                new_jacks = player.jacks + ((move.card, move.target_card),)
                new_player = player.with_jacks(new_jacks)

                players = list(new_state.players)
                players[player_idx] = new_player
                players[opponent_idx] = new_opponent
                new_state = new_state.with_players((players[0], players[1]))
            else:
                player = new_state.players[player_idx]
                new_permanents = player.permanents + (move.card,)
                new_player = player.with_permanents(new_permanents)
                players = list(new_state.players)
                players[player_idx] = new_player
                new_state = new_state.with_players((players[0], players[1]))

    # Check win and end turn
    new_state = _check_win(new_state)
    if not new_state.is_game_over:
        new_state = _end_turn(new_state)

    return new_state


def _determine_one_off_effect(card: Card, target: Card | None) -> OneOffEffect:
    """Determine the one-off effect for a card."""
    match card.rank:
        case Rank.ACE:
            return OneOffEffect.ACE_SCRAP_ALL_POINTS
        case Rank.TWO:
            return OneOffEffect.TWO_DESTROY_PERMANENT
        case Rank.THREE:
            return OneOffEffect.THREE_REVIVE
        case Rank.FOUR:
            return OneOffEffect.FOUR_DISCARD
        case Rank.FIVE:
            return OneOffEffect.FIVE_DRAW_TWO
        case Rank.SIX:
            return OneOffEffect.SIX_SCRAP_ALL_PERMANENTS
        case Rank.SEVEN:
            return OneOffEffect.SEVEN_PLAY_FROM_DECK
        case Rank.NINE:
            return OneOffEffect.NINE_RETURN_PERMANENT
        case _:
            raise IllegalMoveError(f"Card {card} has no one-off effect")


def _execute_discard(state: GameState, move: Discard) -> GameState:
    """Execute discarding a card (Four's effect)."""
    if state.phase != GamePhase.DISCARD_FOUR:
        raise IllegalMoveError("Not in discard phase")
    if state.four_state is None:
        raise IllegalMoveError("No Four state")

    player_idx = state.four_state.player
    player = state.players[player_idx]

    if move.card not in player.hand:
        raise IllegalMoveError(f"Card {move.card} not in hand")

    # Remove from hand, add to scrap
    new_hand = tuple(c for c in player.hand if c != move.card)
    new_player = player.with_hand(new_hand)
    new_scrap = state.scrap + (move.card,)

    players = list(state.players)
    players[player_idx] = new_player

    remaining = state.four_state.cards_to_discard - 1

    if remaining > 0 and len(new_hand) > 0:
        # More cards to discard
        new_four_state = FourState(player=player_idx, cards_to_discard=remaining)
        return (
            state.with_players((players[0], players[1]))
            .with_scrap(new_scrap)
            .with_four_state(new_four_state)
        )
    else:
        # Done discarding, return to main phase and end turn
        new_state = (
            state.with_players((players[0], players[1]))
            .with_scrap(new_scrap)
            .with_four_state(None)
            .with_phase(GamePhase.MAIN)
        )
        new_state = _check_win(new_state)
        if not new_state.is_game_over:
            new_state = _end_turn(new_state)
        return new_state


def _execute_pass(state: GameState) -> GameState:
    """Execute passing the turn."""
    if state.phase != GamePhase.MAIN:
        raise IllegalMoveError("Can only pass during main phase")
    if len(state.deck) > 0:
        raise IllegalMoveError("Cannot pass when deck is not empty")

    new_passes = state.consecutive_passes + 1

    # Check for stalemate (both players pass consecutively)
    if new_passes >= 2:
        # Game ends - player with more points wins
        p0_points = state.players[0].point_total
        p1_points = state.players[1].point_total
        if p0_points > p1_points:
            from cuttle_engine.state import WinReason

            return state.with_winner(0, WinReason.EMPTY_DECK_POINTS)
        elif p1_points > p0_points:
            from cuttle_engine.state import WinReason

            return state.with_winner(1, WinReason.EMPTY_DECK_POINTS)
        # Tie - game continues? Or draw? For now continue
        # Actually in cuttle, if both pass consecutively it's a draw or continue
        # Let's say game continues (reset passes)
        new_passes = 0

    return _end_turn(state.with_consecutive_passes(new_passes))


def _end_turn(state: GameState) -> GameState:
    """End the current turn and switch to the other player."""
    new_turn = state.turn_number + 1 if state.current_player == 1 else state.turn_number
    return state.with_current_player(state.opponent).with_turn_number(new_turn)


def _check_win(state: GameState) -> GameState:
    """Check if someone has won and update state accordingly."""
    winner, reason = state.check_winner()
    if winner is not None:
        return state.with_winner(winner, reason)
    return state

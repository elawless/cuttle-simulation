/**
 * Type definitions for the Cuttle game.
 */

export interface Card {
	rank: number;
	rank_symbol: string;
	rank_name: string;
	suit: number;
	suit_symbol: string;
	suit_name: string;
	display: string;
	point_value: number;
	hidden?: boolean;
}

export interface JackPair {
	jack: Card;
	stolen: Card;
}

export interface Player {
	index: number;
	hand: Card[];
	hand_count: number;
	points_field: Card[];
	permanents: Card[];
	jacks: JackPair[];
	point_total: number;
	point_threshold: number;
	queens_count: number;
	kings_count: number;
}

export interface CounterState {
	one_off_card: Card;
	one_off_player: number;
	target_card: Card | null;
	counter_chain: Card[];
	waiting_for_player: number;
	resolves: boolean;
}

export interface SevenState {
	revealed_cards: Card[];
	player: number;
}

export interface FourState {
	player: number;
	cards_to_discard: number;
}

export interface GameState {
	game_id: string;
	phase: string;
	current_player: number;
	turn_number: number;
	deck_count: number;
	scrap: Card[];
	winner: number | null;
	win_reason: string | null;
	acting_player: number;
	players: Player[];
	counter_state: CounterState | null;
	seven_state: SevenState | null;
	four_state: FourState | null;
}

export interface Move {
	index: number;
	type: string;
	description: string;
	card?: Card;
	target?: Card;
	effect?: string;
	target_player?: number;
	play_as?: string;
}

export interface LLMThinking {
	prompt: string;
	response: string;
	model: string;
	chosen_move_index: number;
	chosen_move_description: string;
	error: string | null;
}

export interface MoveRecord {
	turn: number;
	player: number;
	move: string;
	move_type: string;
	timestamp: string;
	llm_thinking?: LLMThinking;
	hands_before?: string[][];
	hands_after?: string[][];
	points_after?: number[];
}

export interface GameResponse {
	state: GameState;
	legal_moves: Move[];
	is_human_turn: boolean;
	move_history?: MoveRecord[];
}

export interface Strategy {
	name: string;
	description: string;
}

export type GamePhase =
	| 'MAIN'
	| 'COUNTER'
	| 'RESOLVE_SEVEN'
	| 'DISCARD_FOUR'
	| 'GAME_OVER';

export type Suit = 'CLUBS' | 'DIAMONDS' | 'HEARTS' | 'SPADES';
export type SuitSymbol = '♣' | '♦' | '♥' | '♠';

export const SUIT_COLORS: Record<string, string> = {
	CLUBS: '#1a1a1a',
	DIAMONDS: '#dc2626',
	HEARTS: '#dc2626',
	SPADES: '#1a1a1a'
};

export function getSuitColor(suitName: string): string {
	return SUIT_COLORS[suitName] || '#1a1a1a';
}

export function isRedSuit(suitName: string): boolean {
	return suitName === 'HEARTS' || suitName === 'DIAMONDS';
}

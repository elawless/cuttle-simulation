"""Game strategies for Cuttle."""

from strategies.base import Strategy
from strategies.heuristic import HeuristicStrategy
from strategies.random_strategy import RandomStrategy

__all__ = ["Strategy", "RandomStrategy", "HeuristicStrategy"]

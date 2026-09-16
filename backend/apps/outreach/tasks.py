"""Celery autodiscovery entry point for explicit bid-extraction proposals."""

from .bid_extraction import process_bid_extraction

__all__ = ["process_bid_extraction"]

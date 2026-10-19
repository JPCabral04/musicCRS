"""Retrieval package for the MusicCRS group project.

Provides a data loader for the track metadata catalog and retrieval
modules that map a natural language query to a ranked list of track IDs.
Adapted from the RecSys 2026 MusicCRS challenge baselines.
"""
from .base import RetrievalModule
from .data_loader import MusicCatalogLoader
from .methods.bm25 import BM25Retriever

__all__ = ["RetrievalModule", "MusicCatalogLoader", "BM25Retriever"]

"""Shared helpers for the read layer."""
from db.session import get_engine


def ten(v, dp: int = 1):
    """Boundary transform: internal 0-1 scores leave the API on the
    10-point display scale (pipeline.tiers.fmt10 convention), as numbers.
    None passes through so 'no data' stays distinguishable from 0."""
    if v is None:
        return None
    return round(float(v) * 10, dp)

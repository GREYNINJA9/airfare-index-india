"""Dashboard Heatmap Module.

Formats sector-wise matrix data and color scales for the interactive dashboard.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.api.analytics import sector_heatmap


def get_heatmap_matrix() -> Dict[str, Any]:
    """Return structured sector matrix ready for UI table and heatmap rendering."""
    cells = sector_heatmap()

    origins = sorted({c.origin for c in cells})
    destinations = sorted({c.destination for c in cells})

    matrix: Dict[str, Dict[str, Any]] = {}
    for orig in origins:
        matrix[orig] = {}
        for dest in destinations:
            matrix[orig][dest] = None

    for c in cells:
        matrix[c.origin][c.destination] = {
            "sector": c.sector,
            "current_median_inr": c.current_median_inr,
            "price_relative": c.price_relative,
            "change_24h_pct": c.change_24h_pct,
            "change_7d_pct": c.change_7d_pct,
            "observation_count": c.observation_count,
            "heat_intensity": c.heat_intensity,
        }

    return {
        "origins": origins,
        "destinations": destinations,
        "matrix": matrix,
        "cells": [c.model_dump() for c in cells],
    }

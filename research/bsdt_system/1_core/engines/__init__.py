"""Three integration engines, sharing the same Φ + control law.

Gravity   — first-order overdamped:   Ẋ = F   (or controlled F − γ*⟨F,u⟩u)
Molecular — second-order Langevin:    M Ẍ = F − ζ Ẋ + σ_n √(2ζkT) ξ
Hybrid    — gravity field + short-range Lennard-Jones repulsion + BSDT control
"""
from .gravity import Gravity
from .molecular import Molecular
from .hybrid import Hybrid
from .diagnostics import engine_diagnostics

__all__ = ["Gravity", "Molecular", "Hybrid", "engine_diagnostics"]

"""Generic Product layer.

This layer contains reusable interlocking logic independent from one station
layout or one country-specific operating profile.
"""

from .kernel import GenericProductKernel, ProductRules

__all__ = ["GenericProductKernel", "ProductRules"]

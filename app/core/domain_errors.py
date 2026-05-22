from __future__ import annotations


class DomainError(Exception):
    """Base class for expected business-level errors."""


class RecommendationInputError(DomainError):
    """Invalid recommendation input payload (business validation error)."""


class DataNotFoundWarning(DomainError):
    """Expected data was not found (business warning case)."""



class AnalysisReportNotFoundError(DataNotFoundWarning):
    """No suitable analysis report found for recommendation build."""

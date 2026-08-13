class KnowledgeDependencyError(ImportError):
    """Raised when the optional knowledge dependencies are unavailable."""


class KnowledgeIndexNotConfigured(RuntimeError):
    """Raised when an indexing endpoint has no configured knowledge service."""

class ArctusError(Exception):
    """Base Arctus exception."""

class TwinSyncError(ArctusError):
    """State synchronization failure."""

class GraphConsistencyError(ArctusError):
    """Graph invariant violation."""

class PredictionError(ArctusError):
    """Prediction engine failure."""

class ValidationError(ArctusError):
    """Event or model validation failure."""

class ConfigError(ArctusError):
    """Configuration error."""

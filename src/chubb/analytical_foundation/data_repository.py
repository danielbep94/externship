"""
Analytical Foundation — Data Repository Interface.
Decouples analytical calculations from underlying storage (JSON today, Delta/Unity Catalog in Databricks tomorrow).
"""

from typing import Dict, List, Any, Protocol, runtime_checkable


@runtime_checkable
class DataRepository(Protocol):
    """Abstract protocol for reading curated actuarial data."""

    def get_dataset(self) -> Dict[str, Any]:
        """Returns the full validated dataset dictionary."""
        ...

    def get_metadata(self) -> Dict[str, Any]:
        """Returns the dataset metadata dictionary."""
        ...

    def get_states(self) -> List[Dict[str, Any]]:
        """Returns the list of state records."""
        ...

    def get_scatter_stats(self) -> Dict[str, Any]:
        """Returns the OLS regression and correlation statistics."""
        ...


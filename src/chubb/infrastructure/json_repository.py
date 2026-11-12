"""
Infrastructure Layer — JSON Data Repository Implementation.
Loads and validates the curated JSON dataset through ActuarialDataValidator.
"""

from typing import Dict, List, Any
from chubb.infrastructure.paths import resolve_data_path
from chubb.validation_foundation.data_validator import ActuarialDataValidator


class JsonDataRepository:
    """Concrete JSON DataRepository backed by data/curated/data.json."""

    def __init__(self, data_path: str = "", allow_synthetic: bool = False):
        self.data_path = resolve_data_path(data_path)
        self._data = ActuarialDataValidator.load_and_validate(
            self.data_path, allow_synthetic=allow_synthetic
        )

    def get_dataset(self) -> Dict[str, Any]:
        return self._data

    def get_metadata(self) -> Dict[str, Any]:
        return self._data["metadata"]

    def get_states(self) -> List[Dict[str, Any]]:
        return self._data["estados"]

    def get_scatter_stats(self) -> Dict[str, Any]:
        return self._data["scatter_stats"]


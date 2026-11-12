"""
Infrastructure Layer for CHUBB Actuarial Analytics.
Provides file system path resolution and concrete JSON data repository adapters.
"""

from chubb.infrastructure.paths import (
    REPO_ROOT,
    SRC_DIR,
    APP_DIR,
    CONFIG_DIR,
    DATA_DIR,
    OUTPUT_DIR,
    CURATED_DATA_PATH,
    ACTUARIAL_RULES_PATH,
    resolve_data_path,
    resolve_rules_path,
)

__all__ = [
    "REPO_ROOT",
    "SRC_DIR",
    "APP_DIR",
    "CONFIG_DIR",
    "DATA_DIR",
    "OUTPUT_DIR",
    "CURATED_DATA_PATH",
    "ACTUARIAL_RULES_PATH",
    "resolve_data_path",
    "resolve_rules_path",
]


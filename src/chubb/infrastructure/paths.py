"""
Centralized Path Resolution for CHUBB Modular Architecture.
Resolves canonical paths under data/, config/, app/, and output/ with automatic
fallback to legacy root-level paths for backward compatibility.
"""

import os
from pathlib import Path

# src/chubb/infrastructure/paths.py -> parents[3] is repository root (/Users/victordaniel/chubb)
PACKAGE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = PACKAGE_DIR.parent
REPO_ROOT = SRC_DIR.parent

APP_DIR = REPO_ROOT / "app"
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
DOCS_DIR = REPO_ROOT / "docs"

SEMANTIC_CONFIG_DIR = CONFIG_DIR / "semantic"
BUSINESS_RULES_DIR = CONFIG_DIR / "business_rules"

CURATED_DATA_PATH = DATA_DIR / "curated" / "data.json"
LEGACY_DATA_PATH = REPO_ROOT / "data.json"

RAW_BASELINE_CSV_PATH = DATA_DIR / "raw" / "baseline_siniestros.csv"
RAW_GEOJSON_PATH = DATA_DIR / "raw" / "mexico_estados.geojson"
LEGACY_GEOJSON_PATH = DATA_DIR / "mexico_estados.geojson"

DATA_SCHEMA_PATH = DATA_DIR / "schemas" / "actuarial_data.schema.json"

ACTUARIAL_RULES_PATH = BUSINESS_RULES_DIR / "actuarial_rules.json"
LEGACY_RULES_PATH = CONFIG_DIR / "actuarial_rules.json"


def resolve_data_path(custom_path: str = "") -> str:
    """Returns the active data.json path (env override -> custom_path -> data/curated/data.json -> root data.json)."""
    if custom_path and os.path.exists(custom_path):
        return str(Path(custom_path).resolve())
    env_path = os.environ.get("CHUBB_DATA_PATH")
    if env_path and os.path.exists(env_path):
        return str(Path(env_path).resolve())
    if CURATED_DATA_PATH.exists():
        return str(CURATED_DATA_PATH)
    return str(LEGACY_DATA_PATH)


def resolve_rules_path(custom_path: str = "") -> str:
    """Returns the active actuarial_rules.json path (custom_path -> config/business_rules/actuarial_rules.json -> config/actuarial_rules.json)."""
    if custom_path and os.path.exists(custom_path):
        return str(Path(custom_path).resolve())
    env_path = os.environ.get("CHUBB_RULES_PATH")
    if env_path and os.path.exists(env_path):
        return str(Path(env_path).resolve())
    if ACTUARIAL_RULES_PATH.exists():
        return str(ACTUARIAL_RULES_PATH)
    return str(LEGACY_RULES_PATH)


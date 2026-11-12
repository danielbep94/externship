#!/usr/bin/env python3
"""
Automated Quality Gates Runner (QG-01 through QG-08) for CHUBB Modular Architecture.
Verifies:
- QG-01: Data & Config SHA-256 parity and ActuarialDataValidator schema check.
- QG-02: AST Architectural Boundary Audit (zero prohibited cross-Foundation imports).
- QG-03: Backward-Compatibility Facade symbol verification.
- QG-04: Unit, Integration, Golden & Adversarial test suite execution.
- QG-05: Canonical Output Audit (src/validate_assistant_outputs.py).
- QG-06: Python-JavaScript Mathematical Parity (node tests/parity/test_parity.mjs).
- QG-07: 10K Independent Oracle Benchmark (tests/performance/benchmark_10k/run_benchmark_10k.py).
- QG-08: Modular HTTP Server routing & Path Traversal protection check.
"""

import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SRC_DIR))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_qg01_data_and_config() -> bool:
    from chubb.validation_foundation import ActuarialDataValidator

    curated = REPO_ROOT / "data" / "curated" / "data.json"
    legacy_data = REPO_ROOT / "data.json"
    rules_mod = REPO_ROOT / "config" / "business_rules" / "actuarial_rules.json"
    rules_leg = REPO_ROOT / "config" / "actuarial_rules.json"

    if not curated.exists() or not rules_mod.exists():
        print("[FAIL QG-01] Missing curated data.json or business_rules/actuarial_rules.json")
        return False

    if sha256_file(curated) != sha256_file(legacy_data):
        print("[FAIL QG-01] SHA-256 mismatch between data/curated/data.json and root data.json")
        return False

    if sha256_file(rules_mod) != sha256_file(rules_leg):
        print("[FAIL QG-01] SHA-256 mismatch between config/business_rules/actuarial_rules.json and config/actuarial_rules.json")
        return False

    ActuarialDataValidator.load_and_validate(str(curated))
    print(f"[✅ PASS] QG-01 | Data & Config Integrity (SHA-256 verified: {sha256_file(curated)[:12]}...)")
    return True


def check_qg02_architectural_boundaries() -> bool:
    prohibited_rules = {
        "semantic_foundation": {"analytical_foundation", "validation_foundation", "conversational_ai"},
        "analytical_foundation": {"validation_foundation", "conversational_ai"},
        "validation_foundation": {"conversational_ai"},
        "contracts": {"semantic_foundation", "analytical_foundation", "validation_foundation", "conversational_ai", "infrastructure"},
    }

    chubb_dir = SRC_DIR / "chubb"
    violations = []

    for foundation, forbidden_targets in prohibited_rules.items():
        f_dir = chubb_dir / foundation
        for py_file in f_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                imported_mods = []
                if isinstance(node, ast.Import):
                    imported_mods.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_mods.append(node.module)
                for mod in imported_mods:
                    for forbidden in forbidden_targets:
                        if forbidden in mod:
                            violations.append(f"{py_file.relative_to(REPO_ROOT)} imports '{mod}' (prohibited in {foundation})")

    if violations:
        for v in violations:
            print(f"[FAIL QG-02] {v}")
        return False

    print("[✅ PASS] QG-02 | Architectural Boundary & AST Import Audit (0 prohibited dependencies)")
    return True


def check_qg03_compatibility_facades() -> bool:
    import actuarial_core
    import llm_grounding
    import ai_assistant_llm

    required_core = [
        "ActuarialDataValidator",
        "ActuarialCatalog",
        "ConversationMemoryManager",
        "ActuarialOperationsEngine",
        "format_number",
        "normalize_text",
    ]
    required_grounding = [
        "GroundedActuarialAssistant",
        "ActuarialQueryParser",
        "ActuarialOutputVerifier",
        "HallucinationDetectedError",
        "LabelSwapDetectedError",
    ]
    for sym in required_core:
        if not hasattr(actuarial_core, sym):
            print(f"[FAIL QG-03] Missing symbol {sym} in actuarial_core facade")
            return False
    for sym in required_grounding:
        if not hasattr(llm_grounding, sym):
            print(f"[FAIL QG-03] Missing symbol {sym} in llm_grounding facade")
            return False
    if not hasattr(ai_assistant_llm, "LlamaColabDataAgent"):
        print("[FAIL QG-03] Missing LlamaColabDataAgent in ai_assistant_llm facade")
        return False

    print("[✅ PASS] QG-03 | Backward-Compatibility Facades (actuarial_core, llm_grounding, ai_assistant_llm)")
    return True


def run_cmd_gate(gate_id: str, label: str, cmd: list) -> bool:
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[FAIL {gate_id}] {label}\n{res.stdout}\n{res.stderr}")
        return False
    print(f"[✅ PASS] {gate_id} | {label}")
    return True


def check_qg08_dev_server_routing() -> bool:
    import scripts.dev_server as ds

    handler = ds.ModularNoCacheHTTPRequestHandler.__new__(ds.ModularNoCacheHTTPRequestHandler)
    p_index = Path(handler.translate_path("/index.html"))
    p_data = Path(handler.translate_path("/data.json"))
    p_geo = Path(handler.translate_path("/data/mexico_estados.geojson"))
    p_js = Path(handler.translate_path("/js/actuarial_engine.js"))
    p_traversal = Path(handler.translate_path("/../../../../etc/passwd"))

    if not (p_index.exists() and p_data.exists() and p_geo.exists() and p_js.exists()):
        print("[FAIL QG-08] Dev server failed to resolve one or more canonical frontend/data routes")
        return False
    if str(p_traversal) == "/etc/passwd":
        print("[FAIL QG-08] Path traversal not blocked")
        return False

    print("[✅ PASS] QG-08 | Modular HTTP Server Routing & Path Traversal Protection")
    return True


def main() -> int:
    print("=" * 82)
    print("🛡️  CHUBB MODULAR ARCHITECTURE — AUTOMATED QUALITY GATES (QG-01 .. QG-08)")
    print("=" * 82)
    gates = [
        check_qg01_data_and_config(),
        check_qg02_architectural_boundaries(),
        check_qg03_compatibility_facades(),
        run_cmd_gate("QG-04", "Unit, Integration, Golden & Adversarial Tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        run_cmd_gate("QG-05", "Canonical Output Audit (13/13 checks)", [sys.executable, "src/validate_assistant_outputs.py"]),
        run_cmd_gate("QG-06", "Python–JavaScript Mathematical Parity (35/35 vectors)", ["node", "tests/parity/test_parity.mjs"]),
        run_cmd_gate("QG-07", "10K Independent Oracle Benchmark (10,000 queries, 0 S0 errors)", [sys.executable, "tests/performance/benchmark_10k/run_benchmark_10k.py"]),
        check_qg08_dev_server_routing(),
    ]
    print("=" * 82)
    passed = sum(1 for g in gates if g)
    print(f"RESULTADO FINAL DE QUALITY GATES: {passed}/{len(gates)} APROBADOS")
    print("=" * 82)
    return 0 if all(gates) else 1


if __name__ == "__main__":
    sys.exit(main())

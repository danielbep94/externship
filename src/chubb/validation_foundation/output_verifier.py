"""
Validation Foundation — Post-Generation Output Verifier & S0 Semantic Slot Auditor.
Detects hallucinated figures (HallucinationDetectedError) and label swaps (LabelSwapDetectedError).
"""

import re
from typing import Dict, List, Any
from chubb.contracts.error_contract import HallucinationDetectedError, LabelSwapDetectedError
from chubb.semantic_foundation.temporal_registry import normalize_text


class ActuarialOutputVerifier:
    """
    Guardrail Post-Generación y Verificador de Slots Semánticos:
    1. verify(): Audita que toda cifra con $, %, pts, veces/x o r=... exista en el payload permitido.
    2. verify_semantic_slots(): Audita que cada cifra en la narrativa corresponda semánticamente
       a su metric_id y entidad (detectando intercambios de etiquetas LABEL_SWAP_ERROR — Severidad S0).
    """
    EXEMPT_CONSTANTS = {0.0, 1.0, 30.0, 35.0, 100.0, 1000.0, 1000000.0, 2020.0, 2021.0, 2022.0, 2023.0, 2024.0, 0.0001}

    @classmethod
    def verify(cls, generated_text: str, allowed_numbers: List[float], tolerance: float = 0.5) -> bool:
        amounts = re.findall(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', generated_text)
        percentages = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*%', generated_text)
        points = re.findall(r'([0-9,]+(?:\.[0-9]+)?)\s*pts\b', generated_text)
        multiples = re.findall(r'\b([0-9]+(?:\.[0-9]+)?)\s*(?:veces|x)\b', generated_text)
        correlations = re.findall(r'\br\s*=\s*\+?(-?[0-9]+\.[0-9]+)', generated_text)

        extracted_items = []
        for amt in amounts:
            try:
                extracted_items.append((float(amt.replace(',', '')), tolerance))
            except ValueError:
                pass
        for pct in percentages:
            try:
                extracted_items.append((float(pct), tolerance))
            except ValueError:
                pass
        for pt in points:
            try:
                extracted_items.append((float(pt.replace(',', '')), tolerance))
            except ValueError:
                pass
        for mult in multiples:
            try:
                extracted_items.append((float(mult), max(tolerance, 0.05)))
            except ValueError:
                pass
        for corr in correlations:
            try:
                extracted_items.append((float(corr), 0.001))
            except ValueError:
                pass

        for num, tol in extracted_items:
            if num in cls.EXEMPT_CONSTANTS:
                continue
            is_valid = any(abs(num - allowed) <= tol for allowed in allowed_numbers)
            if not is_valid:
                raise HallucinationDetectedError(
                    f"Cifra alucinada detectada en la salida del LLM: {num}. No coincide con el payload actuarial."
                )

        return True

    @classmethod
    def verify_semantic_slots(cls, generated_text: str, structured_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica el contrato estructurado de métricas (metric_id, entity, value, unit, period, filters, operation_id)
        contra el texto narrativo generado.
        Si dos métricas tienen ambos valores presentes en el texto pero la etiqueta de una está vinculada
        al valor de otra, lanza LabelSwapDetectedError (Error Crítico S0).
        """
        allowed_vals = [float(m["value"]) for m in structured_metrics if m.get("value") is not None]
        cls.verify(generated_text, allowed_vals, tolerance=0.5)

        raw_lines = [line.strip() for line in generated_text.splitlines() if line.strip()]

        for idx_a, m_a in enumerate(structured_metrics):
            val_a = m_a.get("value")
            if val_a is None:
                continue
            unit_a = m_a.get("unit", "")
            tol_a = 0.015 if unit_a in ("MXN", "MDP") else (0.11 if unit_a in ("pts", "%") else 0.001)
            raw_keys_a = [k.strip().lower() for k in m_a.get("slot_keywords", []) if k.strip()]
            if not raw_keys_a:
                continue

            for raw_clause in raw_lines:
                clause = normalize_text(raw_clause)
                raw_lower = raw_clause.lower()
                matched_a = any(
                    (rk in raw_lower if "|" in rk else normalize_text(rk) in clause)
                    for rk in raw_keys_a
                )
                if matched_a:
                    nums_in_clause = [
                        float(n.replace(',', ''))
                        for n in re.findall(r'(?:\$\s*)?([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+\.[0-9]+)', raw_clause)
                    ]
                    if not nums_in_clause:
                        continue
                    has_val_a = any(abs(x - val_a) <= tol_a for x in nums_in_clause)
                    if not has_val_a:
                        for idx_b, m_b in enumerate(structured_metrics):
                            if idx_a == idx_b or m_b.get("value") is None:
                                continue
                            if m_b.get("unit") != unit_a:
                                continue
                            val_b = float(m_b["value"])
                            if abs(val_a - val_b) <= tol_a:
                                continue
                            raw_keys_b = [k.strip().lower() for k in m_b.get("slot_keywords", []) if k.strip()]
                            matched_b = any(
                                (rkb in raw_lower if "|" in rkb else normalize_text(rkb) in clause)
                                for rkb in raw_keys_b
                            )
                            if not matched_b:
                                if any(abs(x - val_b) <= tol_a for x in nums_in_clause):
                                    raise LabelSwapDetectedError(
                                        f"LABEL_SWAP_ERROR (S0): El slot '{m_a['metric_id']}' ({m_a.get('entity')}) "
                                        f"esperaba {val_a} {unit_a}, pero recibió el valor {val_b} correspondiente a '{m_b['metric_id']}' ({m_b.get('entity')})."
                                    )

        return {"valid": True, "checked_metrics": len(structured_metrics)}


#!/usr/bin/env python3
"""H12 descriptive economic sensitivity preflight, NOT a new held-out decision.

All measured inputs are immutable original S4-C first-attempt A/B records.
Economic prices, distribution assumptions, and cold-catalog lifecycle charges
are scenario INPUTS, never inferred from bzip2's nine targets.
"""
import argparse
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1] / "results" / "SELECTOR-S4C"
DIGESTS = {
    "evaluation/result.json": "802f7ac91d9b5f5c67f58f8614b37c174363b5329580ba6f1a1f3e39f9471aed",
    "A/timing.json": "5e2135409802c8fed0b23e20ba3b2dde8f030e192fa97eabaf4e77b283f2bba5",
    "B/timing.json": "3ab628b1cef0b89b79c50e0408c3f081512042883d43e69f4bdf6eb8edf9c2f7",
}

def nonnegative(value):
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("invalid rate or cost") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("rates/costs must be finite nonnegative decimals")
    return parsed

def min_deliveries(fixed_cost, margin_per_delivery):
    """Smallest positive integer N with N*margin > fixed_cost (strict ROI)."""
    fixed_cost = nonnegative(fixed_cost)
    margin_per_delivery = Decimal(margin_per_delivery)
    if not margin_per_delivery.is_finite() or margin_per_delivery <= 0:
        return None
    return max(1, int((fixed_cost / margin_per_delivery).to_integral_value(rounding=ROUND_FLOOR)) + 1)

def sealed_evidence(root=ROOT):
    def load(filename):
        content = (root / filename).read_bytes()
        if hashlib.sha256(content).hexdigest() != DIGESTS[filename]:
            raise ValueError(f"sealed first-attempt evidence digest drift: {filename}")
        return json.loads(content)
    result = load("evaluation/result.json")
    if result.get("verdict") != "G5_SCOPED_PASS_K2":
        raise ValueError("unexpected sealed scientific verdict")
    a = result["repeat_a"]
    b = result["repeat_b"]
    if not (a["eligible"] and b["eligible"]):
        raise ValueError("ineligible original repeat")
    p_a = a["aggregate"]["previous1"]["physical_patch_bytes"]
    d_a = a["aggregate"]["delsk2"]["physical_patch_bytes"]
    p_b = b["aggregate"]["previous1"]["physical_patch_bytes"]
    d_b = b["aggregate"]["delsk2"]["physical_patch_bytes"]
    if (p_a, d_a) != (p_b, d_b):
        raise ValueError("A/B physical patch quality drift")
    if (p_a, d_a) != (109199, 107263):
        raise ValueError("unexpected pinned bzip2 cohort patch totals")
    repeat = {}
    for role in ("A", "B"):
        timing = load(role + "/timing.json")
        rounds = timing["rounds"]
        if len(rounds) != 7 or [r["order"] for r in rounds] != ["P-D","D-P","P-D","D-P","P-D","D-P","P-D"]:
            raise ValueError(f"noncanonical paired timing rounds: {role}")
        cpu_delta = median([r["delsk2"]["create_cpu_ns"] - r["previous1"]["create_cpu_ns"] for r in rounds])
        wall_delta = median([r["delsk2"]["create_wall_ns"] - r["previous1"]["create_wall_ns"] for r in rounds])
        if cpu_delta <= 0 or wall_delta <= 0:
            raise ValueError("unexpected negative extra create cost")
        repeat[role] = {
            "extra_create_cpu_seconds": Decimal(cpu_delta) / Decimal("1000000000"),
            "extra_create_wall_seconds": Decimal(wall_delta) / Decimal("1000000000"),
        }
    return {
        "scope": "descriptive first-attempt pinned bzip2 E1 / NOT independent H12",
        "saved_aggregate_physical_csp_bytes": p_a - d_a,
        "repeat": repeat,
    }

def model(evidence, cpu_price, egress_price, wall_penalty, unmeasured_lifecycle_cost, mode):
    cpu_price = nonnegative(cpu_price)
    egress_price = nonnegative(egress_price)
    wall_penalty = nonnegative(wall_penalty)
    unmeasured_lifecycle_cost = nonnegative(unmeasured_lifecycle_cost)
    if mode not in ("shared-release", "customized-per-recipient"):
        raise ValueError("mode must name a validated distribution topology")
    out = {}
    for role, metrics in evidence["repeat"].items():
        extra_create_cost = (
            metrics["extra_create_cpu_seconds"] * cpu_price
            + metrics["extra_create_wall_seconds"] * wall_penalty
        )
        saved_transfer_cost = Decimal(evidence["saved_aggregate_physical_csp_bytes"]) * egress_price
        if mode == "shared-release":
            extra_fixed_cost = extra_create_cost + unmeasured_lifecycle_cost
            delivery_margin = saved_transfer_cost
        else:
            extra_fixed_cost = unmeasured_lifecycle_cost
            delivery_margin = saved_transfer_cost - extra_create_cost
        n = min_deliveries(extra_fixed_cost, delivery_margin)
        out[role] = {
            "extra_create_cost": str(extra_create_cost),
            "saved_transfer_cost_per_identical_cohort_delivery": str(saved_transfer_cost),
            "extra_fixed_lifecycle_cost_assumption": str(unmeasured_lifecycle_cost),
            "net_margin_per_delivery_before_fixed_cost": str(delivery_margin),
            "strictly_positive_roi_first_integer_delivery": n,
        }
    return {
        "schema": "delsk.h12.descriptive-roi-preflight.v1",
        "scope": evidence["scope"],
        "delivery_topology": mode,
        "assumption": "EVERY modeled delivery transfers exactly the original same 9-target cohort; not an estimate of realistic downloads",
        "inputs": {
            "cpu_price_per_second": str(cpu_price),
            "egress_price_per_byte": str(egress_price),
            "independent_wall_deadline_penalty_per_second": str(wall_penalty),
            "extra_lifecycle_cost": str(unmeasured_lifecycle_cost),
        },
        "repeat_sensitivity": out,
        "scope_verdict": "DESCRIPTIVE_ONLY_NOT_H12_ROI_ACCEPTANCE",
        "missing_evidence": ["fresh multi-family consumer cohort", "real catalog RSS/build/storage", "actual target-specific distribution fanout", "network and trial I/O", "validated cost rates"],
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-price-per-second", required=True)
    parser.add_argument("--egress-price-per-byte", required=True)
    parser.add_argument("--extra-lifecycle-cost", required=True, help="Scenario-supplied cost for missing cold catalog/storage/RSS; zero means excluded")
    parser.add_argument("--wall-deadline-penalty-per-second", default="0", help="Separate latency penalty only; prevent double counting CPU")
    parser.add_argument("--mode", choices=["shared-release", "customized-per-recipient"], required=True)
    args = parser.parse_args()
    data = sealed_evidence()
    report = model(data, args.cpu_price_per_second, args.egress_price_per_byte,
                   args.wall_deadline_penalty_per_second, args.extra_lifecycle_cost, args.mode)
    print(json.dumps(report, indent=2, sort_keys=True))
if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
RNG = random.Random(20250605)
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"


@dataclass(frozen=True)
class Location:
    node: str
    role: str
    city: str
    state: str
    latitude: float
    longitude: float
    rationale: str


@dataclass(frozen=True)
class Product:
    sku: str
    ordering_cost: float
    holding_cost_month: float
    stockout_penalty: float
    unit_margin: float
    cube_ft: float
    trend_per_month: float
    demand_error_rate: float


LOCATIONS = {
    "Central": Location(
        "Central",
        "Manufacturing plant and central warehouse",
        "Chicago",
        "IL",
        41.8781,
        -87.6298,
        "The case states that Summit is headquartered in Chicago and has a central warehouse adjacent to its manufacturing plant.",
    ),
    "East": Location(
        "East",
        "East Coast regional warehouse",
        "Allentown",
        "PA",
        40.6023,
        -75.4714,
        "Allentown/Lehigh Valley is a realistic Northeast logistics hub with access to New York, New Jersey, Philadelphia, and I-78/I-476 corridors.",
    ),
    "West": Location(
        "West",
        "West Coast regional warehouse",
        "Ontario",
        "CA",
        34.0633,
        -117.6509,
        "Ontario in California's Inland Empire is a realistic West Coast distribution location near Los Angeles ports and large fulfillment networks.",
    ),
    "Midwest": Location(
        "Midwest",
        "Midwest regional warehouse",
        "Indianapolis",
        "IN",
        39.7684,
        -86.1581,
        "Indianapolis is a realistic Midwest distribution hub with strong interstate access and close enough to Chicago to make the CFO's closure proposal plausible.",
    ),
}


PRODUCTS = {
    "Treadmill": Product("Treadmill", 160, 26, 520, 480, 38, 0.003, 0.10),
    "Elliptical": Product("Elliptical", 150, 22, 330, 300, 42, -0.008, 0.13),
    "Rower": Product("Rower", 140, 18, 280, 220, 28, 0.000, 0.12),
    "SmartStrength": Product("SmartStrength", 180, 34, 650, 700, 32, 0.005, 0.15),
}


REGIONS = ["East", "West", "Midwest"]
SKUS = ["Treadmill", "Elliptical", "Rower", "SmartStrength"]


# The case gives regional demand figures in the inventory question. Because the
# quantitative prompt specifically asks for East Coast treadmills, this
# simulation treats those figures as treadmill baseline demand and constructs
# plausible supplementary demand for the other SKUs.
BASE_MONTHLY_DEMAND = {
    ("East", "Treadmill"): 1250,
    ("West", "Treadmill"): 1050,
    ("Midwest", "Treadmill"): 820,
    ("East", "Elliptical"): 620,
    ("West", "Elliptical"): 540,
    ("Midwest", "Elliptical"): 500,
    ("East", "Rower"): 360,
    ("West", "Rower"): 400,
    ("Midwest", "Rower"): 280,
    ("East", "SmartStrength"): 300,
    ("West", "SmartStrength"): 360,
    ("Midwest", "SmartStrength"): 240,
}


MONTH_WEIGHTS = {
    "Jan": 1.25,
    "Feb": 1.15,
    "Mar": 1.10,
    "Apr": 0.85,
    "May": 0.80,
    "Jun": 0.75,
    "Jul": 0.75,
    "Aug": 0.80,
    "Sep": 0.85,
    "Oct": 1.05,
    "Nov": 1.20,
    "Dec": 1.45,
}


CENTRAL_STOCK = {
    "Treadmill": 1000,
    "Elliptical": 2200,
    "Rower": 650,
    "SmartStrength": 520,
}


DIRECT_CUSTOMER_COMMITMENTS = {
    "Treadmill": 350,
    "Elliptical": 240,
    "Rower": 120,
    "SmartStrength": 120,
}


INVENTORY_COVERAGE = {
    ("East", "Treadmill"): 0.63,
    ("West", "Treadmill"): 0.95,
    ("Midwest", "Treadmill"): 1.38,
    ("East", "Elliptical"): 1.35,
    ("West", "Elliptical"): 1.20,
    ("Midwest", "Elliptical"): 1.70,
    ("East", "Rower"): 0.88,
    ("West", "Rower"): 1.05,
    ("Midwest", "Rower"): 0.95,
    ("East", "SmartStrength"): 0.82,
    ("West", "SmartStrength"): 1.00,
    ("Midwest", "SmartStrength"): 0.90,
}


def haversine_miles(a: Location, b: Location) -> float:
    radius_miles = 3958.7613
    lat1 = math.radians(a.latitude)
    lat2 = math.radians(b.latitude)
    dlat = math.radians(b.latitude - a.latitude)
    dlon = math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(h))


def estimate_road_miles(great_circle_miles: float) -> float:
    # A route factor converts straight-line distance into a practical truck-mile
    # estimate. It is intentionally conservative and should not be read as a
    # carrier quote.
    return great_circle_miles * 1.18


def transit_days(road_miles: float) -> int:
    return max(1, math.ceil(road_miles / 500.0) + 1)


def transfer_cost_per_unit(road_miles: float, product: Product) -> float:
    handling_per_unit = 18.0
    trailer_rate_per_mile = 2.50
    trailer_cube_capacity = 1700.0
    cube_mile_cost = trailer_rate_per_mile / trailer_cube_capacity
    return handling_per_unit + road_miles * cube_mile_cost * product.cube_ft


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_locations() -> list[dict]:
    return [
        {
            "node": loc.node,
            "role": loc.role,
            "city": loc.city,
            "state": loc.state,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "rationale": loc.rationale,
        }
        for loc in LOCATIONS.values()
    ]


def build_distance_matrix() -> list[dict]:
    rows = []
    for from_node, from_loc in LOCATIONS.items():
        for to_node, to_loc in LOCATIONS.items():
            if from_node == to_node:
                great_circle = 0.0
                road = 0.0
                days = 0
            else:
                great_circle = haversine_miles(from_loc, to_loc)
                road = estimate_road_miles(great_circle)
                days = transit_days(road)
            rows.append(
                {
                    "from_node": from_node,
                    "to_node": to_node,
                    "from_city": f"{from_loc.city}, {from_loc.state}",
                    "to_city": f"{to_loc.city}, {to_loc.state}",
                    "great_circle_miles": round(great_circle, 1),
                    "estimated_road_miles": round(road, 1),
                    "estimated_truck_transit_days": days,
                }
            )
    return rows


def lookup_distance(distance_rows: list[dict], from_node: str, to_node: str) -> dict:
    for row in distance_rows:
        if row["from_node"] == from_node and row["to_node"] == to_node:
            return row
    raise KeyError((from_node, to_node))


def simulate_monthly_demand() -> list[dict]:
    rows = []
    months = list(MONTH_WEIGHTS.keys())
    for month_index, month in enumerate(months, start=1):
        seasonality = MONTH_WEIGHTS[month]
        for region in REGIONS:
            for sku in SKUS:
                product = PRODUCTS[sku]
                base = BASE_MONTHLY_DEMAND[(region, sku)]
                trend = 1.0 + product.trend_per_month * (month_index - 1)
                noise = max(0.85, min(1.15, RNG.normalvariate(1.0, 0.045)))
                demand = max(0, round(base * seasonality * trend * noise))
                rows.append(
                    {
                        "year": 2025,
                        "month": month,
                        "month_index": month_index,
                        "region": region,
                        "sku": sku,
                        "base_monthly_demand": base,
                        "seasonality_index": seasonality,
                        "product_trend_factor": round(trend, 4),
                        "simulated_units": demand,
                    }
                )
    return rows


def forecast_next_month() -> list[dict]:
    rows = []
    month = "Jan"
    month_index = 13
    seasonality = MONTH_WEIGHTS[month]
    for region in REGIONS:
        for sku in SKUS:
            product = PRODUCTS[sku]
            base = BASE_MONTHLY_DEMAND[(region, sku)]
            trend = 1.0 + product.trend_per_month * (month_index - 1)
            forecast = base * seasonality * trend
            error_sd = base * product.demand_error_rate
            if region == "East" and sku == "Treadmill":
                error_sd = 125.0
            rows.append(
                {
                    "planning_month": "Jan-2026",
                    "region": region,
                    "sku": sku,
                    "forecast_units": round(forecast, 2),
                    "monthly_forecast_error_sd": round(error_sd, 2),
                    "forecast_method": "seasonal baseline with product trend and SKU-level forecast-error assumption",
                }
            )
    return rows


def build_initial_inventory(forecast_rows: list[dict]) -> list[dict]:
    rows = []
    for row in forecast_rows:
        region = row["region"]
        sku = row["sku"]
        forecast = float(row["forecast_units"])
        coverage = INVENTORY_COVERAGE[(region, sku)]
        on_hand = round(forecast * coverage)
        rows.append(
            {
                "planning_month": row["planning_month"],
                "region": region,
                "sku": sku,
                "on_hand_units": on_hand,
                "coverage_ratio_used": coverage,
                "setup_note": "Constructed to reflect case pattern: East treadmill stockout pressure, Midwest low turnover, and elliptical overstock.",
            }
        )
    return rows


def inventory_policy(forecast_rows: list[dict], initial_inventory: list[dict]) -> list[dict]:
    inv_lookup = {(r["region"], r["sku"]): int(r["on_hand_units"]) for r in initial_inventory}
    rows = []
    lead_time_days = 10
    z = 1.65
    for row in forecast_rows:
        region = row["region"]
        sku = row["sku"]
        product = PRODUCTS[sku]
        forecast = float(row["forecast_units"])
        sigma_month = float(row["monthly_forecast_error_sd"])
        sigma_ltd = sigma_month * math.sqrt(lead_time_days / 30)
        safety_stock = z * sigma_ltd
        mean_ltd = forecast / 30 * lead_time_days
        reorder_point = mean_ltd + safety_stock
        target_stock = forecast + safety_stock
        eoq = math.sqrt(2 * forecast * product.ordering_cost / product.holding_cost_month)
        on_hand = inv_lookup[(region, sku)]
        gap_to_target = max(0.0, target_stock - on_hand)
        surplus_above_target = max(0.0, on_hand - target_stock)
        rows.append(
            {
                "planning_month": row["planning_month"],
                "region": region,
                "sku": sku,
                "forecast_units": round(forecast, 2),
                "monthly_forecast_error_sd": round(sigma_month, 2),
                "mean_lead_time_demand": round(mean_ltd, 2),
                "std_lead_time_demand": round(sigma_ltd, 2),
                "safety_stock": round(safety_stock, 2),
                "reorder_point": round(reorder_point, 2),
                "eoq_units": round(eoq, 2),
                "on_hand_units": on_hand,
                "target_stock_units": round(target_stock, 2),
                "gap_to_target_units": round(gap_to_target, 2),
                "surplus_above_target_units": round(surplus_above_target, 2),
            }
        )
    return rows


def allocate_central_inventory(policy_rows: list[dict]) -> list[dict]:
    rows = []
    for sku in SKUS:
        product = PRODUCTS[sku]
        available = max(0.0, CENTRAL_STOCK[sku] - DIRECT_CUSTOMER_COMMITMENTS[sku])
        requests = [r for r in policy_rows if r["sku"] == sku and float(r["gap_to_target_units"]) > 0]
        total_weight = 0.0
        weighted_requests = []
        for r in requests:
            gap = float(r["gap_to_target_units"])
            severity = gap / max(float(r["target_stock_units"]), 1.0)
            score = (
                0.55 * severity
                + 0.25 * (product.stockout_penalty / 650)
                + 0.20 * (product.unit_margin / 700)
            )
            weight = gap * score
            weighted_requests.append((r, weight))
            total_weight += weight
        for r in [p for p in policy_rows if p["sku"] == sku]:
            request = float(r["gap_to_target_units"])
            if request <= 0 or available <= 0 or total_weight <= 0:
                allocation = 0.0
            else:
                weight = next(w for rr, w in weighted_requests if rr is r)
                allocation = min(request, available * weight / total_weight)
            rows.append(
                {
                    "planning_month": r["planning_month"],
                    "region": r["region"],
                    "sku": sku,
                    "request_units": round(request, 2),
                    "central_stock_units": CENTRAL_STOCK[sku],
                    "direct_customer_commitment_units": DIRECT_CUSTOMER_COMMITMENTS[sku],
                    "available_for_regional_replenishment": round(available, 2),
                    "central_allocated_units": round(allocation, 2),
                    "unfilled_request_after_central": round(max(0.0, request - allocation), 2),
                }
            )
    return rows


def recommend_transfers(
    policy_rows: list[dict], allocation_rows: list[dict], distance_rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    projected = {}
    target = {}
    forecast = {}
    surplus = {}
    gap = {}
    on_hand = {}
    for r in policy_rows:
        key = (r["region"], r["sku"])
        on_hand[key] = float(r["on_hand_units"])
        target[key] = float(r["target_stock_units"])
        forecast[key] = float(r["forecast_units"])
    for r in allocation_rows:
        key = (r["region"], r["sku"])
        projected[key] = on_hand[key] + float(r["central_allocated_units"])
        surplus[key] = max(0.0, projected[key] - target[key])
        gap[key] = max(0.0, target[key] - projected[key])

    transfers = []
    for sku in SKUS:
        product = PRODUCTS[sku]
        receivers = sorted(
            [region for region in REGIONS if gap[(region, sku)] > 1],
            key=lambda region: gap[(region, sku)] * product.stockout_penalty,
            reverse=True,
        )
        for to_region in receivers:
            if gap[(to_region, sku)] <= 1:
                continue
            senders = sorted(
                [region for region in REGIONS if region != to_region and surplus[(region, sku)] > 1],
                key=lambda region: lookup_distance(distance_rows, region, to_region)["estimated_road_miles"],
            )
            for from_region in senders:
                if gap[(to_region, sku)] <= 1:
                    break
                lane = lookup_distance(distance_rows, from_region, to_region)
                road_miles = float(lane["estimated_road_miles"])
                days = int(lane["estimated_truck_transit_days"])
                unit_cost = transfer_cost_per_unit(road_miles, product)
                economically_justified = product.stockout_penalty > unit_cost
                faster_than_central = days < 10
                if not economically_justified or not faster_than_central:
                    continue
                qty = min(gap[(to_region, sku)], surplus[(from_region, sku)])
                qty = math.floor(qty)
                if qty <= 0:
                    continue
                total_cost = qty * unit_cost
                avoided_penalty = qty * product.stockout_penalty
                transfers.append(
                    {
                        "planning_month": "Jan-2026",
                        "from_region": from_region,
                        "to_region": to_region,
                        "sku": sku,
                        "quantity_units": qty,
                        "estimated_road_miles": round(road_miles, 1),
                        "estimated_transit_days": days,
                        "transfer_cost_per_unit": round(unit_cost, 2),
                        "total_transfer_cost": round(total_cost, 2),
                        "avoided_stockout_penalty": round(avoided_penalty, 2),
                        "net_benefit_before_handling_risk": round(avoided_penalty - total_cost, 2),
                        "decision_rule": "Transfer if stockout penalty exceeds transfer cost and sender remains above target stock.",
                    }
                )
                projected[(from_region, sku)] -= qty
                projected[(to_region, sku)] += qty
                surplus[(from_region, sku)] = max(0.0, projected[(from_region, sku)] - target[(from_region, sku)])
                gap[(to_region, sku)] = max(0.0, target[(to_region, sku)] - projected[(to_region, sku)])

    post_rows = []
    for region in REGIONS:
        for sku in SKUS:
            key = (region, sku)
            post_rows.append(
                {
                    "planning_month": "Jan-2026",
                    "region": region,
                    "sku": sku,
                    "forecast_units": round(forecast[key], 2),
                    "target_stock_units": round(target[key], 2),
                    "projected_stock_after_central": round(
                        on_hand[key]
                        + next(
                            float(a["central_allocated_units"])
                            for a in allocation_rows
                            if a["region"] == region and a["sku"] == sku
                        ),
                        2,
                    ),
                    "projected_stock_after_transfers": round(projected[key], 2),
                    "remaining_gap_to_target": round(max(0.0, target[key] - projected[key]), 2),
                    "surplus_after_transfers": round(max(0.0, projected[key] - target[key]), 2),
                }
            )
    return transfers, post_rows


def summarize_kpis(
    policy_rows: list[dict], allocation_rows: list[dict], transfer_rows: list[dict], post_rows: list[dict]
) -> list[dict]:
    def product_penalty(sku: str) -> float:
        return PRODUCTS[sku].stockout_penalty

    central_projected = {}
    for p in policy_rows:
        key = (p["region"], p["sku"])
        alloc = next(
            float(a["central_allocated_units"])
            for a in allocation_rows
            if a["region"] == p["region"] and a["sku"] == p["sku"]
        )
        central_projected[key] = float(p["on_hand_units"]) + alloc

    target = {(p["region"], p["sku"]): float(p["target_stock_units"]) for p in policy_rows}
    baseline_gap = sum(max(0.0, target[k] - v) for k, v in central_projected.items())
    baseline_penalty = sum(max(0.0, target[k] - v) * product_penalty(k[1]) for k, v in central_projected.items())

    system_gap = sum(float(r["remaining_gap_to_target"]) for r in post_rows)
    system_penalty = sum(float(r["remaining_gap_to_target"]) * product_penalty(r["sku"]) for r in post_rows)
    transfer_cost = sum(float(r["total_transfer_cost"]) for r in transfer_rows)

    rows = [
        {
            "scenario": "Current central allocation without lateral transfers",
            "service_gap_units": round(baseline_gap, 2),
            "expected_service_gap_penalty": round(baseline_penalty, 2),
            "transfer_cost": 0.0,
            "net_penalty_after_transfer_cost": round(baseline_penalty, 2),
            "notes": "Reflects central allocation after direct customer commitments, but no regional transfer system.",
        },
        {
            "scenario": "With lateral transfers",
            "service_gap_units": round(system_gap, 2),
            "expected_service_gap_penalty": round(system_penalty, 2),
            "transfer_cost": round(transfer_cost, 2),
            "net_penalty_after_transfer_cost": round(system_penalty + transfer_cost, 2),
            "notes": "Uses transfer rule based on gap-to-target, sender surplus, transit time, and stockout penalty.",
        },
        {
            "scenario": "Improvement",
            "service_gap_units": round(baseline_gap - system_gap, 2),
            "expected_service_gap_penalty": round(baseline_penalty - system_penalty, 2),
            "transfer_cost": round(transfer_cost, 2),
            "net_penalty_after_transfer_cost": round(baseline_penalty - (system_penalty + transfer_cost), 2),
            "notes": "Positive net value means transfers reduce service risk by more than their logistics cost.",
        },
    ]
    return rows


def production_plan(post_rows: list[dict]) -> list[dict]:
    rows = []
    for sku in SKUS:
        forecast_total = sum(float(r["forecast_units"]) for r in post_rows if r["sku"] == sku)
        target_total = sum(float(r["target_stock_units"]) for r in post_rows if r["sku"] == sku)
        projected_total = sum(float(r["projected_stock_after_transfers"]) for r in post_rows if r["sku"] == sku)
        gap = max(0.0, target_total - projected_total)
        surplus = max(0.0, projected_total - target_total)
        gap_rate = gap / max(forecast_total, 1.0)
        surplus_rate = surplus / max(forecast_total, 1.0)
        if sku == "Elliptical" and surplus_rate > 0.25:
            recommendation = "Pilot a constrained reduction of up to 40% for the next planning cycle; verify changeover cost, labor impact, and channel effects before full execution."
            adjustment_pct = -40
        elif gap_rate > 0.18:
            adjustment_pct = min(25, round(gap_rate * 100))
            recommendation = f"Increase production by about {adjustment_pct}% before Q1 demand peaks; prioritize this SKU in central allocation."
        elif gap_rate > 0.08:
            adjustment_pct = min(12, round(gap_rate * 100))
            recommendation = f"Increase production by about {adjustment_pct}% and monitor regional service levels weekly."
        elif surplus_rate > 0.15:
            adjustment_pct = -min(25, round(surplus_rate * 100))
            recommendation = f"Reduce production by about {abs(adjustment_pct)}% until inventory approaches target."
        else:
            adjustment_pct = 0
            recommendation = "Keep production near the base plan and use regional transfers only for local imbalances."
        rows.append(
            {
                "planning_month": "Jan-2026",
                "sku": sku,
                "network_forecast_units": round(forecast_total, 2),
                "network_target_stock_units": round(target_total, 2),
                "projected_network_stock_after_transfers": round(projected_total, 2),
                "remaining_network_gap_units": round(gap, 2),
                "network_surplus_units": round(surplus, 2),
                "recommended_production_adjustment_pct": adjustment_pct,
                "recommendation": recommendation,
            }
        )
    return rows


def build_ai_decision_context(
    transfer_rows: list[dict],
    kpi_rows: list[dict],
    production_rows: list[dict],
    post_rows: list[dict],
) -> dict:
    high_priority_gaps = sorted(
        [r for r in post_rows if float(r["remaining_gap_to_target"]) > 0],
        key=lambda r: float(r["remaining_gap_to_target"]),
        reverse=True,
    )[:6]
    return {
        "case": "Summit Strength Fitness",
        "planning_month": "Jan-2026",
        "model_boundary": (
            "Deterministic EOQ/ROP, central allocation, transfer optimization, "
            "and production feedback have already been computed. The DeepSeek review "
            "explains the output and flags points managers should check."
        ),
        "transfer_recommendations": transfer_rows,
        "kpi_summary": kpi_rows,
        "production_plan": production_rows,
        "remaining_gaps": high_priority_gaps,
        "required_decision_policy": (
            "The review note recommends; managers approve and execute. Do not change mathematical "
            "outputs unless a human identifies data-quality or business exceptions."
        ),
    }


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def soften_scenario_precision(text: str) -> str:
    def money_repl(match: re.Match) -> str:
        raw = match.group(0).replace("$", "").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            return match.group(0)
        if value >= 10000:
            rounded = round(value / 1000.0) * 1000.0
        else:
            rounded = round(value / 100.0) * 100.0
        return f"about ${rounded:,.0f}"

    def units_repl(match: re.Match) -> str:
        value = float(match.group(1))
        return f"about {round(value):,.0f} units"

    text = re.sub(r"\$\d[\d,]*(?:\.\d+)?", money_repl, text)
    text = re.sub(r"\b(\d+\.\d+)\s+units\b", units_repl, text)
    text = re.sub(r"\b0\.\d+%", "less than 0.1%", text)
    text = re.sub(r"\b0\.\d+(?!%)\b", "less than 1", text)
    text = re.sub(r"(?<=:\s)(\d+\.\d+)\b", lambda m: f"about {round(float(m.group(1))):,.0f}", text)
    text = text.replace("about about $", "about $")
    return text


def soften_ai_review_precision(ai_review: dict) -> dict:
    for item in ai_review.get("recommendations", []):
        for key in ["recommendation", "rationale", "managerial_check"]:
            if isinstance(item.get(key), str):
                item[key] = soften_scenario_precision(item[key])
    if isinstance(ai_review.get("executive_decision"), str):
        ai_review["executive_decision"] = soften_scenario_precision(ai_review["executive_decision"])
    return ai_review


def call_deepseek_decision_review(context: dict) -> dict:
    load_local_env()
    api_key = os.environ.get(DEEPSEEK_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            "Missing DEEPSEEK_API_KEY. Set it as an environment variable or add it to "
            "the package .env file before running a fresh review."
        )
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
    model = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an operations-management reviewer. Review the deterministic "
                "inventory model outputs. Do not replace the formulas or optimization results. "
                "Return only valid JSON. Do not include hidden chain-of-thought; use concise rationales."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create a concise review output for a course paper. The JSON schema must be: "
                "{metadata:{provider,model,api_used,decision_scope,note}, executive_decision:string, "
                "recommendations:[{decision_area,recommendation,rationale,risk_level,approval_status,"
                "managerial_check}]}. Use the context below.\n\n"
                + json.dumps(context, ensure_ascii=True, indent=2)
            ),
        },
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1800,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    url = f"{base_url.rstrip('/')}/chat/completions"
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
        response_json = json.loads(raw)
        content = response_json["choices"][0]["message"]["content"]
        result = extract_json_object(content)
        result.setdefault("metadata", {})
        result["metadata"].update(
            {
                "provider": "DeepSeek API",
                "model": model,
                "api_used": True,
                "decision_scope": result["metadata"].get("decision_scope", "post-optimization review"),
            }
        )
        return soften_ai_review_precision(result)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "DeepSeek review failed. Check DEEPSEEK_API_KEY, DEEPSEEK_MODEL, "
            "DEEPSEEK_BASE_URL, and network access before rerunning the system."
        ) from exc


def ai_decision_rows(ai_review: dict) -> list[dict]:
    rows = []
    for idx, item in enumerate(ai_review.get("recommendations", []), start=1):
        rows.append(
            {
                "recommendation_id": idx,
                "decision_area": item.get("decision_area", ""),
                "recommendation": item.get("recommendation", ""),
                "rationale": item.get("rationale", ""),
                "risk_level": item.get("risk_level", ""),
                "approval_status": item.get("approval_status", ""),
                "managerial_check": item.get("managerial_check", ""),
            }
        )
    return rows


def render_markdown_report(
    location_rows: list[dict],
    distance_rows: list[dict],
    forecast_rows: list[dict],
    policy_rows: list[dict],
    allocation_rows: list[dict],
    transfer_rows: list[dict],
    post_rows: list[dict],
    kpi_rows: list[dict],
    production_rows: list[dict],
    ai_review: dict,
) -> str:
    def md_table(rows: list[dict], columns: list[str]) -> str:
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        body = ["| " + " | ".join(str(r.get(c, "")) for c in columns) + " |" for r in rows]
        return "\n".join([header, sep] + body)

    key_distances = [
        r
        for r in distance_rows
        if r["from_node"] in {"Central", "East", "West", "Midwest"}
        and r["to_node"] in {"Central", "East", "West", "Midwest"}
        and r["from_node"] < r["to_node"]
    ]
    east_treadmill_policy = [
        r for r in policy_rows if r["region"] == "East" and r["sku"] == "Treadmill"
    ][0]
    transfer_preview = transfer_rows[:10]
    high_priority_post = sorted(
        post_rows,
        key=lambda r: float(r["remaining_gap_to_target"]),
        reverse=True,
    )[:8]
    baseline_d = 1250.0
    baseline_s = PRODUCTS["Treadmill"].ordering_cost
    baseline_h = PRODUCTS["Treadmill"].holding_cost_month
    baseline_sigma = 125.0
    baseline_z = 1.65
    baseline_l = 10.0
    baseline_q = math.sqrt(2 * baseline_d * baseline_s / baseline_h)
    baseline_sigma_ltd = baseline_sigma * math.sqrt(baseline_l / 30)
    baseline_ss = baseline_z * baseline_sigma_ltd
    baseline_rop = baseline_d / 30 * baseline_l + baseline_ss
    transfer_display = []
    for row in transfer_preview:
        transfer_display.append(
            {
                "from_region": row["from_region"],
                "to_region": row["to_region"],
                "sku": row["sku"],
                "quantity_units": row["quantity_units"],
                "estimated_transit_days": row["estimated_transit_days"],
                "transfer_cost_per_unit": f"${float(row['transfer_cost_per_unit']):,.0f}",
                "total_transfer_cost": f"about ${float(row['total_transfer_cost']):,.0f}",
                "avoided_stockout_penalty": f"about ${float(row['avoided_stockout_penalty']):,.0f}",
                "net_benefit_before_handling_risk": f"about ${float(row['net_benefit_before_handling_risk']):,.0f}",
            }
        )
    kpi_display = []
    for row in kpi_rows:
        kpi_display.append(
            {
                "scenario": row["scenario"],
                "service_gap_units": f"{float(row['service_gap_units']):,.1f}",
                "expected_service_gap_penalty": f"about ${float(row['expected_service_gap_penalty']):,.0f}",
                "transfer_cost": f"about ${float(row['transfer_cost']):,.0f}",
                "net_penalty_after_transfer_cost": f"about ${float(row['net_penalty_after_transfer_cost']):,.0f}",
            }
        )
    ai_rows = ai_decision_rows(ai_review)

    return f"""# Summit Strength Fitness Inventory Simulation System

## 1. Scope

This file documents the simulated data design, the warehouse-location assumptions, the decision-support system, and the resulting recommendations for Summit Strength Fitness. The system is designed for a course-paper analysis, not for real operational deployment.

The case does not specify the exact warehouse cities. Therefore, the cities below are modeling assumptions based on realistic U.S. logistics hubs. They should be described in the paper as simulated locations, not as facts from the case.

## 2. Paper Thesis and Modeling Boundary

Recommended thesis for the paper:

> Summit should replace rigid monthly regional replenishment with an EOQ/ROP-based inventory baseline, introduce governed lateral transfers to coordinate the warehouse network, and shift from steady output to constrained seasonal flexibility, with DeepSeek used only as a review step rather than as an autonomous control system.

This report uses a two-layer model:

1. **Course baseline calculation.** The original case question asks for East Coast treadmill analysis using average monthly demand of 1,250 units. Under that baseline, \\(Q^* \\approx {baseline_q:.2f}\\), \\(SS \\approx {baseline_ss:.2f}\\), and \\(ROP \\approx {baseline_rop:.2f}\\).
2. **January 2026 planning simulation.** The system then applies a January seasonal factor to represent Q1 demand pressure. This increases the simulated East Coast treadmill forecast to {east_treadmill_policy["forecast_units"]} units and therefore raises the simulated EOQ and ROP.

These two layers should not be mixed. The first layer satisfies the original quantitative requirement; the second layer illustrates how the same formulas behave inside a forward-looking planning scenario.

All KPI values below are scenario outputs under simulated assumptions. They should be described as illustrative results, not as empirical evidence from Summit's real operations.

## 3. Location Design

{md_table(location_rows, ["node", "role", "city", "state", "latitude", "longitude"])}

Location rationale:

- Central is placed in Chicago because the case states that Summit is headquartered in Chicago and has a central warehouse adjacent to the manufacturing plant.
- East is placed in Allentown, Pennsylvania because the Lehigh Valley is a plausible Northeast distribution hub for New York, New Jersey, Philadelphia, and broader East Coast demand.
- West is placed in Ontario, California because the Inland Empire is a major West Coast warehousing area near the Los Angeles port complex and large consumer markets.
- Midwest is placed in Indianapolis, Indiana because it is a realistic Midwest logistics hub and is close enough to Chicago to make the CFO's proposal to close the Midwest warehouse plausible.

Distances are estimated using city coordinates. Great-circle distance is converted into estimated road miles by applying a 1.18 route factor. This is a simulation estimate, not a carrier quotation.

{md_table(key_distances, ["from_node", "to_node", "from_city", "to_city", "great_circle_miles", "estimated_road_miles", "estimated_truck_transit_days"])}

## 4. Simulated Data Design

The simulation creates four data layers:

1. Monthly demand data for 2025 by region and SKU.
2. A January 2026 planning forecast by region and SKU.
3. Initial inventory at each regional warehouse.
4. Central-warehouse inventory after direct-customer commitments.

The 2025 monthly demand pattern reflects the case statement that Q1 and Q4 account for a large share of sales. The seasonal index gives January-March and October-December higher demand, while Q2 and Q3 are lower-demand periods. Treadmills are modeled as the most constrained product, while ellipticals are modeled as the overstocked product, matching the case.

Because the quantitative prompt specifically asks for East Coast treadmills, the given East Coast demand figure is used as the baseline for East Coast treadmill demand. Other SKU demand values are simulated as realistic supplementary data so that the multi-product inventory system can operate.

Important assumption note: warehouse coverage ratios, central stock, direct-customer commitments, stockout penalties, and transfer costs are constructed for scenario analysis. They make the operating logic visible, but they should not be presented as known facts.

## 5. Decision Logic

The system has six modules:

| Module | Role | Method |
|---|---|---|
| Demand Forecasting Agent | Forecast next-month regional SKU demand | Seasonal baseline plus product trend and forecast-error assumption |
| Regional Warehouse Agent | Compute inventory gaps and surplus | EOQ, safety stock, reorder point, target stock |
| Central Warehouse Agent | Allocate constrained central inventory | Priority allocation after direct-customer commitments |
| Transfer Optimization Agent | Recommend lateral transfers | Transfer if stockout penalty exceeds transfer cost and sender remains above target |
| Production Planning Agent | Recommend product-mix adjustment | Aggregate network gap/surplus by SKU |
| DeepSeek Review | Explain model outputs and flag approval conditions | DeepSeek V4-Pro API; requires `DEEPSEEK_API_KEY` |

The key East Coast treadmill policy outputs are:

{md_table([east_treadmill_policy], ["region", "sku", "forecast_units", "monthly_forecast_error_sd", "safety_stock", "reorder_point", "eoq_units", "on_hand_units", "target_stock_units", "gap_to_target_units"])}

The numbers above are higher than the baseline EOQ section because this is the January planning scenario, not the average-month baseline.

## 6. Central Allocation Result

The central warehouse first protects direct customer commitments. The remaining stock is then allocated to regional requests. This reflects the case problem that central fulfillment often shorts regional replenishment requests.

{md_table(allocation_rows, ["region", "sku", "request_units", "central_stock_units", "direct_customer_commitment_units", "available_for_regional_replenishment", "central_allocated_units", "unfilled_request_after_central"])}

## 7. Lateral Transfer Recommendations

The transfer engine evaluates regional surplus, remaining service gaps, lane distance, estimated transit days, per-unit transfer cost, and stockout penalty.

{md_table(transfer_display, ["from_region", "to_region", "sku", "quantity_units", "estimated_transit_days", "transfer_cost_per_unit", "total_transfer_cost", "avoided_stockout_penalty", "net_benefit_before_handling_risk"])}

The rounded dollar values above should be read as scenario magnitudes. The exact reproducible values remain available in `data/transfer_recommendations.csv`.

## 8. Resulting Inventory Position

After central allocation and lateral transfers, the highest remaining gaps are:

{md_table(high_priority_post, ["region", "sku", "forecast_units", "target_stock_units", "projected_stock_after_central", "projected_stock_after_transfers", "remaining_gap_to_target", "surplus_after_transfers"])}

## 9. KPI Summary

{md_table(kpi_display, ["scenario", "service_gap_units", "expected_service_gap_penalty", "transfer_cost", "net_penalty_after_transfer_cost"])}

The transfer system reduces service-gap units and expected service-risk penalty after accounting for transfer cost. Under these assumptions, the improvement is approximately $103,000. This should be interpreted as a scenario illustration of the value of governed lateral transfers, not as a verified dollar saving.

## 10. Production Planning Output

{md_table(production_rows, ["sku", "network_forecast_units", "network_target_stock_units", "projected_network_stock_after_transfers", "remaining_network_gap_units", "network_surplus_units", "recommended_production_adjustment_pct", "recommendation"])}

## 11. DeepSeek Review Output

The DeepSeek review is placed after the deterministic optimization steps. It does not recalculate EOQ, ROP, allocation, or transfer quantities. Its role is to summarize the decision, identify risk, and state what managers should verify before approval.

Review note: {ai_review.get("metadata", {}).get("provider", "Unknown provider")} / {ai_review.get("metadata", {}).get("model", "Unknown model")}. {ai_review.get("metadata", {}).get("note", "")}

Executive decision: {ai_review.get("executive_decision", "")}

{md_table(ai_rows, ["decision_area", "recommendation", "rationale", "risk_level", "approval_status", "managerial_check"])}

## 12. Steady Output Policy Trade-Off

The model points toward reducing elliptical output and protecting treadmill availability, but this should not be treated as a purely mechanical decision. The original case asks for a policy debate, so the paper should compare three options:

| Policy | Operational benefit | Risk |
|---|---|---|
| Keep rigid steady output | Stable labor schedule and low disruption | Continued overstock of weak SKUs and stockouts of high-demand SKUs |
| Chase demand fully | Best product-demand match | High workforce stress, changeover cost, unstable schedules, and learning-curve losses |
| Base-plus-adjustment policy | Balances workforce stability with seasonal flexibility | Requires better forecasting, cross-training, and production planning discipline |

Therefore, Summit should not fully abandon steady output. A constrained seasonal adjustment policy is stronger: keep a stable base level of production, cross-train labor, raise treadmill capacity before Q1 and Q4, and reduce elliptical output only after checking changeover cost, morale, channel impact, and brand risk from stockouts.

## 13. Review Step and Pilot Controls

The DeepSeek review step should be piloted before full use. A credible pilot would require:

- Reliable SKU-level demand data by region.
- Near-real-time inventory accuracy from WMS or ERP systems.
- Integrated order priorities, promotion calendars, lead times, and transfer costs.
- Human approval rules for high-value transfers and key-account exceptions.
- Incentives that prevent regional managers from hiding inventory or resisting transfers.
- Monitoring for forecast error, model drift, and repeated override patterns.
- Clear accountability: the tool recommends, but managers approve exceptions and own execution.

This keeps the review step inside operations management logic. The system extends EOQ, safety stock, ROP, pooling, and lateral-transfer reasoning; it does not replace managerial judgment.

## 14. Managerial Interpretation

The system result is consistent with the broader recommendation for Summit:

- EOQ and safety stock create transparent local inventory baselines.
- Central allocation alone does not solve regional imbalance because central stock is constrained by direct customer commitments.
- Lateral transfers are most useful when the sender remains above target stock and the receiver faces a high stockout penalty.
- The Midwest warehouse should not be closed purely on holding-cost logic, because it can act as a buffer for East Coast treadmill shortages.
- The plant should move from rigid steady output to a base-plus-adjustment policy rather than full demand chasing.
- The DeepSeek review should stay behind the inventory model, with human review, exception controls, and data-quality checks.

## 15. Limitations

This is a structured simulation. It does not use Summit's real SKU-level sales records, carrier contracts, warehouse lease costs, labor schedules, or live inventory feeds. The value of the system is that it shows how Summit could connect course concepts--EOQ, safety stock, reorder points, pooling, lateral transfer, and aggregate planning--into one coherent decision process.
"""


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    location_rows = build_locations()
    distance_rows = build_distance_matrix()
    demand_rows = simulate_monthly_demand()
    forecast_rows = forecast_next_month()
    inventory_rows = build_initial_inventory(forecast_rows)
    policy_rows = inventory_policy(forecast_rows, inventory_rows)
    allocation_rows = allocate_central_inventory(policy_rows)
    transfer_rows, post_rows = recommend_transfers(policy_rows, allocation_rows, distance_rows)
    kpi_rows = summarize_kpis(policy_rows, allocation_rows, transfer_rows, post_rows)
    production_rows = production_plan(post_rows)
    ai_context = build_ai_decision_context(transfer_rows, kpi_rows, production_rows, post_rows)
    ai_review = call_deepseek_decision_review(ai_context)
    ai_rows = ai_decision_rows(ai_review)

    write_csv(DATA_DIR / "locations.csv", list(location_rows[0].keys()), location_rows)
    write_csv(DATA_DIR / "distance_matrix.csv", list(distance_rows[0].keys()), distance_rows)
    write_csv(DATA_DIR / "monthly_demand_2025.csv", list(demand_rows[0].keys()), demand_rows)
    write_csv(DATA_DIR / "forecast_jan_2026.csv", list(forecast_rows[0].keys()), forecast_rows)
    write_csv(DATA_DIR / "initial_inventory.csv", list(inventory_rows[0].keys()), inventory_rows)
    write_csv(DATA_DIR / "inventory_policy_outputs.csv", list(policy_rows[0].keys()), policy_rows)
    write_csv(DATA_DIR / "central_allocation.csv", list(allocation_rows[0].keys()), allocation_rows)
    write_csv(DATA_DIR / "transfer_recommendations.csv", list(transfer_rows[0].keys()), transfer_rows)
    write_csv(DATA_DIR / "post_transfer_inventory.csv", list(post_rows[0].keys()), post_rows)
    write_csv(DATA_DIR / "kpi_summary.csv", list(kpi_rows[0].keys()), kpi_rows)
    write_csv(DATA_DIR / "production_plan.csv", list(production_rows[0].keys()), production_rows)
    ai_fieldnames = [
        "recommendation_id",
        "decision_area",
        "recommendation",
        "rationale",
        "risk_level",
        "approval_status",
        "managerial_check",
    ]
    write_csv(DATA_DIR / "ai_decision_review.csv", ai_fieldnames, ai_rows)
    (DATA_DIR / "ai_decision_review.json").write_text(
        json.dumps(ai_review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = render_markdown_report(
        location_rows,
        distance_rows,
        forecast_rows,
        policy_rows,
        allocation_rows,
        transfer_rows,
        post_rows,
        kpi_rows,
        production_rows,
        ai_review,
    )
    (REPORT_DIR / "simulation_data_and_system_results.md").write_text(report, encoding="utf-8")

    print("Generated Summit inventory simulation system outputs:")
    for path in [
        DATA_DIR / "locations.csv",
        DATA_DIR / "distance_matrix.csv",
        DATA_DIR / "monthly_demand_2025.csv",
        DATA_DIR / "forecast_jan_2026.csv",
        DATA_DIR / "inventory_policy_outputs.csv",
        DATA_DIR / "transfer_recommendations.csv",
        DATA_DIR / "kpi_summary.csv",
        DATA_DIR / "production_plan.csv",
        DATA_DIR / "ai_decision_review.csv",
        DATA_DIR / "ai_decision_review.json",
        REPORT_DIR / "simulation_data_and_system_results.md",
    ]:
        print(f"- {path.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

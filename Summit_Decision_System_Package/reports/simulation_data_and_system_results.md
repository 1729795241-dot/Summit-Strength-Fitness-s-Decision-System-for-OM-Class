# Summit Strength Fitness Inventory Simulation System

## 1. Scope

This file documents the simulated data design, the warehouse-location assumptions, the decision-support system, and the resulting recommendations for Summit Strength Fitness. The system is designed for a course-paper analysis, not for real operational deployment.

The case does not specify the exact warehouse cities. Therefore, the cities below are modeling assumptions based on realistic U.S. logistics hubs. They should be described in the paper as simulated locations, not as facts from the case.

## 2. Paper Thesis and Modeling Boundary

Recommended thesis for the paper:

> Summit should replace rigid monthly regional replenishment with an EOQ/ROP-based inventory baseline, introduce governed lateral transfers to coordinate the warehouse network, and shift from steady output to constrained seasonal flexibility, with DeepSeek used only as a review step rather than as an autonomous control system.

This report uses a two-layer model:

1. **Course baseline calculation.** The original case question asks for East Coast treadmill analysis using average monthly demand of 1,250 units. Under that baseline, \(Q^* \approx 124.03\), \(SS \approx 119.08\), and \(ROP \approx 535.75\).
2. **January 2026 planning simulation.** The system then applies a January seasonal factor to represent Q1 demand pressure. This increases the simulated East Coast treadmill forecast to 1618.75 units and therefore raises the simulated EOQ and ROP.

These two layers should not be mixed. The first layer satisfies the original quantitative requirement; the second layer illustrates how the same formulas behave inside a forward-looking planning scenario.

All KPI values below are scenario outputs under simulated assumptions. They should be described as illustrative results, not as empirical evidence from Summit's real operations.

## 3. Location Design

| node | role | city | state | latitude | longitude |
| --- | --- | --- | --- | --- | --- |
| Central | Manufacturing plant and central warehouse | Chicago | IL | 41.8781 | -87.6298 |
| East | East Coast regional warehouse | Allentown | PA | 40.6023 | -75.4714 |
| West | West Coast regional warehouse | Ontario | CA | 34.0633 | -117.6509 |
| Midwest | Midwest regional warehouse | Indianapolis | IN | 39.7684 | -86.1581 |

Location rationale:

- Central is placed in Chicago because the case states that Summit is headquartered in Chicago and has a central warehouse adjacent to the manufacturing plant.
- East is placed in Allentown, Pennsylvania because the Lehigh Valley is a plausible Northeast distribution hub for New York, New Jersey, Philadelphia, and broader East Coast demand.
- West is placed in Ontario, California because the Inland Empire is a major West Coast warehousing area near the Los Angeles port complex and large consumer markets.
- Midwest is placed in Indianapolis, Indiana because it is a realistic Midwest logistics hub and is close enough to Chicago to make the CFO's proposal to close the Midwest warehouse plausible.

Distances are estimated using city coordinates. Great-circle distance is converted into estimated road miles by applying a 1.18 route factor. This is a simulation estimate, not a carrier quotation.

| from_node | to_node | from_city | to_city | great_circle_miles | estimated_road_miles | estimated_truck_transit_days |
| --- | --- | --- | --- | --- | --- | --- |
| Central | East | Chicago, IL | Allentown, PA | 637.3 | 752.0 | 3 |
| Central | West | Chicago, IL | Ontario, CA | 1711.8 | 2019.9 | 6 |
| Central | Midwest | Chicago, IL | Indianapolis, IN | 164.8 | 194.5 | 2 |
| East | West | Allentown, PA | Ontario, CA | 2338.0 | 2758.8 | 7 |
| East | Midwest | Allentown, PA | Indianapolis, IN | 566.7 | 668.7 | 3 |
| Midwest | West | Indianapolis, IN | Ontario, CA | 1774.1 | 2093.4 | 6 |

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

| region | sku | forecast_units | monthly_forecast_error_sd | safety_stock | reorder_point | eoq_units | on_hand_units | target_stock_units | gap_to_target_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| East | Treadmill | 1618.75 | 125.0 | 119.08 | 658.66 | 141.15 | 1020 | 1737.83 | 717.83 |

The numbers above are higher than the baseline EOQ section because this is the January planning scenario, not the average-month baseline.

## 6. Central Allocation Result

The central warehouse first protects direct customer commitments. The remaining stock is then allocated to regional requests. This reflects the case problem that central fulfillment often shorts regional replenishment requests.

| region | sku | request_units | central_stock_units | direct_customer_commitment_units | available_for_regional_replenishment | central_allocated_units | unfilled_request_after_central |
| --- | --- | --- | --- | --- | --- | --- | --- |
| East | Treadmill | 717.83 | 1000 | 350 | 650 | 557.55 | 160.28 |
| West | Treadmill | 167.78 | 1000 | 350 | 650 | 92.45 | 75.33 |
| Midwest | Treadmill | 0.0 | 1000 | 350 | 650 | 0.0 | 0.0 |
| East | Elliptical | 0.0 | 2200 | 240 | 1960 | 0.0 | 0.0 |
| West | Elliptical | 0.0 | 2200 | 240 | 1960 | 0.0 | 0.0 |
| Midwest | Elliptical | 0.0 | 2200 | 240 | 1960 | 0.0 | 0.0 |
| East | Rower | 95.15 | 650 | 120 | 530 | 95.15 | 0.0 |
| West | Rower | 20.73 | 650 | 120 | 530 | 20.73 | 0.0 |
| Midwest | Rower | 50.01 | 650 | 120 | 530 | 50.01 | 0.0 |
| East | SmartStrength | 114.37 | 520 | 120 | 400 | 114.37 | 0.0 |
| West | SmartStrength | 51.44 | 520 | 120 | 400 | 51.44 | 0.0 |
| Midwest | SmartStrength | 66.29 | 520 | 120 | 400 | 66.29 | 0.0 |

## 7. Lateral Transfer Recommendations

The transfer engine evaluates regional surplus, remaining service gaps, lane distance, estimated transit days, per-unit transfer cost, and stockout penalty.

| from_region | to_region | sku | quantity_units | estimated_transit_days | transfer_cost_per_unit | total_transfer_cost | avoided_stockout_penalty | net_benefit_before_handling_risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Midwest | East | Treadmill | 160 | 3 | $55 | about $8,859 | about $83,200 | about $74,341 |
| Midwest | West | Treadmill | 75 | 6 | $135 | about $10,124 | about $39,000 | about $28,876 |

The rounded dollar values above should be read as scenario magnitudes. The exact reproducible values remain available in `data/transfer_recommendations.csv`.

## 8. Resulting Inventory Position

After central allocation and lateral transfers, the highest remaining gaps are:

| region | sku | forecast_units | target_stock_units | projected_stock_after_central | projected_stock_after_transfers | remaining_gap_to_target | surplus_after_transfers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| West | Treadmill | 1359.75 | 1459.78 | 1384.45 | 1459.45 | 0.33 | 0.0 |
| East | Treadmill | 1618.75 | 1737.83 | 1577.55 | 1737.55 | 0.28 | 0.0 |
| East | Elliptical | 700.6 | 777.38 | 946.0 | 946.0 | 0.0 | 168.62 |
| East | Rower | 450.0 | 491.15 | 491.15 | 491.15 | 0.0 | 0.0 |
| East | SmartStrength | 397.5 | 440.37 | 440.37 | 440.37 | 0.0 | 0.0 |
| West | Elliptical | 610.2 | 677.07 | 732.0 | 732.0 | 0.0 | 54.93 |
| West | Rower | 500.0 | 545.73 | 545.73 | 545.73 | 0.0 | 0.0 |
| West | SmartStrength | 477.0 | 528.44 | 528.44 | 528.44 | 0.0 | 0.0 |

## 9. KPI Summary

| scenario | service_gap_units | expected_service_gap_penalty | transfer_cost | net_penalty_after_transfer_cost |
| --- | --- | --- | --- | --- |
| Current central allocation without lateral transfers | 235.6 | about $122,517 | about $0 | about $122,517 |
| With lateral transfers | 0.6 | about $317 | about $18,983 | about $19,300 |
| Improvement | 235.0 | about $122,200 | about $18,983 | about $103,217 |

The transfer system reduces service-gap units and expected service-risk penalty after accounting for transfer cost. Under these assumptions, the improvement is approximately $103,000. This should be interpreted as a scenario illustration of the value of governed lateral transfers, not as a verified dollar saving.

## 10. Production Planning Output

| sku | network_forecast_units | network_target_stock_units | projected_network_stock_after_transfers | remaining_network_gap_units | network_surplus_units | recommended_production_adjustment_pct | recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Treadmill | 4040.4 | 4337.63 | 4427.0 | 0.0 | 89.37 | 0 | Keep production near the base plan and use regional transfers only for local imbalances. |
| Elliptical | 1875.8 | 2081.37 | 2638.0 | 0.0 | 556.63 | -40 | Pilot a constrained reduction of up to 40% for the next planning cycle; verify changeover cost, labor impact, and channel effects before full execution. |
| Rower | 1300.0 | 1418.89 | 1418.89 | 0.0 | 0.0 | 0 | Keep production near the base plan and use regional transfers only for local imbalances. |
| SmartStrength | 1192.5 | 1321.1 | 1321.1 | 0.0 | 0.0 | 0 | Keep production near the base plan and use regional transfers only for local imbalances. |

## 11. DeepSeek Review Output

The DeepSeek review is placed after the deterministic optimization steps. It does not recalculate EOQ, ROP, allocation, or transfer quantities. Its role is to summarize the decision, identify risk, and state what managers should verify before approval.

Review note: DeepSeek API / deepseek-v4-pro. Review of model outputs; no formulas or optimization results replaced. Managers must approve and execute.

Executive decision: Proceed with lateral transfers for Treadmill from Midwest to East and West, and pilot a 40% production reduction for Elliptical. Net penalty reduction of about $103,000 confirms transfers are value-adding. Remaining gaps are negligible (about 1 units).

| decision_area | recommendation | rationale | risk_level | approval_status | managerial_check |
| --- | --- | --- | --- | --- | --- |
| Lateral Transfers | Execute Treadmill transfers: 160 units Midwest→East and 75 units Midwest→West. | Net benefit of about $74,000 (East) and about $29,000 (West) after transfer costs; sender remains above target stock. Avoids about $122,000 in stockout penalties. | Low | Recommended for approval | Verify Midwest surplus is real and not needed for local demand spikes; confirm transit times and road conditions. |
| Production Adjustment | Pilot a 40% reduction in Elliptical production for next cycle. | Network surplus of about 557 units after transfers; reduction aligns stock with target and avoids excess holding costs. | Medium | Recommended for approval with constraints | Assess changeover costs, labor impact, and channel effects before full execution; confirm demand forecast stability. |
| Production Hold | Maintain base production plan for Treadmill, Rower, and SmartStrength. | Network gaps are zero or minimal; transfers address regional imbalances without production changes. | Low | Approved | Monitor regional demand signals for unexpected shifts. |
| Remaining Gaps | Accept negligible remaining gaps (less than 1 West, less than 1 East) as within tolerance. | Total service gap of about 1 units and penalty of about $300 are immaterial; further actions not cost-effective. | Low | Approved | None required; standard monitoring. |

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

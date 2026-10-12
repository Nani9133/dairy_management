"""
Route Optimization Engine
Main deterministic optimizer.

This module combines:

    constraints
    assignment
    sequencing
    rebalancing

into one proposal-only optimization engine.

IMPORTANT:

    This module does NOT modify ERPNext documents.

    The optimizer calculates what SHOULD change.

    A separate approval/write workflow must explicitly
    approve and apply the proposed changes.

Optimization hierarchy:

    1. Feasibility
    2. Capacity
    3. Geographic / routing efficiency
    4. Sequence efficiency
    5. Route stability
    6. Route change minimization

The optimizer is deterministic.

AI/LLM components should explain or assist with the
result, but should not directly assign customers.
"""

from typing import Any, Dict, List, Optional

from .constraints import (
    check_customer_for_route,
)
from .rebalancer import (
    DEFAULT_MIN_IMPROVEMENT,
    generate_customer_rebalance_proposals,
    generate_rebalance_plan,
)
from .sequencing import (
    RoutingEngine,
)


# ============================================================================
# ENGINE VERSION
# ============================================================================

OPTIMIZER_VERSION = "0.1.0"


# ============================================================================
# NORMALIZATION
# ============================================================================

def normalize_customer(
    customer: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize customer data used by the optimizer.
    """

    return {
        "name": customer.get("name"),
        "customer_name": customer.get(
            "customer_name"
        ),
        "latitude": customer.get(
            "latitude"
        ),
        "longitude": customer.get(
            "longitude"
        ),
        "route": customer.get(
            "route"
        ),
        "pickpoint__warehouse": customer.get(
            "pickpoint__warehouse"
        ),
        "state": customer.get(
            "state"
        ),
        "city": customer.get(
            "city"
        ),
        "zone": customer.get(
            "zone"
        ),
        "area": customer.get(
            "area"
        ),
        "point": customer.get(
            "point"
        ),
    }


def normalize_route(
    route: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize route data used by the optimizer.
    """

    return {
        "name": route.get("name"),
        "route_name": route.get(
            "route_name"
        ),
        "route_id": route.get(
            "route_id"
        ),
        "route_type": route.get(
            "route_type"
        ),
        "route_status": route.get(
            "route_status"
        ),
        "point_name": route.get(
            "point_name"
        ),
        "boundary_geojson": route.get(
            "boundary_geojson"
        ),
        "capacity": route.get(
            "capacity"
        ),
        "current_load": route.get(
            "current_load"
        ),
        "capacity_unit": route.get(
            "capacity_unit"
        ),
    }


# ============================================================================
# IDENTIFIERS
# ============================================================================

def customer_key(
    customer: Dict[str, Any],
) -> Optional[str]:
    """
    Return the customer's primary identifier.
    """

    return (
        customer.get("name")
        or customer.get(
            "customer_name"
        )
    )


def route_key(
    route: Dict[str, Any],
) -> Optional[str]:
    """
    Return the route's primary identifier.
    """

    return (
        route.get("name")
        or route.get(
            "route_name"
        )
        or route.get(
            "route_id"
        )
    )


# ============================================================================
# FEASIBILITY
# ============================================================================

def validate_customer(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Validate whether the customer's current route
    and location information are usable.

    No database changes are performed.
    """

    normalized_customer = normalize_customer(
        customer
    )

    current_route_name = normalized_customer.get(
        "route"
    )

    violations = []

    if not normalized_customer.get(
        "name"
    ):
        violations.append(
            "Customer name is missing"
        )

    if normalized_customer.get(
        "latitude"
    ) is None:
        violations.append(
            "Customer latitude is missing"
        )

    if normalized_customer.get(
        "longitude"
    ) is None:
        violations.append(
            "Customer longitude is missing"
        )

    current_route = None

    if current_route_name:

        for route in routes:

            normalized_route = normalize_route(
                route
            )

            if str(
                route_key(
                    normalized_route
                )
            ) == str(
                current_route_name
            ):
                current_route = (
                    normalized_route
                )
                break

    if current_route is None:

        violations.append(
            "Customer current route was not found"
        )

    elif current_route.get(
        "route_status"
    ) != "Active":

        violations.append(
            "Customer current route is not active"
        )

    return {
        "valid": not violations,
        "customer": normalized_customer,
        "current_route": current_route,
        "violations": violations,
    }


# ============================================================================
# ROUTE INDEX
# ============================================================================

def build_route_index(
    routes: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Build a deterministic route lookup dictionary.
    """

    index = {}

    for route in routes:

        normalized_route = normalize_route(
            route
        )

        key = route_key(
            normalized_route
        )

        if key:
            index[str(key)] = (
                normalized_route
            )

    return index


# ============================================================================
# SINGLE CUSTOMER OPTIMIZATION
# ============================================================================

def optimize_customer(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
    customers: List[Dict[str, Any]],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
    min_improvement: float = (
        DEFAULT_MIN_IMPROVEMENT
    ),
) -> Dict[str, Any]:
    """
    Optimize one customer against the available routes.

    The customer's current route is treated as the baseline.

    Alternative routes are evaluated as candidates.

    A route change is only proposed when the alternative
    produces a meaningful objective improvement.

    No ERPNext records are modified.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    validation = validate_customer(
        customer,
        routes,
    )

    if not validation["valid"]:

        return {
            "status": "INVALID_CUSTOMER",
            "feasible": False,
            "customer": validation[
                "customer"
            ],
            "current_route": validation[
                "current_route"
            ],
            "violations": validation[
                "violations"
            ],
            "proposal": None,
            "assignment_changed": False,
            "requires_user_approval": False,
        }

    proposal_plan = (
        generate_customer_rebalance_proposals(
            customer=customer,
            routes=routes,
            customers=customers,
            routing_engine=routing,
            min_improvement=min_improvement,
        )
    )

    proposals = proposal_plan.get(
        "proposals",
        [],
    )

    if proposals:

        best_proposal = proposals[0]

        return {
            "status": "PROPOSAL_READY",
            "feasible": True,
            "customer": proposal_plan[
                "customer"
            ],
            "current_route": proposal_plan[
                "current_route"
            ],
            "baseline": proposal_plan[
                "baseline"
            ],
            "candidate_evaluations": (
                proposal_plan[
                    "candidate_evaluations"
                ]
            ),
            "rejected_routes": (
                proposal_plan[
                    "rejected_routes"
                ]
            ),
            "proposal": best_proposal,
            "proposal_count": len(
                proposals
            ),
            "requires_user_approval": True,
            "assignment_changed": False,
        }

    return {
        "status": (
            proposal_plan.get(
                "status"
            )
            or "NO_CHANGE"
        ),
        "feasible": True,
        "customer": proposal_plan[
            "customer"
        ],
        "current_route": proposal_plan[
            "current_route"
        ],
        "baseline": proposal_plan[
            "baseline"
        ],
        "candidate_evaluations": (
            proposal_plan[
                "candidate_evaluations"
            ]
        ),
        "rejected_routes": (
            proposal_plan[
                "rejected_routes"
            ]
        ),
        "proposal": None,
        "proposal_count": 0,
        "requires_user_approval": False,
        "assignment_changed": False,
    }


# ============================================================================
# MULTI CUSTOMER OPTIMIZATION
# ============================================================================

def optimize_customers(
    customers: List[Dict[str, Any]],
    routes: List[Dict[str, Any]],
    affected_customer_names: Optional[
        List[str]
    ] = None,
    routing_engine: Optional[
        RoutingEngine
    ] = None,
    min_improvement: float = (
        DEFAULT_MIN_IMPROVEMENT
    ),
) -> Dict[str, Any]:
    """
    Optimize a group of affected customers.

    The optimizer intentionally works on the supplied
    affected set rather than recalculating the entire
    city unnecessarily.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    if affected_customer_names:

        affected_set = {
            str(name)
            for name in affected_customer_names
        }

        selected_customers = [
            customer
            for customer in customers
            if (
                str(
                    customer.get(
                        "name"
                    )
                )
                in affected_set
                or str(
                    customer.get(
                        "customer_name"
                    )
                )
                in affected_set
            )
        ]

    else:

        selected_customers = list(
            customers
        )

    results = []

    proposals = []

    no_change = []

    invalid = []

    for customer in selected_customers:

        result = optimize_customer(
            customer=customer,
            routes=routes,
            customers=customers,
            routing_engine=routing,
            min_improvement=min_improvement,
        )

        results.append(
            result
        )

        status = result.get(
            "status"
        )

        if status == "PROPOSAL_READY":

            if result.get(
                "proposal"
            ):
                proposals.append(
                    result[
                        "proposal"
                    ]
                )

        elif status == "NO_CHANGE_REQUIRED":

            no_change.append(
                result
            )

        elif status == "INVALID_CUSTOMER":

            invalid.append(
                result
            )

        else:

            if result.get(
                "proposal"
            ):
                proposals.append(
                    result[
                        "proposal"
                    ]
                )

    return {
        "optimizer_version": (
            OPTIMIZER_VERSION
        ),

        "affected_customer_count": (
            len(
                selected_customers
            )
        ),

        "result_count": len(
            results
        ),

        "proposal_count": len(
            proposals
        ),

        "proposals": proposals,

        "results": results,

        "no_change_count": len(
            no_change
        ),

        "invalid_count": len(
            invalid
        ),

        "requires_user_approval": (
            bool(
                proposals
            )
        ),

        "assignment_changed": False,

        "write_performed": False,
    }


# ============================================================================
# ROUTE REBALANCE PLAN
# ============================================================================

def optimize_rebalance_plan(
    customers: List[Dict[str, Any]],
    routes: List[Dict[str, Any]],
    affected_customer_names: Optional[
        List[str]
    ] = None,
    routing_engine: Optional[
        RoutingEngine
    ] = None,
    min_improvement: float = (
        DEFAULT_MIN_IMPROVEMENT
    ),
) -> Dict[str, Any]:
    """
    High-level entry point for route optimization.

    Returns a proposal-only optimization plan.

    No ERPNext document is changed.
    """

    return optimize_customers(
        customers=customers,
        routes=routes,
        affected_customer_names=(
            affected_customer_names
        ),
        routing_engine=routing_engine,
        min_improvement=min_improvement,
    )


# ============================================================================
# PROPOSAL SUMMARY
# ============================================================================

def summarize_optimization(
    optimization_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a compact deterministic summary suitable for
    the UI/API layer.
    """

    proposals = (
        optimization_result.get(
            "proposals",
            [],
        )
    )

    summary = []

    for proposal in proposals:

        customer = proposal.get(
            "customer",
            {},
        )

        from_route = proposal.get(
            "from_route"
        )

        to_route = proposal.get(
            "to_route"
        )

        summary.append(
            {
                "customer": (
                    customer.get(
                        "customer_name"
                    )
                    or customer.get(
                        "name"
                    )
                ),
                "customer_id": (
                    customer.get(
                        "name"
                    )
                ),
                "from_route": (
                    from_route
                ),
                "to_route": (
                    route_key(
                        to_route
                    )
                    if isinstance(
                        to_route,
                        dict,
                    )
                    else to_route
                ),
                "improvement": (
                    proposal.get(
                        "improvement"
                    )
                ),
                "incremental_distance_km": (
                    proposal.get(
                        "incremental_distance_km"
                    )
                ),
                "estimated_duration_min": (
                    proposal.get(
                        "estimated_duration_min"
                    )
                ),
                "requires_user_approval": (
                    True
                ),
                "assignment_changed": (
                    False
                ),
            }
        )

    return {
        "optimizer_version": (
            optimization_result.get(
                "optimizer_version",
                OPTIMIZER_VERSION,
            )
        ),
        "affected_customer_count": (
            optimization_result.get(
                "affected_customer_count",
                0,
            )
        ),
        "proposal_count": len(
            summary
        ),
        "proposals": summary,
        "requires_user_approval": bool(
            summary
        ),
        "assignment_changed": False,
        "write_performed": False,
    }

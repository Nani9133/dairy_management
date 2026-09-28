"""
Route Optimization Engine
Route Rebalancer.

Generates proposed customer movements between routes.

IMPORTANT:
    This module does NOT modify ERPNext documents.

The rebalancer is responsible for evaluating:
    - affected customers
    - candidate routes
    - route stability
    - geographic impact
    - route distance
    - route travel time
    - capacity hooks

Actual ERPNext assignment changes must happen only
after explicit user approval.
"""

from typing import Any, Dict, List, Optional

from .constraints import (
    check_customer_for_route,
)
from .sequencing import (
    RoutingEngine,
    rank_road_insertion_candidates,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_STABILITY_PENALTY = 10.0
DEFAULT_ROUTE_CHANGE_PENALTY = 10.0
DEFAULT_DISTANCE_WEIGHT = 1.0
DEFAULT_TIME_WEIGHT = 0.25


# ============================================================================
# NORMALIZATION
# ============================================================================

def normalize_customer(
    customer: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize customer data used by the rebalancer.

    GPS coordinates are preserved exactly as supplied.
    """

    return {
        "name": customer.get("name"),
        "customer_name": customer.get("customer_name"),
        "latitude": customer.get("latitude"),
        "longitude": customer.get("longitude"),
        "route": customer.get("route"),
        "pickpoint__warehouse": customer.get(
            "pickpoint__warehouse"
        ),
        "state": customer.get("state"),
        "city": customer.get("city"),
        "zone": customer.get("zone"),
        "area": customer.get("area"),
        "point": customer.get("point"),
    }


def normalize_route(
    route: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize route data.

    Capacity fields are optional because the current
    Route DocType does not yet provide the complete
    vehicle/capacity model required by the future
    optimization layer.
    """

    return {
        "name": route.get("name"),
        "route_name": route.get("route_name"),
        "route_id": route.get("route_id"),
        "route_type": route.get("route_type"),
        "route_status": route.get("route_status"),
        "point_name": route.get("point_name"),
        "boundary_geojson": route.get(
            "boundary_geojson"
        ),

        # Optional future capacity information.
        "capacity": route.get("capacity"),
        "current_load": route.get("current_load"),
        "capacity_unit": route.get(
            "capacity_unit"
        ),
    }


# ============================================================================
# ROUTE HELPERS
# ============================================================================

def route_key(
    route: Dict[str, Any],
) -> Optional[str]:
    """
    Return the stable route identifier.
    """

    return (
        route.get("name")
        or route.get("route_name")
        or route.get("route_id")
    )


def customer_current_route(
    customer: Dict[str, Any],
) -> Optional[str]:
    """
    Return the customer's current route.
    """

    return customer.get("route")


def is_same_route(
    customer: Dict[str, Any],
    route: Dict[str, Any],
) -> bool:
    """
    Determine whether a route is the customer's
    current route.
    """

    current_route = (
        customer_current_route(customer)
    )

    candidate_route = route_key(route)

    if not current_route or not candidate_route:
        return False

    return str(current_route) == str(
        candidate_route
    )


# ============================================================================
# CAPACITY
# ============================================================================

def check_route_capacity(
    route: Dict[str, Any],
    additional_load: float = 1.0,
) -> Dict[str, Any]:
    """
    Check whether a route can accept additional load.

    Current Route records may not yet contain capacity
    information. Therefore, missing capacity is treated
    as an unresolved constraint rather than silently
    assuming unlimited capacity.

    Future vehicle/order integration can provide:

        capacity
        current_load
        capacity_unit
    """

    capacity = route.get("capacity")
    current_load = route.get(
        "current_load"
    )

    # ------------------------------------------------------------
    # Capacity information not available
    # ------------------------------------------------------------

    if capacity is None:
        return {
            "known": False,
            "feasible": True,
            "reason": (
                "Route capacity is not currently configured"
            ),
        }

    try:
        capacity = float(capacity)
    except (TypeError, ValueError):
        return {
            "known": False,
            "feasible": False,
            "reason": (
                "Route capacity is invalid"
            ),
        }

    if current_load is None:
        current_load = 0.0

    try:
        current_load = float(
            current_load
        )
    except (TypeError, ValueError):
        return {
            "known": False,
            "feasible": False,
            "reason": (
                "Route current load is invalid"
            ),
        }

    projected_load = (
        current_load
        + float(additional_load)
    )

    feasible = (
        projected_load <= capacity
    )

    return {
        "known": True,
        "feasible": feasible,
        "capacity": capacity,
        "current_load": current_load,
        "projected_load": projected_load,
        "remaining_capacity": max(
            0.0,
            capacity - projected_load,
        ),
        "reason": (
            None
            if feasible
            else "Route capacity exceeded"
        ),
    }


# ============================================================================
# AFFECTED CUSTOMERS
# ============================================================================

def find_affected_customers(
    customers: List[Dict[str, Any]],
    affected_customer_names: Optional[
        List[str]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Return customers affected by a route/boundary change.

    If affected_customer_names is supplied, only those
    customers are returned.

    If it is not supplied, all supplied customers are
    considered affected.

    This function does not modify customer data.
    """

    if not affected_customer_names:
        return list(customers)

    affected_set = {
        str(name)
        for name in affected_customer_names
    }

    return [
        customer
        for customer in customers
        if str(
            customer.get("name")
        ) in affected_set
        or str(
            customer.get("customer_name")
        ) in affected_set
    ]


# ============================================================================
# CANDIDATE ROUTES
# ============================================================================

def get_eligible_routes(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return active routes that satisfy the current
    deterministic route constraints.
    """

    eligible = []

    for route in routes:

        normalized_route = normalize_route(
            route
        )

        constraint_result = (
            check_customer_for_route(
                customer,
                normalized_route,
            )
        )

        if not constraint_result.feasible:
            continue

        capacity_result = (
            check_route_capacity(
                normalized_route
            )
        )

        if not capacity_result["feasible"]:
            continue

        eligible.append(
            normalized_route
        )

    return eligible


# ============================================================================
# ROUTE CUSTOMER GROUPING
# ============================================================================

def customers_for_route(
    customers: List[Dict[str, Any]],
    route: Dict[str, Any],
    exclude_customer: Optional[
        Dict[str, Any]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Return customers currently assigned to a route.

    A customer being evaluated for movement can be
    excluded from the existing sequence.
    """

    route_identifier = route_key(
        route
    )

    results = []

    excluded_name = None

    if exclude_customer:
        excluded_name = (
            exclude_customer.get("name")
        )

    for customer in customers:

        if (
            customer.get("route")
            != route_identifier
        ):
            continue

        if (
            excluded_name
            and customer.get("name")
            == excluded_name
        ):
            continue

        results.append(
            customer
        )

    return results


# ============================================================================
# ROUTE MOVEMENT PROPOSAL
# ============================================================================

def evaluate_route_move(
    customer: Dict[str, Any],
    target_route: Dict[str, Any],
    customers: List[Dict[str, Any]],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
    stability_penalty: float = (
        DEFAULT_STABILITY_PENALTY
    ),
    route_change_penalty: float = (
        DEFAULT_ROUTE_CHANGE_PENALTY
    ),
) -> Dict[str, Any]:
    """
    Evaluate moving one customer into a target route.

    This produces a proposal only.

    No ERPNext document is changed.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    normalized_customer = normalize_customer(
        customer
    )

    normalized_route = normalize_route(
        target_route
    )

    route_identifier = route_key(
        normalized_route
    )

    # ------------------------------------------------------------
    # Basic constraints
    # ------------------------------------------------------------

    constraint_result = (
        check_customer_for_route(
            normalized_customer,
            normalized_route,
        )
    )

    if not constraint_result.feasible:

        return {
            "feasible": False,
            "customer": normalized_customer,
            "target_route": normalized_route,
            "violations": (
                constraint_result.violations
            ),
        }

    # ------------------------------------------------------------
    # Capacity
    # ------------------------------------------------------------

    capacity_result = (
        check_route_capacity(
            normalized_route
        )
    )

    if not capacity_result["feasible"]:

        return {
            "feasible": False,
            "customer": normalized_customer,
            "target_route": normalized_route,
            "violations": [
                capacity_result["reason"]
            ],
        }

    # ------------------------------------------------------------
    # Existing target route customers
    # ------------------------------------------------------------

    target_customers = customers_for_route(
        customers,
        normalized_route,
        exclude_customer=customer,
    )

    # ------------------------------------------------------------
    # Current route status
    # ------------------------------------------------------------

    current_route = (
        customer_current_route(
            normalized_customer
        )
    )

    same_route = (
        str(current_route)
        == str(route_identifier)
        if current_route
        and route_identifier
        else False
    )

    # ------------------------------------------------------------
    # Candidate insertion
    # ------------------------------------------------------------

    insertion_candidates = (
        rank_road_insertion_candidates(
            target_customers,
            normalized_customer,
            routing,
        )
    )

    if not insertion_candidates:

        return {
            "feasible": False,
            "customer": normalized_customer,
            "target_route": normalized_route,
            "violations": [
                "No insertion position available"
            ],
        }

    best_insertion = (
        insertion_candidates[0]
    )

    # ------------------------------------------------------------
    # Objective components
    # ------------------------------------------------------------

    incremental_distance = (
        best_insertion.get(
            "incremental_distance_km"
        )
    )

    duration_min = (
        best_insertion.get(
            "duration_min"
        )
    )

    if incremental_distance is None:
        return {
            "feasible": False,
            "customer": normalized_customer,
            "target_route": normalized_route,
            "violations": [
                "Unable to calculate route distance"
            ],
        }

    distance_cost = (
        incremental_distance
        * DEFAULT_DISTANCE_WEIGHT
    )

    time_cost = (
        (
            duration_min
            * DEFAULT_TIME_WEIGHT
        )
        if duration_min is not None
        else 0.0
    )

    # ------------------------------------------------------------
    # Stability
    # ------------------------------------------------------------

    stability_cost = 0.0

    if not same_route:
        stability_cost = (
            stability_penalty
        )

    route_change_cost = 0.0

    if not same_route:
        route_change_cost = (
            route_change_penalty
        )

    # ------------------------------------------------------------
    # Total score
    # ------------------------------------------------------------

    total_score = (
        distance_cost
        + time_cost
        + stability_cost
        + route_change_cost
    )

    return {
        "feasible": True,

        "customer": normalized_customer,

        "current_route": current_route,

        "target_route": normalized_route,

        "route_change": not same_route,

        "proposed_sequence_position": (
            best_insertion.get(
                "position"
            )
        ),

        "proposed_sequence": (
            best_insertion.get(
                "sequence"
            )
        ),

        "incremental_distance_km": (
            incremental_distance
        ),

        "total_route_distance_km": (
            best_insertion.get(
                "total_distance_km"
            )
        ),

        "estimated_duration_min": (
            duration_min
        ),

        "routing_provider": (
            best_insertion.get(
                "provider"
            )
        ),

        "distance_cost": distance_cost,

        "time_cost": time_cost,

        "stability_cost": stability_cost,

        "route_change_cost": route_change_cost,

        "total_score": total_score,

        "capacity": capacity_result,

        "insertion_candidates": (
            insertion_candidates
        ),

        "violations": [],
    }


# ============================================================================
# CUSTOMER REBALANCING
# ============================================================================

def generate_customer_rebalance_proposals(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
    customers: List[Dict[str, Any]],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> Dict[str, Any]:
    """
    Generate route movement proposals for one customer.

    The current route is retained as information.

    No assignment is changed.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    normalized_customer = normalize_customer(
        customer
    )

    current_route = (
        normalized_customer.get(
            "route"
        )
    )

    eligible_routes = get_eligible_routes(
        normalized_customer,
        routes,
    )

    proposals = []
    rejected_routes = []

    for route in eligible_routes:

        route_identifier = route_key(
            route
        )

        # --------------------------------------------------------
        # Evaluate candidate
        # --------------------------------------------------------

        proposal = evaluate_route_move(
            normalized_customer,
            route,
            customers,
            routing,
        )

        if proposal["feasible"]:

            proposals.append(
                proposal
            )

        else:

            rejected_routes.append(
                {
                    "route": route,
                    "violations": (
                        proposal.get(
                            "violations",
                            [],
                        )
                    ),
                }
            )

    # ------------------------------------------------------------
    # Sort proposals by deterministic score
    # ------------------------------------------------------------

    proposals.sort(
        key=lambda proposal: (
            proposal.get(
                "total_score"
            )
            if proposal.get(
                "total_score"
            ) is not None
            else float("inf"),
            proposal.get(
                "incremental_distance_km"
            )
            if proposal.get(
                "incremental_distance_km"
            ) is not None
            else float("inf"),
        )
    )

    for rank, proposal in enumerate(
        proposals,
        start=1,
    ):
        proposal["rank"] = rank

    return {
        "customer": normalized_customer,

        "current_route": current_route,

        "candidate_route_count": (
            len(eligible_routes)
        ),

        "proposal_count": (
            len(proposals)
        ),

        "proposals": proposals,

        "rejected_routes": rejected_routes,

        "requires_user_approval": True,

        "assignment_changed": False,
    }


# ============================================================================
# MULTI-CUSTOMER REBALANCING
# ============================================================================

def generate_rebalance_plan(
    customers: List[Dict[str, Any]],
    routes: List[Dict[str, Any]],
    affected_customer_names: Optional[
        List[str]
    ] = None,
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> Dict[str, Any]:
    """
    Generate a complete proposed rebalance plan.

    This is the main entry point for the rebalancer.

    IMPORTANT:

        This function NEVER changes ERPNext data.

    It only produces proposals for later approval.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    affected_customers = (
        find_affected_customers(
            customers,
            affected_customer_names,
        )
    )

    customer_plans = []

    for customer in affected_customers:

        plan = (
            generate_customer_rebalance_proposals(
                customer,
                routes,
                customers,
                routing,
            )
        )

        customer_plans.append(
            plan
        )

    proposed_changes = []

    for plan in customer_plans:

        proposals = plan.get(
            "proposals",
            [],
        )

        if not proposals:
            continue

        best = proposals[0]

        # --------------------------------------------------------
        # Only report actual route movement as a proposed change.
        # --------------------------------------------------------

        if best.get(
            "route_change"
        ):

            proposed_changes.append(
                {
                    "customer": best[
                        "customer"
                    ],

                    "from_route": best[
                        "current_route"
                    ],

                    "to_route": best[
                        "target_route"
                    ],

                    "sequence_position": best[
                        "proposed_sequence_position"
                    ],

                    "incremental_distance_km": best[
                        "incremental_distance_km"
                    ],

                    "estimated_duration_min": best[
                        "estimated_duration_min"
                    ],

                    "routing_provider": best[
                        "routing_provider"
                    ],

                    "score": best[
                        "total_score"
                    ],

                    "requires_user_approval": True,
                }
            )

    return {
        "affected_customer_count": (
            len(affected_customers)
        ),

        "customer_plans": customer_plans,

        "proposed_change_count": (
            len(proposed_changes)
        ),

        "proposed_changes": (
            proposed_changes
        ),

        "requires_user_approval": True,

        "assignment_changed": False,
    }

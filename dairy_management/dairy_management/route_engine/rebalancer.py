"""
Route Optimization Engine
Route Rebalancer.

Proposal-only route rebalancing.

IMPORTANT:
    This module NEVER modifies ERPNext documents.

Responsibilities:
    1. Treat the customer's current route as the baseline.
    2. Evaluate other eligible routes as alternatives.
    3. Check route feasibility and capacity.
    4. Find the best sequence insertion position.
    5. Calculate the candidate objective.
    6. Compare candidate objective against the baseline.
    7. Propose a route change only when there is a
       meaningful improvement after stability penalties.

The final route assignment must require explicit user approval.
"""

from typing import Any, Dict, List, Optional

from .constraints import check_customer_for_route
from .sequencing import (
    RoutingEngine,
    rank_road_insertion_candidates,
)


# ============================================================================
# DEFAULT OPTIMIZATION WEIGHTS
# ============================================================================

DEFAULT_STABILITY_PENALTY = 10.0
DEFAULT_ROUTE_CHANGE_PENALTY = 10.0

DEFAULT_DISTANCE_WEIGHT = 1.0
DEFAULT_TIME_WEIGHT = 0.25

# Minimum objective improvement required before proposing
# a route change.
#
# Example:
#
# baseline score = 10
# candidate score = 9.8
#
# improvement = 0.2
#
# If threshold = 1.0, this is NOT enough to move the customer.
DEFAULT_MIN_IMPROVEMENT = 1.0


# ============================================================================
# NORMALIZATION
# ============================================================================

def normalize_customer(
    customer: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize customer information used by the route engine.
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
    Normalize route information used by the route engine.
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

        # Capacity fields are intentionally optional.
        # They can be connected to the actual vehicle/
        # route capacity model later.
        "capacity": route.get("capacity"),
        "current_load": route.get("current_load"),
        "capacity_unit": route.get(
            "capacity_unit"
        ),
    }


# ============================================================================
# IDENTIFIERS
# ============================================================================

def route_key(
    route: Dict[str, Any],
) -> Optional[str]:
    """
    Return the primary route identifier.
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
    Determine whether the candidate route is the customer's
    current route.
    """

    current_route = customer_current_route(
        customer
    )

    candidate_route = route_key(
        route
    )

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

    Capacity is optional at this stage.

    If capacity is not configured, the route remains
    feasible but the result clearly reports that capacity
    is unknown.
    """

    capacity = route.get(
        "capacity"
    )

    current_load = route.get(
        "current_load"
    )

    if capacity is None:
        return {
            "known": False,
            "feasible": True,
            "reason": (
                "Route capacity is not currently configured"
            ),
        }

    try:
        capacity = float(
            capacity
        )

    except (
        TypeError,
        ValueError,
    ):
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

    except (
        TypeError,
        ValueError,
    ):
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
# CUSTOMER FILTERING
# ============================================================================

def find_affected_customers(
    customers: List[Dict[str, Any]],
    affected_customer_names: Optional[
        List[str]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Return only affected customers when a specific
    customer list is supplied.

    If no list is supplied, all customers are considered.
    """

    if not affected_customer_names:
        return list(
            customers
        )

    affected_set = {
        str(name)
        for name in affected_customer_names
    }

    return [
        customer
        for customer in customers
        if (
            str(customer.get("name"))
            in affected_set
            or str(
                customer.get(
                    "customer_name"
                )
            )
            in affected_set
        )
    ]


def customers_for_route(
    customers: List[Dict[str, Any]],
    route: Dict[str, Any],
    exclude_customer: Optional[
        Dict[str, Any]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Return customers currently assigned to a route.

    The affected customer itself is excluded when supplied.
    """

    route_identifier = route_key(
        route
    )

    excluded_name = None

    if exclude_customer:
        excluded_name = (
            exclude_customer.get(
                "name"
            )
        )

    results = []

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
# ROUTE ELIGIBILITY
# ============================================================================

def get_eligible_routes(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return routes that satisfy the basic feasibility
    and capacity checks.
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

        if not capacity_result[
            "feasible"
        ]:
            continue

        eligible.append(
            normalized_route
        )

    return eligible


# ============================================================================
# ROUTE OBJECTIVE
# ============================================================================

def calculate_route_objective(
    incremental_distance_km: Optional[
        float
    ],
    duration_min: Optional[
        float
    ],
    route_change: bool,
    stability_penalty: float = (
        DEFAULT_STABILITY_PENALTY
    ),
    route_change_penalty: float = (
        DEFAULT_ROUTE_CHANGE_PENALTY
    ),
) -> Dict[str, float]:
    """
    Calculate the deterministic objective components
    for a candidate route.

    Lower total score is better.

    Objective:

        distance cost
        + travel time cost
        + stability penalty
        + route change penalty
    """

    if incremental_distance_km is None:
        raise ValueError(
            "Incremental distance is required"
        )

    distance_cost = (
        float(
            incremental_distance_km
        )
        * DEFAULT_DISTANCE_WEIGHT
    )

    time_cost = 0.0

    if duration_min is not None:
        time_cost = (
            float(duration_min)
            * DEFAULT_TIME_WEIGHT
        )

    stability_cost = (
        0.0
        if not route_change
        else float(
            stability_penalty
        )
    )

    route_change_cost = (
        0.0
        if not route_change
        else float(
            route_change_penalty
        )
    )

    total_score = (
        distance_cost
        + time_cost
        + stability_cost
        + route_change_cost
    )

    return {
        "distance_cost": distance_cost,
        "time_cost": time_cost,
        "stability_cost": stability_cost,
        "route_change_cost": route_change_cost,
        "total_score": total_score,
    }


# ============================================================================
# ROUTE EVALUATION
# ============================================================================

def evaluate_route(
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
    Evaluate a customer against a route.

    This function works for both:

        1. Current route / baseline
        2. Candidate reassignment route

    It does NOT modify any ERPNext document.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    normalized_customer = (
        normalize_customer(
            customer
        )
    )

    normalized_route = (
        normalize_route(
            target_route
        )
    )

    route_identifier = route_key(
        normalized_route
    )

    # ------------------------------------------------------------------
    # Basic feasibility
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Capacity
    # ------------------------------------------------------------------

    capacity_result = (
        check_route_capacity(
            normalized_route
        )
    )

    if not capacity_result[
        "feasible"
    ]:

        return {
            "feasible": False,
            "customer": normalized_customer,
            "target_route": normalized_route,
            "violations": [
                capacity_result[
                    "reason"
                ]
            ],
        }

    # ------------------------------------------------------------------
    # Existing route customers
    # ------------------------------------------------------------------

    target_customers = (
        customers_for_route(
            customers,
            normalized_route,
            exclude_customer=customer,
        )
    )

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

    # ------------------------------------------------------------------
    # Sequence insertion
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Objective
    # ------------------------------------------------------------------

    objective = (
        calculate_route_objective(
            incremental_distance_km=(
                incremental_distance
            ),
            duration_min=duration_min,
            route_change=(
                not same_route
            ),
            stability_penalty=(
                stability_penalty
            ),
            route_change_penalty=(
                route_change_penalty
            ),
        )
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

        "distance_cost": (
            objective[
                "distance_cost"
            ]
        ),

        "time_cost": (
            objective[
                "time_cost"
            ]
        ),

        "stability_cost": (
            objective[
                "stability_cost"
            ]
        ),

        "route_change_cost": (
            objective[
                "route_change_cost"
            ]
        ),

        "total_score": (
            objective[
                "total_score"
            ]
        ),

        "capacity": (
            capacity_result
        ),

        "insertion_candidates": (
            insertion_candidates
        ),

        "violations": [],
    }


# ============================================================================
# BASELINE + CANDIDATES
# ============================================================================

def generate_customer_rebalance_proposals(
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
    Evaluate the customer's current route as the baseline
    and other eligible routes as reassignment candidates.

    IMPORTANT:

        The current route is NOT treated as a proposed
        route change.

    A route change is proposed only when an alternative
    route improves the objective by at least
    ``min_improvement``.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    normalized_customer = (
        normalize_customer(
            customer
        )
    )

    current_route_name = (
        normalized_customer.get(
            "route"
        )
    )

    eligible_routes = (
        get_eligible_routes(
            normalized_customer,
            routes,
        )
    )

    baseline = None
    candidate_evaluations = []
    rejected_routes = []

    # ------------------------------------------------------------------
    # Evaluate current route
    # ------------------------------------------------------------------

    for route in eligible_routes:

        if not is_same_route(
            normalized_customer,
            route,
        ):
            continue

        baseline = evaluate_route(
            normalized_customer,
            route,
            customers,
            routing,
        )

        break

    # ------------------------------------------------------------------
    # If current route is not available
    # ------------------------------------------------------------------

    if baseline is None:

        return {
            "customer": normalized_customer,

            "current_route": current_route_name,

            "baseline": None,

            "candidate_route_count": 0,

            "candidate_count": 0,

            "proposal_count": 0,

            "proposals": [],

            "candidate_evaluations": [],

            "rejected_routes": [],

            "requires_user_approval": False,

            "assignment_changed": False,

            "status": (
                "CURRENT_ROUTE_NOT_ELIGIBLE"
            ),

            "message": (
                "Customer current route is "
                "not available as an eligible "
                "baseline route."
            ),
        }

    baseline_score = baseline.get(
        "total_score"
    )

    # ------------------------------------------------------------------
    # Evaluate alternative routes
    # ------------------------------------------------------------------

    for route in eligible_routes:

        if is_same_route(
            normalized_customer,
            route,
        ):
            continue

        evaluation = evaluate_route(
            normalized_customer,
            route,
            customers,
            routing,
        )

        if not evaluation.get(
            "feasible"
        ):

            rejected_routes.append(
                {
                    "route": route,
                    "violations": (
                        evaluation.get(
                            "violations",
                            [],
                        )
                    ),
                }
            )

            continue

        candidate_score = (
            evaluation.get(
                "total_score"
            )
        )

        improvement = (
            float(
                baseline_score
            )
            - float(
                candidate_score
            )
        )

        evaluation[
            "baseline_score"
        ] = baseline_score

        evaluation[
            "improvement"
        ] = improvement

        evaluation[
            "improvement_threshold"
        ] = min_improvement

        evaluation[
            "meaningful_improvement"
        ] = (
            improvement
            >= float(
                min_improvement
            )
        )

        candidate_evaluations.append(
            evaluation
        )

    # ------------------------------------------------------------------
    # Rank alternative routes
    # ------------------------------------------------------------------

    candidate_evaluations.sort(
        key=lambda candidate: (
            -float(
                candidate.get(
                    "improvement",
                    float("-inf"),
                )
            ),
            float(
                candidate.get(
                    "total_score",
                    float("inf"),
                )
            ),
        )
    )

    for rank, candidate in enumerate(
        candidate_evaluations,
        start=1,
    ):
        candidate[
            "candidate_rank"
        ] = rank

    # ------------------------------------------------------------------
    # Generate proposal only when improvement
    # is meaningful
    # ------------------------------------------------------------------

    proposals = []

    for candidate in (
        candidate_evaluations
    ):

        if not candidate.get(
            "meaningful_improvement"
        ):
            continue

        proposals.append(
            {
                "customer": candidate[
                    "customer"
                ],

                "from_route": (
                    candidate[
                        "current_route"
                    ]
                ),

                "to_route": (
                    candidate[
                        "target_route"
                    ]
                ),

                "sequence_position": (
                    candidate[
                        "proposed_sequence_position"
                    ]
                ),

                "proposed_sequence": (
                    candidate[
                        "proposed_sequence"
                    ]
                ),

                "incremental_distance_km": (
                    candidate[
                        "incremental_distance_km"
                    ]
                ),

                "estimated_duration_min": (
                    candidate[
                        "estimated_duration_min"
                    ]
                ),

                "routing_provider": (
                    candidate[
                        "routing_provider"
                    ]
                ),

                "baseline_score": (
                    baseline_score
                ),

                "candidate_score": (
                    candidate[
                        "total_score"
                    ]
                ),

                "improvement": (
                    candidate[
                        "improvement"
                    ]
                ),

                "requires_user_approval": True,

                "assignment_changed": False,
            }
        )

    return {
        "customer": normalized_customer,

        "current_route": current_route_name,

        "baseline": baseline,

        "candidate_route_count": len(
            candidate_evaluations
        ),

        "candidate_count": len(
            candidate_evaluations
        ),

        "proposal_count": len(
            proposals
        ),

        "proposals": proposals,

        "candidate_evaluations": (
            candidate_evaluations
        ),

        "rejected_routes": (
            rejected_routes
        ),

        "requires_user_approval": (
            bool(proposals)
        ),

        "assignment_changed": False,

        "status": (
            "PROPOSAL_READY"
            if proposals
            else "NO_ROUTE_CHANGE_REQUIRED"
        ),
    }


# ============================================================================
# MULTI-CUSTOMER REBALANCE PLAN
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
    min_improvement: float = (
        DEFAULT_MIN_IMPROVEMENT
    ),
) -> Dict[str, Any]:
    """
    Generate a proposal-only rebalancing plan.

    No ERPNext records are changed.
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
                customer=customer,
                routes=routes,
                customers=customers,
                routing_engine=routing,
                min_improvement=(
                    min_improvement
                ),
            )
        )

        customer_plans.append(
            plan
        )

    proposed_changes = []

    for plan in customer_plans:

        for proposal in plan.get(
            "proposals",
            [],
        ):

            proposed_changes.append(
                proposal
            )

    return {
        "affected_customer_count": (
            len(
                affected_customers
            )
        ),

        "customer_plans": (
            customer_plans
        ),

        "proposed_change_count": (
            len(
                proposed_changes
            )
        ),

        "proposed_changes": (
            proposed_changes
        ),

        "requires_user_approval": (
            bool(
                proposed_changes
            )
        ),

        "assignment_changed": False,
    }

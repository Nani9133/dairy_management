"""
Route Optimization Engine
Route assignment utilities.

This module determines candidate routes for customers.
It does NOT modify ERPNext documents.
"""

from typing import Any, Dict, List, Optional

from .constraints import check_customer_for_route


def normalize_route(route: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize route data so the assignment engine can work
    with either ERPNext records or plain dictionaries.
    """

    return {
        "name": route.get("name"),
        "route_name": route.get("route_name"),
        "route_id": route.get("route_id"),
        "route_type": route.get("route_type"),
        "route_status": route.get("route_status"),
        "point_name": route.get("point_name"),
        "boundary_geojson": route.get("boundary_geojson"),
    }


def find_candidate_routes(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return routes that are currently feasible candidates
    for the customer.

    No ERPNext data is modified.
    """

    candidates = []

    for route in routes:
        normalized_route = normalize_route(route)

        result = check_customer_for_route(
            customer,
            normalized_route,
        )

        if result.feasible:
            candidates.append({
                **normalized_route,
                "eligible": True,
                "violations": [],
            })

    return candidates


def find_ineligible_routes(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return routes that cannot currently accept the customer,
    including the reason.
    """

    ineligible = []

    for route in routes:
        normalized_route = normalize_route(route)

        result = check_customer_for_route(
            customer,
            normalized_route,
        )

        if not result.feasible:
            ineligible.append({
                **normalized_route,
                "eligible": False,
                "violations": result.violations,
            })

    return ineligible


def get_route_assignment_candidates(
    customer: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Produce a complete assignment-candidate result.

    This is proposal data only.
    It does not update Customer or Route.
    """

    candidates = find_candidate_routes(
        customer,
        routes,
    )

    ineligible = find_ineligible_routes(
        customer,
        routes,
    )

    return {
        "customer": {
            "name": customer.get("name"),
            "customer_name": customer.get("customer_name"),
            "latitude": customer.get("latitude"),
            "longitude": customer.get("longitude"),
        },
        "candidate_routes": candidates,
        "ineligible_routes": ineligible,
        "candidate_count": len(candidates),
        "ineligible_count": len(ineligible),
    }

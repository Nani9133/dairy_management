"""
Route Optimization Engine
Constraint and feasibility utilities.

This module contains deterministic checks used by the route optimizer.
It does not modify ERPNext documents.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ConstraintResult:
    """
    Result of a constraint check.
    """

    feasible: bool
    violations: List[str]

    @property
    def reason(self) -> str:
        return "; ".join(self.violations)


def check_required_location(customer: Dict[str, Any]) -> ConstraintResult:
    """
    Check whether a customer has valid GPS coordinates.

    Customer GPS coordinates are treated as fixed input.
    The optimizer must never modify them.
    """

    violations = []

    latitude = customer.get("latitude")
    longitude = customer.get("longitude")

    if latitude is None:
        violations.append("Customer latitude is missing")

    if longitude is None:
        violations.append("Customer longitude is missing")

    if latitude is not None:
        try:
            latitude = float(latitude)

            if latitude < -90 or latitude > 90:
                violations.append("Customer latitude is outside valid range")
        except (TypeError, ValueError):
            violations.append("Customer latitude is invalid")

    if longitude is not None:
        try:
            longitude = float(longitude)

            if longitude < -180 or longitude > 180:
                violations.append("Customer longitude is outside valid range")
        except (TypeError, ValueError):
            violations.append("Customer longitude is invalid")

    return ConstraintResult(
        feasible=not violations,
        violations=violations,
    )


def check_route_status(route: Dict[str, Any]) -> ConstraintResult:
    """
    Check whether a route is currently eligible for optimization.
    """

    violations = []

    status = str(route.get("route_status") or "").strip()

    if status.lower() != "active":
        violations.append(
            f"Route is not active: {status or 'unknown'}"
        )

    return ConstraintResult(
        feasible=not violations,
        violations=violations,
    )


def check_customer_for_route(
    customer: Dict[str, Any],
    route: Dict[str, Any],
) -> ConstraintResult:
    """
    Basic deterministic feasibility check for assigning a customer
    to a route.

    This intentionally does NOT check vehicle/order capacity yet,
    because those belong to modules that are being developed
    separately.
    """

    violations = []

    location_result = check_required_location(customer)

    if not location_result.feasible:
        violations.extend(location_result.violations)

    route_result = check_route_status(route)

    if not route_result.feasible:
        violations.extend(route_result.violations)

    return ConstraintResult(
        feasible=not violations,
        violations=violations,
    )


def validate_route_customers(
    customers: List[Dict[str, Any]],
    route: Dict[str, Any],
) -> ConstraintResult:
    """
    Validate all customers currently considered for a route.
    """

    violations = []

    route_result = check_route_status(route)

    if not route_result.feasible:
        violations.extend(route_result.violations)

    for customer in customers:
        customer_name = (
            customer.get("customer_name")
            or customer.get("name")
            or "Unknown Customer"
        )

        result = check_required_location(customer)

        if not result.feasible:
            for violation in result.violations:
                violations.append(
                    f"{customer_name}: {violation}"
                )

    return ConstraintResult(
        feasible=not violations,
        violations=violations,
    )


def can_assign_customer(
    customer: Dict[str, Any],
    route: Dict[str, Any],
) -> bool:
    """
    Simple boolean helper used by the assignment engine.
    """

    return check_customer_for_route(
        customer,
        route,
    ).feasible

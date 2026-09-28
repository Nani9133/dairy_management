"""
Route Optimization Engine
Auto Sequence Engine.

Generates possible customer insertion positions and evaluates
geographic or road-based insertion cost.

Routing priority:

1. OSRM road distance + travel time when available
2. Haversine distance fallback when OSRM is unavailable

This module does NOT modify ERPNext documents.
"""

from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional

from .routing.osrm import OSRMClient


EARTH_RADIUS_KM = 6371.0088


# ============================================================================
# BASIC GEOGRAPHIC FUNCTIONS
# ============================================================================

def haversine_distance(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    """
    Calculate straight-line distance between two GPS points.

    Returns:
        Distance in kilometres.
    """

    lat1 = radians(float(latitude1))
    lon1 = radians(float(longitude1))

    lat2 = radians(float(latitude2))
    lon2 = radians(float(longitude2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a),
    )

    return EARTH_RADIUS_KM * c


def stop_has_location(
    stop: Dict[str, Any],
) -> bool:
    """
    Check whether a stop has valid GPS coordinates.
    """

    latitude = stop.get("latitude")
    longitude = stop.get("longitude")

    if latitude is None or longitude is None:
        return False

    try:
        latitude = float(latitude)
        longitude = float(longitude)

    except (TypeError, ValueError):
        return False

    return (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def distance_between_stops(
    stop_a: Dict[str, Any],
    stop_b: Dict[str, Any],
) -> Optional[float]:
    """
    Calculate straight-line geographic distance between two stops.

    Returns:
        Distance in kilometres.

    Returns None when either stop does not have valid GPS.
    """

    if not stop_has_location(stop_a):
        return None

    if not stop_has_location(stop_b):
        return None

    return haversine_distance(
        stop_a["latitude"],
        stop_a["longitude"],
        stop_b["latitude"],
        stop_b["longitude"],
    )


def sequence_distance(
    stops: List[Dict[str, Any]],
) -> Optional[float]:
    """
    Calculate total straight-line geographic distance between
    consecutive stops.

    This function intentionally remains Haversine-based.

    OSRM road distance is handled separately by RoutingEngine.
    """

    if len(stops) <= 1:
        return 0.0

    total_distance = 0.0

    for index in range(len(stops) - 1):

        distance = distance_between_stops(
            stops[index],
            stops[index + 1],
        )

        if distance is None:
            return None

        total_distance += distance

    return total_distance


# ============================================================================
# ROUTING ENGINE
# ============================================================================

class RoutingEngine:
    """
    Routing abstraction used by the sequence optimizer.

    Preferred routing provider:
        OSRM

    Fallback:
        Haversine geographic distance

    The optimizer does not need to know whether routing came
    from OSRM or the fallback implementation.
    """

    def __init__(
        self,
        osrm_client: Optional[OSRMClient] = None,
    ):
        self.osrm = osrm_client or OSRMClient()

    def is_road_routing_available(self) -> bool:
        """
        Check whether the configured OSRM server is available.
        """

        return self.osrm.is_available()

    @staticmethod
    def _coordinates_from_stops(
        stops: List[Dict[str, Any]],
    ) -> Optional[List[List[float]]]:
        """
        Convert stops into OSRM coordinate format.

        OSRM expects:

            [longitude, latitude]

        Example:

            [
                [78.4867, 17.3850],
                [78.4800, 17.3900]
            ]
        """

        coordinates = []

        for stop in stops:

            if not stop_has_location(stop):
                return None

            coordinates.append(
                [
                    float(stop["longitude"]),
                    float(stop["latitude"]),
                ]
            )

        return coordinates

    def sequence_metrics(
        self,
        stops: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate routing metrics for a complete stop sequence.

        OSRM available:

            road distance
            road travel time

        OSRM unavailable:

            Haversine distance
            travel time unavailable

        Returns:

            {
                "distance_km": float,
                "duration_min": float | None,
                "provider": "osrm" | "haversine_fallback" | "none",
            }
        """

        if len(stops) <= 1:
            return {
                "distance_km": 0.0,
                "duration_min": 0.0,
                "provider": "none",
            }

        coordinates = self._coordinates_from_stops(
            stops
        )

        if coordinates is None:
            return {
                "distance_km": None,
                "duration_min": None,
                "provider": "unavailable",
            }

        # ------------------------------------------------------------
        # Try OSRM first
        # ------------------------------------------------------------

        if self.is_road_routing_available():

            try:

                result = self.osrm.route(
                    coordinates,
                    overview="false",
                    steps=False,
                )

                return {
                    "distance_km": result.get(
                        "distance_km"
                    ),
                    "duration_min": result.get(
                        "duration_min"
                    ),
                    "provider": "osrm",
                }

            except Exception:
                # Do not break route optimization if OSRM
                # temporarily becomes unavailable.
                pass

        # ------------------------------------------------------------
        # Haversine fallback
        # ------------------------------------------------------------

        geographic_distance = sequence_distance(
            stops
        )

        return {
            "distance_km": geographic_distance,
            "duration_min": None,
            "provider": "haversine_fallback",
        }

    def distance(
        self,
        stops: List[Dict[str, Any]],
    ) -> Optional[float]:
        """
        Convenience method returning only distance.
        """

        metrics = self.sequence_metrics(
            stops
        )

        return metrics.get(
            "distance_km"
        )

    def travel_time(
        self,
        stops: List[Dict[str, Any]],
    ) -> Optional[float]:
        """
        Convenience method returning travel time in minutes.

        Returns None when OSRM is unavailable.
        """

        metrics = self.sequence_metrics(
            stops
        )

        return metrics.get(
            "duration_min"
        )


# ============================================================================
# INSERTION CANDIDATES
# ============================================================================

def generate_insertion_candidates(
    existing_stops: List[Dict[str, Any]],
    new_stop: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate every possible position where a new stop can
    be inserted.

    Example:

        Existing:

            A -> B -> C

        Candidates:

            X -> A -> B -> C
            A -> X -> B -> C
            A -> B -> X -> C
            A -> B -> C -> X

    This function uses geographic distance for compatibility
    with the original sequencing engine.
    """

    candidates = []

    for position in range(
        len(existing_stops) + 1
    ):

        new_sequence = list(
            existing_stops
        )

        new_sequence.insert(
            position,
            new_stop,
        )

        distance = sequence_distance(
            new_sequence
        )

        candidates.append(
            {
                "position": position,
                "sequence": new_sequence,
                "distance_km": distance,
            }
        )

    return candidates


def calculate_insertion_cost(
    existing_stops: List[Dict[str, Any]],
    new_stop: Dict[str, Any],
    position: int,
) -> Optional[float]:
    """
    Calculate incremental geographic distance caused
    by inserting a customer at a specific position.

    Lower is better.

    Returns None if calculation cannot be performed.
    """

    if position < 0:
        return None

    if position > len(existing_stops):
        return None

    # ------------------------------------------------------------
    # Existing sequence
    # ------------------------------------------------------------

    before_sequence = list(
        existing_stops
    )

    before_distance = sequence_distance(
        before_sequence
    )

    # ------------------------------------------------------------
    # New sequence
    # ------------------------------------------------------------

    after_sequence = list(
        existing_stops
    )

    after_sequence.insert(
        position,
        new_stop,
    )

    after_distance = sequence_distance(
        after_sequence
    )

    if before_distance is None:
        return None

    if after_distance is None:
        return None

    return (
        after_distance
        - before_distance
    )


def rank_insertion_candidates(
    existing_stops: List[Dict[str, Any]],
    new_stop: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate and rank insertion candidates.

    Ranking is based on lowest incremental
    geographic distance.

    This remains the original deterministic
    Haversine ranking function.
    """

    candidates = []

    for position in range(
        len(existing_stops) + 1
    ):

        insertion_cost = (
            calculate_insertion_cost(
                existing_stops,
                new_stop,
                position,
            )
        )

        sequence = list(
            existing_stops
        )

        sequence.insert(
            position,
            new_stop,
        )

        total_distance = sequence_distance(
            sequence
        )

        candidates.append(
            {
                "position": position,
                "sequence": sequence,
                "incremental_distance_km": (
                    insertion_cost
                ),
                "total_distance_km": (
                    total_distance
                ),
            }
        )

    candidates.sort(
        key=lambda candidate: (
            candidate[
                "incremental_distance_km"
            ]
            if candidate[
                "incremental_distance_km"
            ] is not None
            else float("inf")
        )
    )

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        candidate["rank"] = rank

    return candidates


# ============================================================================
# ROAD-AWARE INSERTION
# ============================================================================

def calculate_road_insertion_cost(
    existing_stops: List[Dict[str, Any]],
    new_stop: Dict[str, Any],
    position: int,
    routing_engine: Optional[RoutingEngine] = None,
) -> Optional[float]:
    """
    Calculate incremental route distance using the routing engine.

    OSRM is used when available.

    Haversine is used as fallback.

    Returns:
        Incremental distance in kilometres.
    """

    if position < 0:
        return None

    if position > len(existing_stops):
        return None

    routing = (
        routing_engine
        or RoutingEngine()
    )

    # ------------------------------------------------------------
    # Before insertion
    # ------------------------------------------------------------

    before_sequence = list(
        existing_stops
    )

    before_metrics = routing.sequence_metrics(
        before_sequence
    )

    before_distance = before_metrics.get(
        "distance_km"
    )

    # ------------------------------------------------------------
    # After insertion
    # ------------------------------------------------------------

    after_sequence = list(
        existing_stops
    )

    after_sequence.insert(
        position,
        new_stop,
    )

    after_metrics = routing.sequence_metrics(
        after_sequence
    )

    after_distance = after_metrics.get(
        "distance_km"
    )

    if before_distance is None:
        return None

    if after_distance is None:
        return None

    return (
        after_distance
        - before_distance
    )


def rank_road_insertion_candidates(
    existing_stops: List[Dict[str, Any]],
    new_stop: Dict[str, Any],
    routing_engine: Optional[RoutingEngine] = None,
) -> List[Dict[str, Any]]:
    """
    Generate and rank insertion candidates using the routing engine.

    Preferred:

        OSRM road distance

    Fallback:

        Haversine distance

    Each candidate includes:

        position
        sequence
        incremental_distance_km
        total_distance_km
        duration_min
        provider
        rank
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    candidates = []

    for position in range(
        len(existing_stops) + 1
    ):

        # --------------------------------------------------------
        # Build candidate sequence
        # --------------------------------------------------------

        sequence = list(
            existing_stops
        )

        sequence.insert(
            position,
            new_stop,
        )

        # --------------------------------------------------------
        # Candidate metrics
        # --------------------------------------------------------

        metrics = routing.sequence_metrics(
            sequence
        )

        total_distance = metrics.get(
            "distance_km"
        )

        duration_min = metrics.get(
            "duration_min"
        )

        provider = metrics.get(
            "provider"
        )

        # --------------------------------------------------------
        # Existing sequence metrics
        # --------------------------------------------------------

        before_metrics = (
            routing.sequence_metrics(
                existing_stops
            )
        )

        before_distance = (
            before_metrics.get(
                "distance_km"
            )
        )

        if (
            before_distance is None
            or total_distance is None
        ):
            incremental_distance = None

        else:
            incremental_distance = (
                total_distance
                - before_distance
            )

        candidates.append(
            {
                "position": position,
                "sequence": sequence,
                "incremental_distance_km": (
                    incremental_distance
                ),
                "total_distance_km": (
                    total_distance
                ),
                "duration_min": (
                    duration_min
                ),
                "provider": provider,
            }
        )

    # ------------------------------------------------------------
    # Rank
    # ------------------------------------------------------------

    candidates.sort(
        key=lambda candidate: (
            candidate[
                "incremental_distance_km"
            ]
            if candidate[
                "incremental_distance_km"
            ] is not None
            else float("inf"),
            candidate[
                "total_distance_km"
            ]
            if candidate[
                "total_distance_km"
            ] is not None
            else float("inf"),
        )
    )

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        candidate["rank"] = rank

    return candidates


# ============================================================================
# ROUTE SEQUENCE METRICS
# ============================================================================

def calculate_sequence_metrics(
    stops: List[Dict[str, Any]],
    routing_engine: Optional[RoutingEngine] = None,
) -> Dict[str, Any]:
    """
    Calculate complete metrics for a route sequence.

    Returns:

        {
            "distance_km": ...,
            "duration_min": ...,
            "provider": ...
        }
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    return routing.sequence_metrics(
        stops
    )


# ============================================================================
# SIMPLE ROUTE COMPARISON
# ============================================================================

def compare_sequences(
    sequences: List[List[Dict[str, Any]]],
    routing_engine: Optional[RoutingEngine] = None,
) -> List[Dict[str, Any]]:
    """
    Calculate and rank multiple complete route sequences.

    This is useful later when the optimizer generates
    multiple route alternatives.

    No route is automatically assigned or saved.
    """

    routing = (
        routing_engine
        or RoutingEngine()
    )

    results = []

    for index, sequence in enumerate(
        sequences
    ):

        metrics = routing.sequence_metrics(
            sequence
        )

        results.append(
            {
                "candidate_index": index,
                "sequence": sequence,
                "distance_km": metrics.get(
                    "distance_km"
                ),
                "duration_min": metrics.get(
                    "duration_min"
                ),
                "provider": metrics.get(
                    "provider"
                ),
            }
        )

    results.sort(
        key=lambda result: (
            result["distance_km"]
            if result["distance_km"] is not None
            else float("inf"),
            result["duration_min"]
            if result["duration_min"] is not None
            else float("inf"),
        )
    )

    for rank, result in enumerate(
        results,
        start=1,
    ):
        result["rank"] = rank

    return results

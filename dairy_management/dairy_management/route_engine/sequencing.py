"""
Route Optimization Engine
Auto Sequence Engine.

Responsibilities
----------------
1. Calculate geographic distance.
2. Use OSRM road routing when available.
3. Fall back to Haversine distance when OSRM is unavailable.
4. Generate insertion candidates.
5. Rank insertion positions.
6. Generate a complete route sequence.
7. Improve a route using deterministic 2-opt.
8. Calculate route distance/time metrics.
9. Compare route sequences.

IMPORTANT
---------
This module is completely proposal-only.

It does NOT:
    - modify ERPNext documents
    - modify customer GPS
    - modify route assignments
    - modify delivery orders
    - write to the database

The optimizer decides WHAT should change.
The approval/write workflow decides WHEN it is actually changed.
"""

from math import (
    atan2,
    cos,
    radians,
    sin,
    sqrt,
)
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
)

from .routing.osrm import OSRMClient


# ============================================================================
# CONSTANTS
# ============================================================================

EARTH_RADIUS_KM = 6371.0088

DEFAULT_AVERAGE_SPEED_KMPH = 30.0

DEFAULT_MAX_2OPT_ITERATIONS = 100

SEQUENCE_ENGINE_VERSION = "0.2.0"


# ============================================================================
# BASIC HELPERS
# ============================================================================

def _safe_float(
    value: Any,
) -> Optional[float]:
    """
    Safely convert a value to float.
    """

    if value is None:
        return None

    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def stop_id(
    stop: Dict[str, Any],
) -> Optional[str]:
    """
    Return the most useful identifier for a stop.
    """

    return (
        stop.get("name")
        or stop.get("customer_name")
        or stop.get("id")
    )


def stop_has_location(
    stop: Dict[str, Any],
) -> bool:
    """
    Check whether a stop has valid latitude/longitude.
    """

    latitude = _safe_float(
        stop.get("latitude")
    )

    longitude = _safe_float(
        stop.get("longitude")
    )

    if latitude is None or longitude is None:
        return False

    if latitude < -90 or latitude > 90:
        return False

    if longitude < -180 or longitude > 180:
        return False

    return True


def coordinates(
    stop: Dict[str, Any],
) -> Optional[Tuple[float, float]]:
    """
    Return (latitude, longitude).
    """

    if not stop_has_location(stop):
        return None

    return (
        float(stop["latitude"]),
        float(stop["longitude"]),
    )


# ============================================================================
# HAVERSINE
# ============================================================================

def haversine_distance(
    first: Dict[str, Any],
    second: Dict[str, Any],
) -> Optional[float]:
    """
    Calculate straight-line distance in kilometres.
    """

    first_coordinates = coordinates(
        first
    )

    second_coordinates = coordinates(
        second
    )

    if (
        first_coordinates is None
        or second_coordinates is None
    ):
        return None

    lat1, lon1 = first_coordinates
    lat2, lon2 = second_coordinates

    lat1 = radians(lat1)
    lat2 = radians(lat2)

    delta_lat = radians(
        lat2 - lat1
    )

    delta_lon = radians(
        lon2 - lon1
    )

    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    value = min(
        1.0,
        max(0.0, value),
    )

    angular_distance = 2 * atan2(
        sqrt(value),
        sqrt(1 - value),
    )

    return (
        EARTH_RADIUS_KM
        * angular_distance
    )


# ============================================================================
# ROUTING ENGINE
# ============================================================================

class RoutingEngine:
    """
    Routing abstraction.

    Preferred provider:
        OSRM

    Fallback provider:
        Haversine distance

    The interface is intentionally independent of the optimizer.
    """

    def __init__(
        self,
        osrm_client: Optional[
            OSRMClient
        ] = None,
        average_speed_kmph: float = (
            DEFAULT_AVERAGE_SPEED_KMPH
        ),
    ):
        self.osrm = (
            osrm_client
            or OSRMClient()
        )

        self.average_speed_kmph = (
            float(
                average_speed_kmph
            )
        )

    # ----------------------------------------------------------------------
    # OSRM AVAILABILITY
    # ----------------------------------------------------------------------

    def is_road_routing_available(
        self,
    ) -> bool:
        """
        Return whether OSRM is reachable.
        """

        try:
            return bool(
                self.osrm.is_available()
            )
        except Exception:
            return False

    # ----------------------------------------------------------------------
    # STOP COORDINATES
    # ----------------------------------------------------------------------

    def _coordinates_from_stops(
        self,
        stops: Sequence[
            Dict[str, Any]
        ],
    ) -> List[
        Tuple[float, float]
    ]:
        """
        Convert stops into coordinate tuples.
        """

        result = []

        for stop in stops:

            point = coordinates(
                stop
            )

            if point is None:
                raise ValueError(
                    "All route stops must "
                    "have valid latitude "
                    "and longitude"
                )

            result.append(point)

        return result

    # ----------------------------------------------------------------------
    # DISTANCE BETWEEN TWO STOPS
    # ----------------------------------------------------------------------

    def distance(
        self,
        first: Dict[str, Any],
        second: Dict[str, Any],
    ) -> Optional[float]:
        """
        Return distance in kilometres.

        OSRM is preferred.

        Haversine is used as fallback.
        """

        if not (
            stop_has_location(first)
            and stop_has_location(second)
        ):
            return None

        try:

            if self.is_road_routing_available():

                result = self.osrm.route(
                    coordinates=[
                        coordinates(first),
                        coordinates(second),
                    ],
                    overview=False,
                    steps=False,
                )

                if result:

                    distance_m = (
                        result.get(
                            "distance"
                        )
                    )

                    if distance_m is not None:

                        return (
                            float(
                                distance_m
                            )
                            / 1000.0
                        )

        except Exception:
            pass

        return haversine_distance(
            first,
            second,
        )

    # ----------------------------------------------------------------------
    # TRAVEL TIME BETWEEN TWO STOPS
    # ----------------------------------------------------------------------

    def travel_time(
        self,
        first: Dict[str, Any],
        second: Dict[str, Any],
    ) -> Optional[float]:
        """
        Return travel time in minutes.

        OSRM is preferred.

        Haversine fallback estimates travel time
        using average speed.
        """

        if not (
            stop_has_location(first)
            and stop_has_location(second)
        ):
            return None

        try:

            if self.is_road_routing_available():

                result = self.osrm.route(
                    coordinates=[
                        coordinates(first),
                        coordinates(second),
                    ],
                    overview=False,
                    steps=False,
                )

                if result:

                    duration_seconds = (
                        result.get(
                            "duration"
                        )
                    )

                    if duration_seconds is not None:

                        return (
                            float(
                                duration_seconds
                            )
                            / 60.0
                        )

        except Exception:
            pass

        distance_km = (
            haversine_distance(
                first,
                second,
            )
        )

        if distance_km is None:
            return None

        if (
            self.average_speed_kmph
            <= 0
        ):
            return None

        return (
            distance_km
            / self.average_speed_kmph
            * 60.0
        )

    # ----------------------------------------------------------------------
    # SEQUENCE METRICS
    # ----------------------------------------------------------------------

    def sequence_metrics(
        self,
        stops: Sequence[
            Dict[str, Any]
        ],
    ) -> Dict[str, Any]:
        """
        Calculate total distance and travel time
        for a complete sequence.
        """

        stops = list(stops)

        if len(stops) <= 1:

            return {
                "distance_km": 0.0,
                "travel_time_min": 0.0,
                "provider": (
                    "none"
                    if not stops
                    else "single_stop"
                ),
            }

        total_distance = 0.0
        total_time = 0.0

        used_haversine = False
        used_osrm = False

        for index in range(
            len(stops) - 1
        ):

            first = stops[index]
            second = stops[index + 1]

            distance_km = self.distance(
                first,
                second,
            )

            if distance_km is None:

                return {
                    "distance_km": None,
                    "travel_time_min": None,
                    "provider": "invalid",
                }

            total_distance += (
                distance_km
            )

            try:

                road_available = (
                    self.is_road_routing_available()
                )

            except Exception:

                road_available = False

            if road_available:

                used_osrm = True

            else:

                used_haversine = True

            travel_time_min = (
                self.travel_time(
                    first,
                    second,
                )
            )

            if travel_time_min is not None:

                total_time += (
                    travel_time_min
                )

        if (
            used_osrm
            and not used_haversine
        ):
            provider = "osrm"

        elif used_haversine:

            provider = (
                "haversine_fallback"
            )

        else:

            provider = "unknown"

        return {
            "distance_km": (
                total_distance
            ),
            "travel_time_min": (
                total_time
            ),
            "provider": provider,
        }


# ============================================================================
# LEGACY COMPATIBILITY FUNCTIONS
# ============================================================================

def distance_between_stops(
    first: Dict[str, Any],
    second: Dict[str, Any],
) -> Optional[float]:
    """
    Backward-compatible Haversine distance.
    """

    return haversine_distance(
        first,
        second,
    )


def sequence_distance(
    stops: Sequence[
        Dict[str, Any]
    ],
) -> Optional[float]:
    """
    Backward-compatible total Haversine distance.
    """

    stops = list(stops)

    if len(stops) <= 1:
        return 0.0

    total = 0.0

    for index in range(
        len(stops) - 1
    ):

        distance = (
            haversine_distance(
                stops[index],
                stops[index + 1],
            )
        )

        if distance is None:
            return None

        total += distance

    return total


def calculate_sequence_metrics(
    stops: Sequence[
        Dict[str, Any]
    ],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> Dict[str, Any]:
    """
    Calculate route metrics using RoutingEngine.
    """

    engine = (
        routing_engine
        or RoutingEngine()
    )

    return engine.sequence_metrics(
        list(stops)
    )


# ============================================================================
# INSERTION
# ============================================================================

def generate_insertion_candidates(
    stops: Sequence[
        Dict[str, Any]
    ],
    new_stop: Dict[str, Any],
) -> List[
    Dict[str, Any]
]:
    """
    Generate every possible insertion position.

    Position 0:
        before the first stop

    Position len(stops):
        after the final stop
    """

    stops = list(stops)

    candidates = []

    for position in range(
        len(stops) + 1
    ):

        candidate_sequence = (
            stops[:position]
            + [new_stop]
            + stops[position:]
        )

        candidates.append(
            {
                "position": position,
                "sequence": (
                    candidate_sequence
                ),
            }
        )

    return candidates


def calculate_insertion_cost(
    stops: Sequence[
        Dict[str, Any]
    ],
    new_stop: Dict[str, Any],
    position: int,
) -> Dict[str, Any]:
    """
    Calculate incremental Haversine distance caused
    by inserting a stop.
    """

    stops = list(stops)

    before = (
        stops[position - 1]
        if position > 0
        else None
    )

    after = (
        stops[position]
        if position < len(stops)
        else None
    )

    if before is None and after is None:

        return {
            "incremental_distance_km": 0.0,
            "total_distance_km": 0.0,
        }

    if before is None:

        added = haversine_distance(
            new_stop,
            after,
        )

        if added is None:
            return {
                "incremental_distance_km": None,
                "total_distance_km": None,
            }

        existing = sequence_distance(
            stops
        ) or 0.0

        return {
            "incremental_distance_km": (
                added
            ),
            "total_distance_km": (
                existing + added
            ),
        }

    if after is None:

        added = haversine_distance(
            before,
            new_stop,
        )

        if added is None:
            return {
                "incremental_distance_km": None,
                "total_distance_km": None,
            }

        existing = sequence_distance(
            stops
        ) or 0.0

        return {
            "incremental_distance_km": (
                added
            ),
            "total_distance_km": (
                existing + added
            ),
        }

    old_leg = haversine_distance(
        before,
        after,
    )

    new_leg_1 = haversine_distance(
        before,
        new_stop,
    )

    new_leg_2 = haversine_distance(
        new_stop,
        after,
    )

    if (
        old_leg is None
        or new_leg_1 is None
        or new_leg_2 is None
    ):

        return {
            "incremental_distance_km": None,
            "total_distance_km": None,
        }

    incremental = (
        new_leg_1
        + new_leg_2
        - old_leg
    )

    existing = sequence_distance(
        stops
    ) or 0.0

    return {
        "incremental_distance_km": (
            incremental
        ),
        "total_distance_km": (
            existing + incremental
        ),
    }


def rank_insertion_candidates(
    stops: Sequence[
        Dict[str, Any]
    ],
    new_stop: Dict[str, Any],
) -> List[
    Dict[str, Any]
]:
    """
    Rank insertion positions using Haversine distance.
    """

    candidates = []

    for candidate in generate_insertion_candidates(
        stops,
        new_stop,
    ):

        position = candidate[
            "position"
        ]

        cost = calculate_insertion_cost(
            stops,
            new_stop,
            position,
        )

        if (
            cost[
                "incremental_distance_km"
            ]
            is None
        ):
            continue

        candidates.append(
            {
                **candidate,
                **cost,
            }
        )

    candidates.sort(
        key=lambda item: (
            item[
                "incremental_distance_km"
            ],
            item["position"],
        )
    )

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        candidate[
            "rank"
        ] = rank

    return candidates


# ============================================================================
# ROAD-AWARE INSERTION
# ============================================================================

def calculate_road_insertion_cost(
    stops: Sequence[
        Dict[str, Any]
    ],
    new_stop: Dict[str, Any],
    position: int,
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> Dict[str, Any]:
    """
    Calculate insertion cost using the RoutingEngine.

    OSRM is preferred when available.
    """

    engine = (
        routing_engine
        or RoutingEngine()
    )

    stops = list(stops)

    original_metrics = (
        engine.sequence_metrics(
            stops
        )
    )

    candidate_sequence = (
        stops[:position]
        + [new_stop]
        + stops[position:]
    )

    candidate_metrics = (
        engine.sequence_metrics(
            candidate_sequence
        )
    )

    if (
        original_metrics[
            "distance_km"
        ]
        is None
        or candidate_metrics[
            "distance_km"
        ]
        is None
    ):

        return {
            "incremental_distance_km": None,
            "total_distance_km": None,
            "incremental_time_min": None,
            "total_time_min": None,
            "provider": (
                candidate_metrics.get(
                    "provider"
                )
            ),
        }

    original_time = (
        original_metrics.get(
            "travel_time_min"
        )
        or 0.0
    )

    candidate_time = (
        candidate_metrics.get(
            "travel_time_min"
        )
        or 0.0
    )

    return {
        "incremental_distance_km": (
            candidate_metrics[
                "distance_km"
            ]
            - original_metrics[
                "distance_km"
            ]
        ),
        "total_distance_km": (
            candidate_metrics[
                "distance_km"
            ]
        ),
        "incremental_time_min": (
            candidate_time
            - original_time
        ),
        "total_time_min": (
            candidate_time
        ),
        "provider": (
            candidate_metrics.get(
                "provider"
            )
        ),
    }


def rank_road_insertion_candidates(
    stops: Sequence[
        Dict[str, Any]
    ],
    new_stop: Dict[str, Any],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> List[
    Dict[str, Any]
]:
    """
    Rank insertion positions using the RoutingEngine.

    Ranking priority:

        1. incremental distance
        2. incremental travel time
        3. insertion position
    """

    engine = (
        routing_engine
        or RoutingEngine()
    )

    candidates = []

    for candidate in generate_insertion_candidates(
        stops,
        new_stop,
    ):

        position = candidate[
            "position"
        ]

        cost = (
            calculate_road_insertion_cost(
                stops=stops,
                new_stop=new_stop,
                position=position,
                routing_engine=engine,
            )
        )

        if (
            cost[
                "incremental_distance_km"
            ]
            is None
        ):
            continue

        candidates.append(
            {
                **candidate,
                **cost,
            }
        )

    candidates.sort(
        key=lambda item: (
            item[
                "incremental_distance_km"
            ],
            item.get(
                "incremental_time_min"
            )
            if item.get(
                "incremental_time_min"
            )
            is not None
            else float("inf"),
            item["position"],
        )
    )

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):

        candidate[
            "rank"
        ] = rank

    return candidates


# ============================================================================
# NEAREST NEIGHBOR
# ============================================================================

def nearest_neighbor_sequence(
    stops: Sequence[
        Dict[str, Any]
    ],
    start_stop: Optional[
        Dict[str, Any]
    ] = None,
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> List[
    Dict[str, Any]
]:
    """
    Generate an initial deterministic sequence.

    If start_stop is supplied, that stop is kept first.

    Otherwise the first supplied stop is used.

    Remaining stops are selected using the shortest
    available next-leg distance.
    """

    stops = list(stops)

    if len(stops) <= 2:
        return list(stops)

    engine = (
        routing_engine
        or RoutingEngine()
    )

    remaining = list(stops)

    if start_stop is not None:

        start_key = stop_id(
            start_stop
        )

        selected_index = None

        for index, stop in enumerate(
            remaining
        ):

            if (
                stop_id(stop)
                == start_key
            ):
                selected_index = index
                break

        if selected_index is not None:

            current = remaining.pop(
                selected_index
            )

        else:

            current = remaining.pop(
                0
            )

    else:

        current = remaining.pop(
            0
        )

    sequence = [
        current
    ]

    while remaining:

        best_index = None
        best_distance = None

        for index, candidate in enumerate(
            remaining
        ):

            distance = engine.distance(
                current,
                candidate,
            )

            if distance is None:
                continue

            if (
                best_distance is None
                or distance < best_distance
                or (
                    distance
                    == best_distance
                    and str(
                        stop_id(
                            candidate
                        )
                    )
                    <
                    str(
                        stop_id(
                            remaining[
                                best_index
                            ]
                        )
                    )
                )
            ):

                best_index = index
                best_distance = distance

        if best_index is None:

            # Deterministic fallback for stops
            # without usable routing.

            remaining.sort(
                key=lambda item: str(
                    stop_id(item)
                )
            )

            next_stop = remaining.pop(
                0
            )

        else:

            next_stop = remaining.pop(
                best_index
            )

        sequence.append(
            next_stop
        )

        current = next_stop

    return sequence


# ============================================================================
# 2-OPT
# ============================================================================

def _two_opt_swap(
    sequence: List[
        Dict[str, Any]
    ],
    first_index: int,
    second_index: int,
) -> List[
    Dict[str, Any]
]:
    """
    Reverse the section between two indices.
    """

    return (
        sequence[:first_index]
        + list(
            reversed(
                sequence[
                    first_index:
                    second_index + 1
                ]
            )
        )
        + sequence[
            second_index + 1:
        ]
    )


def optimize_sequence_2opt(
    stops: Sequence[
        Dict[str, Any]
    ],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
    max_iterations: int = (
        DEFAULT_MAX_2OPT_ITERATIONS
    ),
    start_stop: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:
    """
    Improve a route sequence using deterministic 2-opt.

    The algorithm:

        1. Build nearest-neighbor sequence.
        2. Calculate current route cost.
        3. Test pairwise edge reversals.
        4. Keep only strict improvements.
        5. Repeat until no improvement remains
           or max_iterations is reached.

    The first stop can optionally be fixed.

    This is a local deterministic optimizer.
    """

    engine = (
        routing_engine
        or RoutingEngine()
    )

    stops = list(stops)

    if len(stops) <= 2:

        sequence = list(stops)

        return {
            "sequence": sequence,
            "metrics": (
                engine.sequence_metrics(
                    sequence
                )
            ),
            "iterations": 0,
            "improved": False,
        }

    sequence = nearest_neighbor_sequence(
        stops,
        start_stop=start_stop,
        routing_engine=engine,
    )

    best_metrics = (
        engine.sequence_metrics(
            sequence
        )
    )

    best_distance = (
        best_metrics[
            "distance_km"
        ]
    )

    if best_distance is None:

        return {
            "sequence": sequence,
            "metrics": best_metrics,
            "iterations": 0,
            "improved": False,
        }

    improved = False
    iterations = 0

    # If a start stop is fixed, do not reverse
    # the first element.
    start_index = (
        1
        if start_stop is not None
        else 0
    )

    while (
        iterations
        < max_iterations
    ):

        iteration_improved = False

        for first_index in range(
            start_index,
            len(sequence) - 1,
        ):

            for second_index in range(
                first_index + 1,
                len(sequence),
            ):

                candidate = (
                    _two_opt_swap(
                        sequence,
                        first_index,
                        second_index,
                    )
                )

                candidate_metrics = (
                    engine.sequence_metrics(
                        candidate
                    )
                )

                candidate_distance = (
                    candidate_metrics[
                        "distance_km"
                    ]
                )

                if candidate_distance is None:
                    continue

                # Strict improvement only.
                #
                # This prevents oscillation and makes
                # the algorithm deterministic.

                if (
                    candidate_distance
                    < best_distance
                    - 1e-9
                ):

                    sequence = candidate

                    best_metrics = (
                        candidate_metrics
                    )

                    best_distance = (
                        candidate_distance
                    )

                    improved = True
                    iteration_improved = True

                    break

            if iteration_improved:
                break

        iterations += 1

        if not iteration_improved:
            break

    return {
        "sequence": sequence,
        "metrics": best_metrics,
        "iterations": iterations,
        "improved": improved,
    }


# ============================================================================
# FULL ROUTE SEQUENCING
# ============================================================================

def generate_route_sequence(
    stops: Sequence[
        Dict[str, Any]
    ],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
    start_stop: Optional[
        Dict[str, Any]
    ] = None,
    max_2opt_iterations: int = (
        DEFAULT_MAX_2OPT_ITERATIONS
    ),
) -> Dict[str, Any]:
    """
    Generate and optimize a complete route sequence.

    This is the main Auto Sequence entry point.
    """

    engine = (
        routing_engine
        or RoutingEngine()
    )

    stops = list(stops)

    if not stops:

        return {
            "sequence": [],
            "metrics": {
                "distance_km": 0.0,
                "travel_time_min": 0.0,
                "provider": "none",
            },
            "iterations": 0,
            "improved": False,
            "engine_version": (
                SEQUENCE_ENGINE_VERSION
            ),
        }

    result = optimize_sequence_2opt(
        stops=stops,
        routing_engine=engine,
        max_iterations=(
            max_2opt_iterations
        ),
        start_stop=start_stop,
    )

    return {
        **result,
        "engine_version": (
            SEQUENCE_ENGINE_VERSION
        ),
    }


# ============================================================================
# SEQUENCE COMPARISON
# ============================================================================

def compare_sequences(
    original: Sequence[
        Dict[str, Any]
    ],
    candidate: Sequence[
        Dict[str, Any]
    ],
    routing_engine: Optional[
        RoutingEngine
    ] = None,
) -> Dict[str, Any]:
    """
    Compare two route sequences.

    Returns distance/time difference and provider.
    """

    engine = (
        routing_engine
        or RoutingEngine()
    )

    original = list(
        original
    )

    candidate = list(
        candidate
    )

    original_metrics = (
        engine.sequence_metrics(
            original
        )
    )

    candidate_metrics = (
        engine.sequence_metrics(
            candidate
        )
    )

    original_distance = (
        original_metrics.get(
            "distance_km"
        )
    )

    candidate_distance = (
        candidate_metrics.get(
            "distance_km"
        )
    )

    original_time = (
        original_metrics.get(
            "travel_time_min"
        )
    )

    candidate_time = (
        candidate_metrics.get(
            "travel_time_min"
        )
    )

    distance_change = None

    if (
        original_distance is not None
        and candidate_distance is not None
    ):

        distance_change = (
            candidate_distance
            - original_distance
        )

    time_change = None

    if (
        original_time is not None
        and candidate_time is not None
    ):

        time_change = (
            candidate_time
            - original_time
        )

    return {
        "original": {
            "distance_km": (
                original_distance
            ),
            "travel_time_min": (
                original_time
            ),
            "provider": (
                original_metrics.get(
                    "provider"
                )
            ),
        },
        "candidate": {
            "distance_km": (
                candidate_distance
            ),
            "travel_time_min": (
                candidate_time
            ),
            "provider": (
                candidate_metrics.get(
                    "provider"
                )
            ),
        },
        "distance_change_km": (
            distance_change
        ),
        "travel_time_change_min": (
            time_change
        ),
        "improved": (
            distance_change is not None
            and distance_change < 0
        ),
    }


# ============================================================================
# ROUTE SEQUENCE SUMMARY
# ============================================================================

def sequence_summary(
    sequence: Sequence[
        Dict[str, Any]
    ],
    metrics: Optional[
        Dict[str, Any]
    ] = None,
) -> List[
    Dict[str, Any]
]:
    """
    Convert a route sequence into a UI/API-friendly
    stop summary.

    GPS values are copied exactly as supplied.

    This function never modifies coordinates.
    """

    result = []

    for position, stop in enumerate(
        sequence,
        start=1,
    ):

        result.append(
            {
                "sequence": position,
                "customer_id": stop.get(
                    "name"
                ),
                "customer_name": stop.get(
                    "customer_name"
                ),
                "latitude": stop.get(
                    "latitude"
                ),
                "longitude": stop.get(
                    "longitude"
                ),
                "route": stop.get(
                    "route"
                ),
            }
        )

    return result


# ============================================================================
# MODULE INFO
# ============================================================================

def get_engine_info() -> Dict[str, Any]:
    """
    Return sequence engine capabilities.
    """

    engine = RoutingEngine()

    road_available = (
        engine.is_road_routing_available()
    )

    return {
        "engine": (
            "Dairy Route Auto Sequence Engine"
        ),
        "version": (
            SEQUENCE_ENGINE_VERSION
        ),
        "road_routing": (
            road_available
        ),
        "primary_routing": (
            "OSRM"
            if road_available
            else "Haversine fallback"
        ),
        "optimization": [
            "nearest_neighbor",
            "2-opt",
            "insertion_optimization",
        ],
        "database_write": False,
        "gps_modification": False,
    }

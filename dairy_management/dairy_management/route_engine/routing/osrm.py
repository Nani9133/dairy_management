"""
Route Optimization Engine
OSRM routing client.

This module provides road distance and travel-time information.
It does not modify ERPNext documents.
"""

import os
from typing import Any, Dict, List, Optional

import requests


class OSRMClient:
    """
    Small replaceable client for an OSRM routing server.

    Default:
        http://127.0.0.1:5000

    Configure another OSRM server with:
        OSRM_BASE_URL=http://your-osrm-server:5000
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 15,
    ):
        self.base_url = (
            base_url
            or os.environ.get("OSRM_BASE_URL")
            or "http://127.0.0.1:5000"
        ).rstrip("/")

        self.timeout = timeout

    @staticmethod
    def _coordinate_string(coordinates: List[List[float]]) -> str:
        """
        Convert:
            [[lon, lat], [lon, lat]]

        into OSRM format:
            lon,lat;lon,lat
        """
        return ";".join(
            f"{float(longitude)},{float(latitude)}"
            for longitude, latitude in coordinates
        )

    def route(
        self,
        coordinates: List[List[float]],
        overview: str = "false",
        steps: bool = False,
    ) -> Dict[str, Any]:
        """
        Calculate a road route through the supplied coordinates.

        Returns:
            {
                "distance_m": ...,
                "duration_s": ...,
                "distance_km": ...,
                "duration_min": ...,
                "geometry": ...,
                "raw": ...
            }
        """

        if not coordinates or len(coordinates) < 2:
            raise ValueError(
                "At least two coordinates are required for routing"
            )

        coordinate_string = self._coordinate_string(coordinates)

        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{coordinate_string}"
        )

        params = {
            "overview": overview,
            "steps": "true" if steps else "false",
        }

        response = requests.get(
            url,
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") != "Ok":
            raise RuntimeError(
                f"OSRM routing failed: {data.get('message') or data.get('code')}"
            )

        if not data.get("routes"):
            raise RuntimeError("OSRM returned no routes")

        route = data["routes"][0]

        distance_m = float(route.get("distance", 0))
        duration_s = float(route.get("duration", 0))

        return {
            "distance_m": distance_m,
            "duration_s": duration_s,
            "distance_km": distance_m / 1000.0,
            "duration_min": duration_s / 60.0,
            "geometry": route.get("geometry"),
            "raw": data,
        }

    def distance_matrix(
        self,
        coordinates: List[List[float]],
    ) -> Dict[str, Any]:
        """
        Calculate road distance and travel-time matrices.

        Coordinates use:
            [longitude, latitude]
        """

        if not coordinates:
            raise ValueError("At least one coordinate is required")

        coordinate_string = self._coordinate_string(coordinates)

        url = (
            f"{self.base_url}/table/v1/driving/"
            f"{coordinate_string}"
        )

        params = {
            "annotations": "duration,distance",
        }

        response = requests.get(
            url,
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") != "Ok":
            raise RuntimeError(
                f"OSRM table request failed: "
                f"{data.get('message') or data.get('code')}"
            )

        return {
            "distances_m": data.get("distances") or [],
            "durations_s": data.get("durations") or [],
            "distances_km": [
                [
                    value / 1000.0 if value is not None else None
                    for value in row
                ]
                for row in (data.get("distances") or [])
            ],
            "durations_min": [
                [
                    value / 60.0 if value is not None else None
                    for value in row
                ]
                for row in (data.get("durations") or [])
            ],
            "sources": data.get("sources") or [],
            "destinations": data.get("destinations") or [],
            "raw": data,
        }

    def is_available(self) -> bool:
        """
        Check whether the configured OSRM server is reachable.
        """

        try:
            response = requests.get(
                f"{self.base_url}/",
                timeout=self.timeout,
            )

            return response.status_code < 500

        except requests.RequestException:
            return False

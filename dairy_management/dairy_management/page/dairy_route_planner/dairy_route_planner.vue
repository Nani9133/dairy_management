<script setup>
import {
    computed,
    nextTick,
    onBeforeUnmount,
    onMounted,
    ref
} from "vue";

import { useHost } from "@framework/ui/island";

import L from "leaflet";
import "leaflet/dist/leaflet.css";

import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";

import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import { point as turfPoint } from "@turf/helpers";

/* =========================================================
   HOST
========================================================= */

const emit = defineEmits(["title", "actions"]);
const host = useHost();

const title = "Route Planner";


/* =========================================================
   FILTER DATA
========================================================= */

const states = ref([]);
const cities = ref([]);
const zones = ref([]);
const areas = ref([]);
const points = ref([]);
const routes = ref([]);


/* =========================================================
   SELECTED FILTERS
========================================================= */

const selectedState = ref("");
const selectedCity = ref([]);
const selectedZone = ref([]);
const selectedArea = ref([]);
const selectedPoint = ref([]);
const selectedRoute = ref([]);

const openDropdown = ref("");
const searchCity = ref("");
const searchZone = ref("");
const searchArea = ref("");
const searchPoint = ref("");
const searchRoute = ref("");

const selectedStateName = computed(() =>
    selectedName(states.value, selectedState.value, "state_name")
);

function selectedNames(list, values, field) {
    const safeList = Array.isArray(list) ? list : [];
    const safeValues = Array.isArray(values) ? values : [];

    return safeValues
        .map(value => selectedName(safeList, value, field))
        .filter(Boolean);
}

const selectedCityNames = computed(() => selectedNames(cities.value, selectedCity.value, "city_name"));
const selectedZoneNames = computed(() => selectedNames(zones.value, selectedZone.value, "zone_name"));
const selectedAreaNames = computed(() => selectedNames(areas.value, selectedArea.value, "area_name"));
const selectedPointNames = computed(() => selectedNames(points.value, selectedPoint.value, "point_name"));
const selectedRouteNames = computed(() => selectedNames(routes.value, selectedRoute.value, "route_name"));

const selectedCityName = computed(() => selectedCityNames.value.join(", "));
const selectedZoneName = computed(() => selectedZoneNames.value.join(", "));
const selectedAreaName = computed(() => selectedAreaNames.value.join(", "));
const selectedPointName = computed(() => selectedPointNames.value.join(", "));
const selectedRouteName = computed(() => selectedRouteNames.value.join(", "));

function toggleDropdown(level) {
    openDropdown.value = openDropdown.value === level ? "" : level;
}

function toggleSelection(level, value) {
    const refs = { city: selectedCity, zone: selectedZone, area: selectedArea, point: selectedPoint, route: selectedRoute };
    const selectedRef = refs[level];
    if (!selectedRef || !value) return;

    if (!Array.isArray(selectedRef.value)) {
        selectedRef.value = [];
    }

    const index = selectedRef.value.indexOf(value);

    if (index >= 0) {
        selectedRef.value.splice(index, 1);
    } else {
        selectedRef.value.push(value);
    }

    if (level === "city") cityChanged();
    if (level === "zone") zoneChanged();
    if (level === "area") areaChanged();
    if (level === "point") pointChanged();
    if (level === "route") routeChanged();
}

function selectAllLevel(level) {
    const config = { city: [selectedCity, cities], zone: [selectedZone, zones], area: [selectedArea, areas], point: [selectedPoint, points], route: [selectedRoute, routes] }[level];
    if (!config) return;
    config[0].value = config[1].value.map(row => row.name).filter(Boolean);

    if (level === "city") cityChanged();
    if (level === "zone") zoneChanged();
    if (level === "area") areaChanged();
    if (level === "point") pointChanged();
    if (level === "route") routeChanged();
}

function clearLevel(level) {
    const refs = { city: selectedCity, zone: selectedZone, area: selectedArea, point: selectedPoint, route: selectedRoute };
    const selectedRef = refs[level];
    if (!selectedRef) return;
    selectedRef.value = [];

    if (level === "city") cityChanged();
    if (level === "zone") zoneChanged();
    if (level === "area") areaChanged();
    if (level === "point") pointChanged();
    if (level === "route") routeChanged();
}

function filteredOptions(list, search, field) {
    const rows = Array.isArray(list?.value) ? list.value : [];
    const query = String(search || "").trim().toLowerCase();

    if (!query) {
        return rows;
    }

    return rows.filter(row =>
        String(
            row?.[field] ||
            row?.name ||
            ""
        ).toLowerCase().includes(query)
    );
}

const filteredCities = computed(() => filteredOptions(cities, searchCity.value, "city_name"));
const filteredZones = computed(() => filteredOptions(zones, searchZone.value, "zone_name"));
const filteredAreas = computed(() => filteredOptions(areas, searchArea.value, "area_name"));
const filteredPoints = computed(() => filteredOptions(points, searchPoint.value, "point_name"));
const filteredRoutes = computed(() => filteredOptions(routes, searchRoute.value, "route_name"));

function selectedDisplay(names, emptyText = "Select") {
    const safeNames = Array.isArray(names) ? names : [];

    if (safeNames.length === 0) {
        return emptyText;
    }

    if (safeNames.length <= 3) {
        return safeNames.join(", ");
    }

    return `${safeNames.slice(0, 3).join(", ")}, +${safeNames.length - 3} more`;
}

function hasItems(value) {
    return Array.isArray(value) && value.length > 0;
}


/* =========================================================
   PAGE STATE
========================================================= */

const loading = ref(false);
const errorMessage = ref("");

const customers = ref([]);
const customerCount = ref(0);


/* =========================================================
   MAP STATE
========================================================= */

const mapContainer = ref(null);
const mapInstance = ref(null);

const customerMarkers = ref([]);

/*
 * Leaflet polygon layers.
 *
 * drawnBoundaries stores every polygon currently on the map.
 * drawnBoundary remains the latest/active polygon so the existing UI
 * can continue to use the same ref.
 */
const drawnBoundaries = ref([]);
const drawnBoundary = ref(null);

/*
 * Each boundary gets a stable color.
 * Customers inside a boundary use the same color as that boundary.
 */
const boundaryColors = [
    "#2563eb", // Blue
    "#9333ea", // Purple
    "#ea580c", // Orange
    "#16a34a", // Green
    "#dc2626", // Red
    "#0891b2", // Cyan
    "#ca8a04", // Yellow
    "#db2777"  // Pink
];

/*
 * Route colors are independent from drawing order.
 * The route itself is the source of truth for customer color.
 */
const routeColors = [
    "#2563eb", // Blue
    "#9333ea", // Purple
    "#ea580c", // Orange
    "#16a34a", // Green
    "#dc2626", // Red
    "#0891b2", // Cyan
    "#ca8a04", // Yellow
    "#db2777"  // Pink
];

/* Route name -> stable color */
const routeColorByName = new Map();
let nextRouteColorIndex = 0;

/* Leaflet layer -> assigned color */
const boundaryColorByLayer = new Map();
let nextBoundaryColorIndex = 0;

/* Customer ID -> { layer, color } */
const customerBoundaryAssignments = ref({});

/*
 * Customers currently selected.
 *
 * We store customer objects here so later
 * we can send their IDs to ERPNext.
 */
const selectedCustomers = ref([]);


/* =========================================================
   HELPERS
========================================================= */

function getFieldValue(row, field, fallback = "") {
    if (
        row &&
        row[field] !== undefined &&
        row[field] !== null
    ) {
        return row[field];
    }

    return fallback;
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function selectedName(list, value, field) {
    const safeList = Array.isArray(list) ? list : [];
    const item = safeList.find(row => row?.name === value);

    return item
        ? getFieldValue(item, field, value)
        : value;
}


/* =========================================================
   CUSTOMER IDENTIFICATION
========================================================= */

function getCustomerId(customer) {
    return String(
        customer?.name ||
        customer?.customer_id ||
        customer?.customer_name ||
        ""
    );
}


function isCustomerSelected(customer) {
    const customerId = getCustomerId(customer);

    return selectedCustomers.value.some(
        item => getCustomerId(item) === customerId
    );
}


/* =========================================================
   FILTER API
========================================================= */

async function loadStates() {
    try {
        const response = await frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "State",
                filters: {
                    status: "Active"
                },
                fields: [
                    "name",
                    "state_name"
                ],
                order_by: "state_name asc",
                limit_page_length: 500
            }
        });

        states.value = response.message || [];

    } catch (error) {
        console.error(
            "Failed to load states:",
            error
        );

        errorMessage.value =
            "Unable to load states.";
    }
}


async function loadFilters({
    state = null,
    city = null,
    zone = null,
    area = null,
    point = null
} = {}) {

    try {
        const response = await frappe.call({
            method:
                "dairy_management.api.route_planner_filters",

            args: {
                state,
                city,
                zone,
                area,
                point
            }
        });

        return response.message || {
            cities: [],
            zones: [],
            areas: [],
            points: [],
            routes: []
        };

    } catch (error) {

        console.error(
            "Failed to load route planner filters:",
            error
        );

        errorMessage.value =
            "Unable to load geography filters.";

        return {
            cities: [],
            zones: [],
            areas: [],
            points: [],
            routes: []
        };
    }
}


/* =========================================================
   STATE CHANGE
========================================================= */

function mergeFilterRows(rows) {
    const seen = new Set();
    return (rows || []).filter(row => {
        const key = String(row?.name || "");
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}


async function stateChanged() {
    selectedCity.value = [];
    selectedZone.value = [];
    selectedArea.value = [];
    selectedPoint.value = [];
    selectedRoute.value = [];
    openDropdown.value = "";
    searchCity.value = "";
    searchZone.value = "";
    searchArea.value = "";
    searchPoint.value = "";
    searchRoute.value = "";
    cities.value = [];
    zones.value = [];
    areas.value = [];
    points.value = [];
    routes.value = [];
    customers.value = [];
    customerCount.value = 0;
    clearCustomerMap();

    if (!selectedState.value) return;

    loading.value = true;
    const data = await loadFilters({ state: selectedState.value });
    cities.value = data.cities || [];
    loading.value = false;
}

async function cityChanged() {
    selectedZone.value = [];
    selectedArea.value = [];
    selectedPoint.value = [];
    selectedRoute.value = [];
    zones.value = [];
    areas.value = [];
    points.value = [];
    routes.value = [];
    customers.value = [];
    customerCount.value = 0;
    clearCustomerMap();

    if (!hasItems(selectedCity.value)) return;

    loading.value = true;
    try {
        const responses = await Promise.all(selectedCity.value.map(city =>
            loadFilters({ state: selectedState.value, city })
        ));
        zones.value = mergeFilterRows(responses.flatMap(data => data.zones || []));
    } finally {
        loading.value = false;
    }
}

async function zoneChanged() {
    selectedArea.value = [];
    selectedPoint.value = [];
    selectedRoute.value = [];
    areas.value = [];
    points.value = [];
    routes.value = [];
    customers.value = [];
    customerCount.value = 0;
    clearCustomerMap();

    if (!hasItems(selectedZone.value)) return;

    loading.value = true;
    try {
        const responses = await Promise.all(selectedZone.value.map(zone =>
            loadFilters({ state: selectedState.value, zone })
        ));
        areas.value = mergeFilterRows(responses.flatMap(data => data.areas || []));
    } finally {
        loading.value = false;
    }
}

async function areaChanged() {
    selectedPoint.value = [];
    selectedRoute.value = [];
    points.value = [];
    routes.value = [];
    customers.value = [];
    customerCount.value = 0;
    clearCustomerMap();

    if (!hasItems(selectedArea.value)) return;

    loading.value = true;
    try {
        const responses = await Promise.all(selectedArea.value.map(area =>
            loadFilters({ state: selectedState.value, area })
        ));
        points.value = mergeFilterRows(responses.flatMap(data => data.points || []));
    } finally {
        loading.value = false;
    }
}

async function pointChanged() {
    selectedRoute.value = [];
    routes.value = [];
    customers.value = [];
    customerCount.value = 0;
    clearCustomerMap();

    if (!hasItems(selectedPoint.value)) return;

    loading.value = true;
    try {
        const responses = await Promise.all(selectedPoint.value.map(point =>
            loadFilters({ state: selectedState.value, point })
        ));
        routes.value = mergeFilterRows(responses.flatMap(data => data.routes || []));
    } finally {
        loading.value = false;
    }
}

async function routeChanged() {
    customers.value = [];
    customerCount.value = 0;
    selectedCustomers.value = [];
    clearCustomerMap();

    if (!hasItems(selectedRoute.value)) return;
    await loadRouteCustomers();
}


/* =========================================================
   LOAD CUSTOMERS
========================================================= */

async function loadRouteCustomers() {
    loading.value = true;
    errorMessage.value = "";

    try {
        const responses = await Promise.all(selectedRoute.value.map(route =>
            frappe.call({
                method: "dairy_management.api.route_planner_customers",
                args: {
                    state: selectedState.value,
                    city: null,
                    zone: null,
                    area: null,
                    point: null,
                    route
                }
            })
        ));

        const customerMap = new Map();

        responses.forEach(response => {
            const data = response.message || {};
            (data.customers || []).forEach(customer => {
                const customerId = getCustomerId(customer);
                if (customerId && !customerMap.has(customerId)) {
                    customerMap.set(customerId, customer);
                }
            });
        });

        customers.value = Array.from(customerMap.values());
        customerCount.value = customers.value.length;
        selectedCustomers.value = [];

        await nextTick();
        await initializeCustomerMap();
    } catch (error) {
        console.error("Failed to load customers:", error);
        errorMessage.value = "Unable to load customers.";
    } finally {
        loading.value = false;
    }
}


/* =========================================================
   CLEAR CUSTOMER SELECTION
========================================================= */

function clearSelection() {

    selectedCustomers.value = [];

    updateAllMarkerStyles();
}


/* =========================================================
   TOGGLE CUSTOMER SELECTION
========================================================= */

function toggleCustomerSelection(customer) {

    const customerId =
        getCustomerId(customer);

    if (!customerId) {
        return;
    }

    const existingIndex =
        selectedCustomers.value.findIndex(
            item =>
                getCustomerId(item) === customerId
        );

    if (existingIndex >= 0) {

        selectedCustomers.value.splice(
            existingIndex,
            1
        );

    } else {

        selectedCustomers.value.push(
            customer
        );
    }

    updateAllMarkerStyles();
}


/* =========================================================
   BOUNDARY / CUSTOMER COLOR HELPERS
========================================================= */

function getRouteColor(routeName) {
    const name = String(routeName || "").trim();

    if (!name) {
        return "#64748b";
    }

    if (routeColorByName.has(name)) {
        return routeColorByName.get(name);
    }

    const color =
        routeColors[
            nextRouteColorIndex % routeColors.length
        ];

    nextRouteColorIndex += 1;

    routeColorByName.set(name, color);

    return color;
}


function getBoundaryColor(boundaryLayer) {
    if (!boundaryLayer) {
        return "#2563eb";
    }

    if (boundaryColorByLayer.has(boundaryLayer)) {
        return boundaryColorByLayer.get(boundaryLayer);
    }

    const color =
        boundaryColors[
            nextBoundaryColorIndex % boundaryColors.length
        ];

    nextBoundaryColorIndex += 1;

    boundaryColorByLayer.set(
        boundaryLayer,
        color
    );

    return color;
}


function isCustomerInsideLayer(customer, boundaryLayer) {
    const latitude = Number(customer?.latitude);
    const longitude = Number(customer?.longitude);

    if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude) ||
        !boundaryLayer
    ) {
        return false;
    }

    try {
        const customerPoint = turfPoint([
            longitude,
            latitude
        ]);

        return booleanPointInPolygon(
            customerPoint,
            boundaryLayer.toGeoJSON()
        );
    } catch (error) {
        console.warn(
            "Unable to check customer against boundary:",
            error
        );
        return false;
    }
}


/*
 * Recalculate the boundary assignment for EVERY customer.
 *
 * If boundaries overlap, the most recently drawn boundary wins.
 * That means a customer belongs to exactly one color/group.
 */
function recalculateBoundaryAssignments() {
    const assignments = {};
    const insideCustomers = [];

    if (!drawnBoundaries.value.length) {
        customerBoundaryAssignments.value = assignments;
        return insideCustomers;
    }

    customers.value.forEach((customer) => {
        const customerId = getCustomerId(customer);

        if (!customerId) {
            return;
        }

        let assignedBoundary = null;
        let assignedColor = null;

        /*
         * Iterate in creation order.
         * Later boundaries overwrite earlier ones.
         */
        drawnBoundaries.value.forEach((boundaryLayer) => {
            if (
                isCustomerInsideLayer(
                    customer,
                    boundaryLayer
                )
            ) {
                assignedBoundary = boundaryLayer;
                assignedColor = getBoundaryColor(
                    boundaryLayer
                );
            }
        });

        if (assignedBoundary) {
            assignments[customerId] = {
                layer: assignedBoundary,
                color: assignedColor
            };

            insideCustomers.push(customer);
        }
    });

    customerBoundaryAssignments.value = assignments;

    return insideCustomers;
}


function getCustomersInsideBoundaries() {
    return recalculateBoundaryAssignments();
}


function selectAllInsideBoundary() {
    const insideCustomers =
        recalculateBoundaryAssignments();

    selectedCustomers.value =
        insideCustomers;

    updateAllMarkerStyles();

    console.log(
        "Customers inside boundaries:",
        insideCustomers.length
    );

    console.log(
        "Selected customer IDs:",
        insideCustomers.map(
            customer => getCustomerId(customer)
        )
    );
}


/* =========================================================
   DETECT / REFRESH CUSTOMERS INSIDE ALL BOUNDARIES
========================================================= */

function detectCustomersInsideBoundaries() {
    if (!drawnBoundaries.value.length) {
        customerBoundaryAssignments.value = {};
        selectedCustomers.value = [];
        updateAllMarkerStyles();
        return;
    }

    const insideCustomers =
        recalculateBoundaryAssignments();

    /*
     * Boundary membership is the automatic selection.
     * Manual marker selection can still be toggled afterwards.
     */
    selectedCustomers.value =
        insideCustomers;

    updateAllMarkerStyles();

    console.log(
        "Customers inside boundaries:",
        insideCustomers.length
    );

    console.log(
        "Selected customer IDs:",
        insideCustomers.map(
            customer => getCustomerId(customer)
        )
    );
}


/*
 * Backward-compatible helper for any existing calls.
 */
function detectCustomersInsideBoundary(boundaryLayer) {
    if (
        boundaryLayer &&
        !drawnBoundaries.value.includes(boundaryLayer)
    ) {
        drawnBoundaries.value.push(boundaryLayer);
    }

    if (boundaryLayer) {
        drawnBoundary.value = boundaryLayer;
        getBoundaryColor(boundaryLayer);
    }

    detectCustomersInsideBoundaries();
}


/* =========================================================
   UPDATE MARKER STYLES
========================================================= */

const updateAllMarkerStyles = () => {
    customerMarkers.value.forEach((markerInfo) => {
        const customerId =
            getCustomerId(markerInfo.customer);

        const selected =
            selectedCustomers.value.some(
                (customer) =>
                    getCustomerId(customer) === customerId
            );

        const assignment =
            customerBoundaryAssignments.value[
                customerId
            ];

        /*
         * Route color has priority over boundary color.
         * This guarantees that every customer belonging to the
         * same ERPNext route always has the same color.
         */
        const routeColor =
            getRouteColor(markerInfo.customer?.route);

        const displayColor =
            routeColor || assignment?.color || "#2563eb";

        const markerElement =
            markerInfo.marker.getElement();

        if (!markerElement) {
            return;
        }

        const markerContainer =
            markerElement.querySelector(
                ".customer-marker"
            );

        if (!markerContainer) {
            return;
        }

        /* Remove old dynamic color first. */
        markerContainer.classList.remove(
            "customer-marker-assigned"
        );

        markerContainer.style.removeProperty(
            "--customer-color"
        );

        markerContainer.style.removeProperty(
            "--customer-color-soft"
        );

        if (displayColor) {
            markerContainer.classList.add(
                "customer-marker-assigned"
            );

            markerContainer.style.setProperty(
                "--customer-color",
                displayColor
            );

            markerContainer.style.setProperty(
                "--customer-color-soft",
                hexToRgba(
                    displayColor,
                    0.20
                )
            );

            markerContainer.setAttribute(
                "data-route-color",
                displayColor
            );
        }

        if (selected) {
            markerContainer.classList.add(
                "customer-marker-selected"
            );
        } else {
            markerContainer.classList.remove(
                "customer-marker-selected"
            );
        }
    });
};


function hexToRgba(hex, alpha) {
    const normalized =
        String(hex || "")
            .replace("#", "")
            .trim();

    if (normalized.length !== 6) {
        return `rgba(37, 99, 235, ${alpha})`;
    }

    const red = parseInt(
        normalized.slice(0, 2),
        16
    );

    const green = parseInt(
        normalized.slice(2, 4),
        16
    );

    const blue = parseInt(
        normalized.slice(4, 6),
        16
    );

    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}


/* =========================================================
   CLEAR DRAWN BOUNDARY
========================================================= */

function clearBoundary() {
    if (mapInstance.value) {
        drawnBoundaries.value.forEach((boundaryLayer) => {
            try {
                if (
                    boundaryLayer &&
                    mapInstance.value.hasLayer(
                        boundaryLayer
                    )
                ) {
                    mapInstance.value.removeLayer(
                        boundaryLayer
                    );
                }
            } catch (error) {
                console.warn(
                    "Unable to remove boundary:",
                    error
                );
            }
        });
    }

    drawnBoundaries.value = [];
    drawnBoundary.value = null;
    boundaryColorByLayer.clear();
    nextBoundaryColorIndex = 0;
    customerBoundaryAssignments.value = {};
    selectedCustomers.value = [];

    updateAllMarkerStyles();

    console.log(
        "All route boundaries cleared"
    );
}


/* =========================================================
   CLEAR MAP
========================================================= */

function clearCustomerMap() {

    /*
     * Remove customer markers
     */

    customerMarkers.value.forEach(
        markerInfo => {

            try {

                if (
                    markerInfo.marker &&
                    mapInstance.value
                ) {
                    mapInstance.value.removeLayer(
                        markerInfo.marker
                    );
                }

            } catch (error) {

                console.warn(
                    "Unable to remove marker:",
                    error
                );
            }
        }
    );

    customerMarkers.value = [];


    /*
     * Remove map
     */

    if (mapInstance.value) {

        try {

            /*
             * Remove Geoman controls/events
             */

            if (
                mapInstance.value.pm &&
                mapInstance.value.pm.removeControls
            ) {

                mapInstance.value.pm.removeControls();
            }

            mapInstance.value.remove();

        } catch (error) {

            console.warn(
                "Unable to remove map:",
                error
            );
        }
    }

    mapInstance.value = null;

    drawnBoundaries.value = [];
    drawnBoundary.value = null;
    boundaryColorByLayer.clear();
    nextBoundaryColorIndex = 0;
    customerBoundaryAssignments.value = {};

    selectedCustomers.value = [];
}


/* =========================================================
   INITIALIZE LEAFLET MAP
========================================================= */

async function initializeCustomerMap() {

    await nextTick();

    if (!mapContainer.value) {
        return;
    }


    /*
     * Clean previous map
     */

    clearCustomerMap();


    /*
     * Validate customers
     */

    const validCustomers =
        customers.value.filter(
            customer => {

                const latitude =
                    Number(customer.latitude);

                const longitude =
                    Number(customer.longitude);

                return (
                    Number.isFinite(latitude) &&
                    Number.isFinite(longitude)
                );
            }
        );


    if (!validCustomers.length) {
        return;
    }


    /*
     * First customer
     */

    const firstCustomer =
        validCustomers[0];


    const firstLatitude =
        Number(firstCustomer.latitude);

    const firstLongitude =
        Number(firstCustomer.longitude);


    /* =====================================================
       CREATE LEAFLET MAP
    ===================================================== */

    mapInstance.value =
        L.map(
            mapContainer.value,
            {
                zoomControl: true
            }
        );


    /* =====================================================
       OPENSTREETMAP
    ===================================================== */

    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }
    ).addTo(
        mapInstance.value
    );


    /* =====================================================
       INITIAL MAP POSITION
    ===================================================== */

    mapInstance.value.setView(
        [
            firstLatitude,
            firstLongitude
        ],
        14
    );


    /* =====================================================
       GEOMAN CONTROLS
    ===================================================== */

    if (
        mapInstance.value.pm &&
        mapInstance.value.pm.addControls
    ) {

        mapInstance.value.pm.addControls({

            position: "topleft",

            drawText: false,

            drawCircle: false,

            drawCircleMarker: false,

            drawMarker: false,

            drawPolyline: false,

            drawRectangle: false,

            drawPolygon: true,

            editMode: true,

            dragMode: false,

            cutPolygon: false,

            removalMode: true,

            rotateMode: false
        });
    }


    /* =====================================================
       GEOMAN CREATE
    ===================================================== */

    mapInstance.value.on(
        "pm:create",
        event => {
            const layer = event.layer;

            if (event.shape !== "Polygon") {
                return;
            }

            /*
             * Keep every polygon on the map.
             */
            if (!drawnBoundaries.value.includes(layer)) {
                drawnBoundaries.value.push(layer);
            }

            drawnBoundary.value = layer;

            /*
             * Give this boundary its own stable color.
             */
            const boundaryColor =
                getBoundaryColor(layer);

            layer.setStyle({
                color: boundaryColor,
                weight: 3,
                opacity: 1,
                fillColor: boundaryColor,
                fillOpacity: 0.10
            });

            /*
             * Live update when the polygon is edited.
             * This means stretching a boundary immediately
             * recolors newly included customers.
             */
            layer.on(
                "pm:edit",
                () => {
                    detectCustomersInsideBoundaries();
                }
            );

            layer.on(
                "pm:dragend",
                () => {
                    detectCustomersInsideBoundaries();
                }
            );

            detectCustomersInsideBoundaries();

            console.log(
                "Route boundary created. Total boundaries:",
                drawnBoundaries.value.length,
                "Color:",
                boundaryColor
            );

            /*
             * Keep polygon drawing active so another polygon
             * can be drawn immediately after finishing this one.
             */
            setTimeout(() => {
                if (
                    mapInstance.value &&
                    mapInstance.value.pm
                ) {
                    try {
                        mapInstance.value.pm.enableDraw(
                            "Polygon",
                            {
                                continueDrawing: true
                            }
                        );
                    } catch (error) {
                        console.warn(
                            "Unable to continue polygon drawing:",
                            error
                        );
                    }
                }
            }, 50);
        }
    );


    /* =====================================================
       GEOMAN EDIT
    ===================================================== */

    mapInstance.value.on(
        "pm:edit",
        event => {
            const layer = event.layer;

            if (
                !drawnBoundaries.value.includes(layer)
            ) {
                return;
            }

            detectCustomersInsideBoundaries();

            console.log(
                "Route boundary updated. Total boundaries:",
                drawnBoundaries.value.length
            );
        }
    );


    /* =====================================================
       GEOMAN REMOVE
    ===================================================== */

    mapInstance.value.on(
        "pm:remove",
        event => {
            const layer = event.layer;

            const index =
                drawnBoundaries.value.indexOf(layer);

            if (index === -1) {
                return;
            }

            drawnBoundaries.value.splice(
                index,
                1
            );

            boundaryColorByLayer.delete(layer);

            drawnBoundary.value =
                drawnBoundaries.value.length
                    ? drawnBoundaries.value[
                        drawnBoundaries.value.length - 1
                    ]
                    : null;

            detectCustomersInsideBoundaries();

            console.log(
                "Route boundary deleted. Remaining boundaries:",
                drawnBoundaries.value.length
            );
        }
    );


    /* =====================================================
       CUSTOMER MARKERS
    ===================================================== */


    const bounds =
        L.latLngBounds([]);


    validCustomers.forEach(
        customer => {

            const latitude =
                Number(customer.latitude);

            const longitude =
                Number(customer.longitude);


            bounds.extend([
                latitude,
                longitude
            ]);


            /* =================================================
               MARKER ELEMENT
            ================================================= */

            const markerElement =
                document.createElement(
                    "div"
                );

            markerElement.className =
                "customer-marker";


            markerElement.innerHTML = `
                <div class="customer-marker-dot"></div>
            `;



            /* =================================================
               POPUP DATA
            ================================================= */

            const customerName =
                escapeHtml(
                    customer.customer_name ||
                    customer.name
                );


            const customerId =
                escapeHtml(
                    customer.name
                );


            const routeName =
                escapeHtml(
                    customer.route || ""
                );


            const pointName =
                escapeHtml(
                    customer.pickpoint__warehouse ||
                    ""
                );


            const popupHtml = `
                <div
                    style="
                        min-width:220px;
                        line-height:1.6;
                    "
                >

                    <strong>
                        ${customerName}
                    </strong>

                    <br>

                    <span>
                        ID:
                        ${customerId}
                    </span>

                    <br>

                    <span>
                        Route:
                        ${routeName}
                    </span>

                    <br>

                    <span>
                        Point:
                        ${pointName}
                    </span>

                    <br>

                    <span>
                        GPS:
                        ${latitude.toFixed(6)},
                        ${longitude.toFixed(6)}
                    </span>

                    <br><br>

                    <button
                        type="button"
                        class="customer-popup-select"
                    >
                        ${
                            isCustomerSelected(
                                customer
                            )
                                ? "Remove from Selection"
                                : "Select Customer"
                        }
                    </button>

                </div>
            `;


            /* =================================================
               LEAFLET ICON
            ================================================= */

            const markerIcon =
                L.divIcon({

                    className:
                        "customer-marker-wrapper",

                    html:
                        markerElement.outerHTML,

                    iconSize: [
                        24,
                        24
                    ],

                    iconAnchor: [
                        12,
                        12
                    ],

                    popupAnchor: [
                        0,
                        -12
                    ]
                });


            /* =================================================
               CREATE LEAFLET MARKER
            ================================================= */

            const marker =
                L.marker(
                    [
                        latitude,
                        longitude
                    ],
                    {
                        icon:
                            markerIcon,

                        title:
                            customer.customer_name ||
                            customer.name,

                        /*
                         * Customer GPS is the source of truth.
                         * Never allow the customer marker to be dragged.
                         */
                        draggable: false,

                        /*
                         * Do not let Leaflet-Geoman treat customer markers
                         * as editable/draggable map objects.
                         */
                        pmIgnore: true
                    }
                );

            /*
             * Final safety check: customer markers are display-only.
             * Their position always remains exactly at the ERPNext
             * latitude/longitude returned by the customer API.
             */
            if (marker.dragging) {
                marker.dragging.disable();
            }

            if (marker.pm && marker.pm.disable) {
                marker.pm.disable();
            }


            /* =================================================
               POPUP
            ================================================= */

            marker.bindPopup(
                popupHtml,
                {
                    closeButton: true
                }
            );


            /* =================================================
               MARKER CLICK
            ================================================= */

            marker.on(
                "click",
                () => {

                    toggleCustomerSelection(
                        customer
                    );
                }
            );


            /* =================================================
               POPUP OPEN
            ================================================= */

            marker.on(
                "popupopen",
                event => {

                    const popupElement =
                        event.popup
                            .getElement();

                    if (!popupElement) {
                        return;
                    }


                    const selectButton =
                        popupElement.querySelector(
                            ".customer-popup-select"
                        );


                    if (!selectButton) {
                        return;
                    }


                    selectButton.onclick =
                        () => {

                            toggleCustomerSelection(
                                customer
                            );


                            selectButton.textContent =
                                isCustomerSelected(
                                    customer
                                )
                                    ? "Remove from Selection"
                                    : "Select Customer";
                        };
                }
            );


            /*
             * Add marker to map.
             */

            marker.addTo(
                mapInstance.value
            );


            /*
             * Store marker information.
             */

            customerMarkers.value.push({

                marker,

                customer,

                element:
                    markerElement
            });

            /* Apply the current boundary/customer color immediately. */
            updateAllMarkerStyles();
        }
    );


    /* =====================================================
       FIT MAP TO CUSTOMERS
    ===================================================== */

    if (
        bounds.isValid()
    ) {

        mapInstance.value.fitBounds(
            bounds,
            {
                padding: [
                    50,
                    50
                ],

                maxZoom: 17,

                animate: true
            }
        );
    }


    /*
     * Leaflet sometimes needs a resize after
     * the Vue container becomes visible.
     */

    await nextTick();

    setTimeout(
        () => {

            if (
                mapInstance.value
            ) {

                mapInstance.value.invalidateSize();
            }

        },
        100
    );


    console.log(
        "Leaflet customer map initialized:",
        validCustomers.length,
        "customers"
    );
}


/* =========================================================
   LIFECYCLE
========================================================= */

onMounted(
    async () => {

        emit(
            "title",
            title
        );

        await loadStates();
    }
);


onBeforeUnmount(
    () => {

        clearCustomerMap();
    }
);
</script>


<template>

    <div class="route-planner-page">

        <!-- =================================================
             PAGE HEADER
        ================================================= -->

        <div class="page-header">

            <div>

                <h1>
                    Route Planner
                </h1>

                <p>
                    Plan and manage customer routes
                    using GPS locations.
                </p>

            </div>


            <div class="header-cards">

                <div class="customer-count-card">

                    <span>
                        Customers
                    </span>

                    <strong>
                        {{ customerCount }}
                    </strong>

                </div>


                <div
                    v-if="hasItems(selectedRoute)"
                    class="customer-count-card selected-count-card"
                >

                    <span>
                        Selected
                    </span>

                    <strong>
                        {{ selectedCustomers.length || 0 }}
                    </strong>

                </div>

            </div>

        </div>


        <!-- =================================================
             ERROR
        ================================================= -->

        <div
            v-if="errorMessage"
            class="error-message"
        >
            {{ errorMessage }}
        </div>


        <!-- =================================================
             FILTERS
        ================================================= -->

        <div class="filter-card">

            <div class="filter-group">
                <label>State</label>
                <select v-model="selectedState" @change="stateChanged">
                    <option value="">Select State</option>
                    <option v-for="state in states" :key="state.name" :value="state.name">
                        {{ state.state_name }}
                    </option>
                </select>
            </div>

            <div class="filter-group">
                <label>City</label>
                <div class="multi-select">
                    <button type="button" class="multi-select-trigger"
                        :disabled="!selectedState || !hasItems(cities)"
                        @click="toggleDropdown('city')">
                        <span class="multi-select-text">{{ selectedDisplay(selectedCityNames, 'Select City') }}</span>
                        <span class="multi-select-arrow">▼</span>
                    </button>
                    <div v-if="openDropdown === 'city'" class="multi-select-menu">
                        <input v-model="searchCity" class="multi-select-search" placeholder="Search city...">
                        <div class="multi-select-actions">
                            <button type="button" @click="selectAllLevel('city')">Select All</button>
                            <button type="button" @click="clearLevel('city')">Clear All</button>
                        </div>
                        <label v-for="city in filteredCities" :key="city.name" class="multi-select-option">
                            <input type="checkbox" :checked="selectedCity.includes(city.name)"
                                @change="toggleSelection('city', city.name)">
                            <span>{{ city.city_name }}</span>
                        </label>
                        <div v-if="!hasItems(filteredCities)" class="multi-select-empty">No cities found</div>
                    </div>
                </div>
            </div>

            <div class="filter-group">
                <label>Zone</label>
                <div class="multi-select">
                    <button type="button" class="multi-select-trigger"
                        :disabled="!hasItems(selectedCity) || !hasItems(zones)"
                        @click="toggleDropdown('zone')">
                        <span class="multi-select-text">{{ selectedDisplay(selectedZoneNames, 'Select Zone') }}</span>
                        <span class="multi-select-arrow">▼</span>
                    </button>
                    <div v-if="openDropdown === 'zone'" class="multi-select-menu">
                        <input v-model="searchZone" class="multi-select-search" placeholder="Search zone...">
                        <div class="multi-select-actions">
                            <button type="button" @click="selectAllLevel('zone')">Select All</button>
                            <button type="button" @click="clearLevel('zone')">Clear All</button>
                        </div>
                        <label v-for="zone in filteredZones" :key="zone.name" class="multi-select-option">
                            <input type="checkbox" :checked="selectedZone.includes(zone.name)"
                                @change="toggleSelection('zone', zone.name)">
                            <span>{{ zone.zone_name }}</span>
                        </label>
                        <div v-if="!hasItems(filteredZones)" class="multi-select-empty">No zones found</div>
                    </div>
                </div>
            </div>

            <div class="filter-group">
                <label>Area</label>
                <div class="multi-select">
                    <button type="button" class="multi-select-trigger"
                        :disabled="!hasItems(selectedZone) || !hasItems(areas)"
                        @click="toggleDropdown('area')">
                        <span class="multi-select-text">{{ selectedDisplay(selectedAreaNames, 'Select Area') }}</span>
                        <span class="multi-select-arrow">▼</span>
                    </button>
                    <div v-if="openDropdown === 'area'" class="multi-select-menu">
                        <input v-model="searchArea" class="multi-select-search" placeholder="Search area...">
                        <div class="multi-select-actions">
                            <button type="button" @click="selectAllLevel('area')">Select All</button>
                            <button type="button" @click="clearLevel('area')">Clear All</button>
                        </div>
                        <label v-for="area in filteredAreas" :key="area.name" class="multi-select-option">
                            <input type="checkbox" :checked="selectedArea.includes(area.name)"
                                @change="toggleSelection('area', area.name)">
                            <span>{{ area.area_name }}</span>
                        </label>
                        <div v-if="!hasItems(filteredAreas)" class="multi-select-empty">No areas found</div>
                    </div>
                </div>
            </div>

            <div class="filter-group">
                <label>Point</label>
                <div class="multi-select">
                    <button type="button" class="multi-select-trigger"
                        :disabled="!hasItems(selectedArea) || !hasItems(points)"
                        @click="toggleDropdown('point')">
                        <span class="multi-select-text">{{ selectedDisplay(selectedPointNames, 'Select Point') }}</span>
                        <span class="multi-select-arrow">▼</span>
                    </button>
                    <div v-if="openDropdown === 'point'" class="multi-select-menu">
                        <input v-model="searchPoint" class="multi-select-search" placeholder="Search point...">
                        <div class="multi-select-actions">
                            <button type="button" @click="selectAllLevel('point')">Select All</button>
                            <button type="button" @click="clearLevel('point')">Clear All</button>
                        </div>
                        <label v-for="point in filteredPoints" :key="point.name" class="multi-select-option">
                            <input type="checkbox" :checked="selectedPoint.includes(point.name)"
                                @change="toggleSelection('point', point.name)">
                            <span>{{ point.point_name }}</span>
                        </label>
                        <div v-if="!hasItems(filteredPoints)" class="multi-select-empty">No points found</div>
                    </div>
                </div>
            </div>

            <div class="filter-group">
                <label>Route</label>
                <div class="multi-select">
                    <button type="button" class="multi-select-trigger"
                        :disabled="!hasItems(selectedPoint) || !hasItems(routes)"
                        @click="toggleDropdown('route')">
                        <span class="multi-select-text">{{ selectedDisplay(selectedRouteNames, 'Select Route') }}</span>
                        <span class="multi-select-arrow">▼</span>
                    </button>
                    <div v-if="openDropdown === 'route'" class="multi-select-menu">
                        <input v-model="searchRoute" class="multi-select-search" placeholder="Search route...">
                        <div class="multi-select-actions">
                            <button type="button" @click="selectAllLevel('route')">Select All</button>
                            <button type="button" @click="clearLevel('route')">Clear All</button>
                        </div>
                        <label v-for="route in filteredRoutes" :key="route.name" class="multi-select-option">
                            <input type="checkbox" :checked="selectedRoute.includes(route.name)"
                                @change="toggleSelection('route', route.name)">
                            <span>{{ route.route_name }}</span>
                        </label>
                        <div v-if="!hasItems(filteredRoutes)" class="multi-select-empty">No routes found</div>
                    </div>
                </div>
            </div>

        </div>


        <!-- =================================================
             SELECTED GEOGRAPHY
        ================================================= -->

        <div class="selected-card">
            <div class="selected-label">Selected Geography</div>
            <div class="selected-value">
                <span v-text="selectedStateName"></span>

                <span v-if="hasItems(selectedCity)" class="geography-segment">
                    <span class="geography-arrow">→</span>
                    <span v-text="selectedCityName"></span>
                </span>

                <span v-if="hasItems(selectedZone)" class="geography-segment">
                    <span class="geography-arrow">→</span>
                    <span v-text="selectedZoneName"></span>
                </span>

                <span v-if="hasItems(selectedArea)" class="geography-segment">
                    <span class="geography-arrow">→</span>
                    <span v-text="selectedAreaName"></span>
                </span>

                <span v-if="hasItems(selectedPoint)" class="geography-segment">
                    <span class="geography-arrow">→</span>
                    <span v-text="selectedPointName"></span>
                </span>

                <span v-if="hasItems(selectedRoute)" class="geography-segment">
                    <span class="geography-arrow">→</span>
                    <span v-text="selectedRouteName"></span>
                </span>
            </div>
        </div>


        <!-- =================================================
             CUSTOMER MAP
        ================================================= -->

        <div class="map-card">

            <div class="map-header">

                <div>

                    <h2>
                        Customer Locations
                    </h2>

                    <p>
                        Customers assigned to the
                        selected route. GPS locations are locked.
                    </p>

                </div>


                <div class="map-actions">

                    <button
                        type="button"
                        class="map-action-button"
                        @click="selectAllInsideBoundary"
                        :disabled="!hasItems(drawnBoundaries)"
                    >
                        Select All Inside
                    </button>


                    <button
                        type="button"
                        class="map-action-button"
                        @click="clearSelection"
                        :disabled="!hasItems(selectedCustomers)"
                    >
                        Clear Selection
                    </button>


                    <button
                        type="button"
                        class="map-action-button danger"
                        @click="clearBoundary"
                        :disabled="!hasItems(drawnBoundaries)"
                    >
                        Clear Boundary
                    </button>


                    <div
                        v-if="hasItems(selectedRoute)"
                        class="route-badge"
                    >
                        {{ selectedRouteName }}
                    </div>

                </div>

            </div>


            <div
                v-if="loading"
                class="map-loading"
            >
                Loading...
            </div>


            <div
                ref="mapContainer"
                class="customer-map"
            ></div>


            <!-- =================================================
                 ROUTE COLOR LEGEND
            ================================================= -->

            <div
                v-if="hasItems(selectedRoute)"
                class="boundary-legend route-legend"
            >

                <div
                    v-for="routeName in selectedRouteNames"
                    :key="routeName"
                    class="boundary-legend-item"
                >
                    <span
                        class="boundary-legend-dot"
                        :style="{
                            backgroundColor: getRouteColor(routeName)
                        }"
                    ></span>

                    <span>
                        {{ routeName }}
                    </span>
                </div>

            </div>


            <!-- =================================================
                 BOUNDARY COLOR LEGEND
            ================================================= -->

            <div
                v-if="hasItems(drawnBoundaries)"
                class="boundary-legend"
            >

                <div
                    v-for="(boundaryLayer, index) in drawnBoundaries"
                    :key="index"
                    class="boundary-legend-item"
                >
                    <span
                        class="boundary-legend-dot"
                        :style="{
                            backgroundColor: getBoundaryColor(boundaryLayer)
                        }"
                    ></span>

                    <span>
                        Boundary {{ index + 1 }}
                    </span>
                </div>

            </div>


            <!-- =================================================
                 SELECTION INFORMATION
            ================================================= -->

            <div
                v-if="hasItems(selectedRoute)"
                class="selection-footer"
            >

                <div>

                    <strong>
                        {{ selectedCustomers.length || 0 }}
                    </strong>

                    customers selected

                </div>


                <div
                    v-if="hasItems(drawnBoundaries)"
                    class="boundary-status"
                >
                    {{ drawnBoundaries.length || 0 }}
                    {{ drawnBoundaries.length === 1 ? "Boundary" : "Boundaries" }}
                    active
                </div>

            </div>

        </div>

    </div>

</template>


<style scoped>

.route-planner-page {
    padding: 24px;
    background: #f8fafc;
    min-height: 100vh;
}


.page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
    margin-bottom: 20px;
}


.page-header h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 700;
    color: #334155;
}


.page-header p {
    margin: 8px 0 0;
    color: #64748b;
    font-size: 14px;
}


.header-cards {
    display: flex;
    gap: 10px;
}


.customer-count-card {
    min-width: 94px;
    padding: 12px 18px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    text-align: center;
}


.customer-count-card span {
    display: block;
    font-size: 12px;
    color: #64748b;
}


.customer-count-card strong {
    display: block;
    margin-top: 4px;
    font-size: 24px;
    color: #334155;
}


.selected-count-card {
    border-color: #2563eb;
}


.selected-count-card strong {
    color: #2563eb;
}


.error-message {
    margin-bottom: 16px;
    padding: 12px 16px;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    color: #b91c1c;
}


.filter-card {
    display: grid;
    grid-template-columns:
        repeat(6, minmax(0, 1fr));

    gap: 14px;

    padding: 20px;

    background: white;

    border: 1px solid #e2e8f0;

    border-radius: 10px;

    margin-bottom: 16px;
}


.filter-group {
    min-width: 0;
}


.filter-group label {
    display: block;

    margin-bottom: 7px;

    font-size: 12px;

    font-weight: 600;

    color: #475569;
}


.filter-group select {
    width: 100%;

    height: 38px;

    padding: 0 10px;

    border: 1px solid #cbd5e1;

    border-radius: 7px;

    background: white;

    color: #334155;

    font-size: 13px;

    outline: none;
}


.filter-group select:focus {
    border-color: #64748b;
}


.filter-group select:disabled {
    background: #f1f5f9;

    color: #94a3b8;

    cursor: not-allowed;
}


.multi-select {
    position: relative;
    width: 100%;
}

.multi-select-trigger {
    width: 100%;
    min-height: 38px;
    padding: 7px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    background: white;
    color: #334155;
    font-size: 13px;
    outline: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    cursor: pointer;
    text-align: left;
}

.multi-select-trigger:disabled {
    background: #f1f5f9;
    color: #94a3b8;
    cursor: not-allowed;
}

.multi-select-text {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

.multi-select-arrow {
    flex: 0 0 auto;
    color: #64748b;
    font-size: 10px;
}

.multi-select-menu {
    position: absolute;
    z-index: 1000;
    top: calc(100% + 5px);
    left: 0;
    width: 100%;
    min-width: 220px;
    max-height: 330px;
    overflow-y: auto;
    padding: 8px;
    background: white;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
}

.multi-select-search {
    width: 100%;
    height: 34px;
    padding: 0 9px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    outline: none;
    font-size: 12px;
    margin-bottom: 7px;
    box-sizing: border-box;
}

.multi-select-actions {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    padding: 2px 0 7px;
    border-bottom: 1px solid #e2e8f0;
    margin-bottom: 3px;
}

.multi-select-actions button {
    border: none;
    background: transparent;
    color: #2563eb;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    padding: 4px 2px;
}

.multi-select-option {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 34px;
    padding: 5px 6px;
    border-radius: 5px;
    cursor: pointer;
    color: #334155;
    font-size: 12px;
}

.multi-select-option:hover {
    background: #f8fafc;
}

.multi-select-option input {
    margin: 0;
    width: 15px;
    height: 15px;
    accent-color: #2563eb;
}

.multi-select-empty {
    padding: 14px 6px;
    text-align: center;
    color: #94a3b8;
    font-size: 12px;
}

.selected-card {
    padding: 18px 20px;

    background: white;

    border: 1px solid #e2e8f0;

    border-radius: 10px;

    margin-bottom: 16px;
}


.selected-label {
    font-size: 12px;

    color: #64748b;

    margin-bottom: 7px;
}


.geography-segment { display: inline; }

.geography-arrow {
    display: inline-block;
    margin: 0 8px;
    color: #94a3b8;
}


.selected-value {
    font-size: 14px;

    font-weight: 600;

    color: #334155;
}


.map-card {
    background: white;

    border: 1px solid #e2e8f0;

    border-radius: 10px;

    overflow: hidden;
}


.map-header {
    display: flex;

    justify-content: space-between;

    align-items: center;

    gap: 16px;

    padding: 18px 20px;

    border-bottom: 1px solid #e2e8f0;
}


.map-header h2 {
    margin: 0;

    font-size: 17px;

    font-weight: 600;

    color: #334155;
}


.map-header p {
    margin: 5px 0 0;

    font-size: 13px;

    color: #64748b;
}


.map-actions {
    display: flex;

    align-items: center;

    justify-content: flex-end;

    flex-wrap: wrap;

    gap: 8px;
}


.map-action-button {
    height: 34px;

    padding: 0 12px;

    border: 1px solid #cbd5e1;

    border-radius: 7px;

    background: white;

    color: #334155;

    font-size: 12px;

    font-weight: 600;

    cursor: pointer;
}


.map-action-button:hover:not(:disabled) {
    background: #f8fafc;
}


.map-action-button:disabled {
    opacity: 0.45;

    cursor: not-allowed;
}


.map-action-button.danger {
    color: #b91c1c;

    border-color: #fecaca;
}


.route-badge {
    padding: 7px 12px;

    border-radius: 20px;

    background: #f1f5f9;

    color: #334155;

    font-size: 12px;

    font-weight: 600;
}


.customer-map {
    width: 100%;

    height: 620px;

    position: relative;

    z-index: 1;
}


.map-loading {
    position: absolute;

    z-index: 20;

    margin: 12px;

    padding: 8px 12px;

    background: white;

    border: 1px solid #e2e8f0;

    border-radius: 6px;

    font-size: 12px;

    color: #475569;
}


.selection-footer {
    display: flex;

    justify-content: space-between;

    align-items: center;

    padding: 12px 20px;

    border-top: 1px solid #e2e8f0;

    background: #f8fafc;

    color: #475569;

    font-size: 13px;
}


.selection-footer strong {
    color: #2563eb;

    font-size: 16px;
}


.boundary-status {
    padding: 5px 10px;

    border-radius: 15px;

    background: #dbeafe;

    color: #1d4ed8;

    font-size: 12px;

    font-weight: 600;
}


/* =========================================================
   LEAFLET CUSTOMER MARKERS
========================================================= */

:global(.customer-marker-wrapper) {
    background: transparent !important;

    border: none !important;
}


:global(.customer-marker) {
    width: 24px;

    height: 24px;

    display: flex;

    align-items: center;

    justify-content: center;

    cursor: pointer;
}


:global(.customer-marker-dot) {
    width: 15px;
    height: 15px;
    border-radius: 50%;
    background: #2563eb;
    border: 3px solid white;
    box-shadow:
        0 2px 6px rgba(0, 0, 0, 0.35);
    transition:
        transform 0.15s ease,
        background 0.15s ease,
        box-shadow 0.15s ease;
}


/*
 * Customer belongs to a boundary.
 * The CSS variable is set from the boundary color.
 */
:global(.customer-marker-assigned .customer-marker-dot) {
    background: var(--customer-color, #2563eb);
    box-shadow:
        0 0 0 3px var(--customer-color-soft, rgba(37, 99, 235, 0.20)),
        0 2px 6px rgba(0, 0, 0, 0.35);
}


/*
 * Selected customer: same boundary color, slightly larger.
 */
:global(.customer-marker-selected .customer-marker-dot) {
    width: 20px;
    height: 20px;
    background: var(--customer-color, #16a34a);
    border: 3px solid white;
    box-shadow:
        0 0 0 4px var(--customer-color-soft, rgba(22, 163, 74, 0.20)),
        0 3px 8px rgba(0, 0, 0, 0.35);
}


/* =========================================================
   BOUNDARY COLOR LEGEND
========================================================= */

.boundary-legend {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 14px;
    padding: 10px 20px;
    border-top: 1px solid #e2e8f0;
    background: #ffffff;
}


.boundary-legend-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #475569;
    font-size: 12px;
    font-weight: 600;
}


.boundary-legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 0 0 1px #cbd5e1;
}


/* =========================================================
   POPUP BUTTON
========================================================= */

:global(.customer-popup-select) {
    width: 100%;

    padding: 7px 10px;

    border: 1px solid #cbd5e1;

    border-radius: 6px;

    background: #2563eb;

    color: white;

    font-size: 12px;

    font-weight: 600;

    cursor: pointer;
}


:global(.customer-popup-select:hover) {
    background: #1d4ed8;
}


/* =========================================================
   LEAFLET
========================================================= */

:global(.leaflet-container) {
    width: 100%;

    height: 100%;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background: #e2e8f0;
}


:global(.leaflet-control-zoom) {
    border: 1px solid #cbd5e1 !important;
}


:global(.leaflet-control-zoom a) {
    color: #334155 !important;
}


:global(.leaflet-popup-content) {
    margin: 12px;
}


:global(.leaflet-popup-content-wrapper) {
    border-radius: 8px;
}


@media (max-width: 1200px) {

    .filter-card {
        grid-template-columns:
            repeat(3, minmax(0, 1fr));
    }

}


@media (max-width: 900px) {

    .map-header {
        align-items: flex-start;

        flex-direction: column;
    }

    .map-actions {
        width: 100%;

        justify-content: flex-start;
    }

}


@media (max-width: 700px) {

    .route-planner-page {
        padding: 12px;
    }


    .page-header {
        flex-direction: column;
    }


    .header-cards {
        width: 100%;
    }


    .customer-count-card {
        flex: 1;
    }


    .filter-card {
        grid-template-columns:
            1fr;
    }


    .customer-map {
        height: 500px;
    }


    .selection-footer {
        align-items: flex-start;

        flex-direction: column;

        gap: 8px;
    }

}

</style>

// -*- mode: javascript; indent-tabs-mode: nil; c-basic-offset: 8 -*-

// Part of dump1090, a Mode S message decoder for RTLSDR devices.
//
// routes.js: resolve the departure and arrival airports of a flight
// from its callsign.
//
// The aircraft feed does not carry route data, so routes are looked up
// per callsign from a route cache server (see tools/logo-cache-proxy.py,
// which proxies the adsbdb public route API). Lookups are cached in
// memory for the session; the cache server stores them on disk.
//
// getRouteForFlight() is synchronous and returns null until the route
// has been fetched once; the fetch happens in the background and the
// next table refresh picks up the result.
//
// Copyright (c) 2026 dump1090 contributors
//
// This file is free software: you may copy, redistribute and/or modify it
// under the terms of the GNU General Public License as published by the
// Free Software Foundation, either version 2 of the License, or (at your
// option) any later version.

"use strict";

// In-memory route cache: callsign -> { dep: <ICAO>, arr: <ICAO> } or null
// when the route is unknown. Unknown routes are memoized so the cache
// server is not asked again during the session.
var AirlineRouteCache = {};

// Callsigns that currently have a fetch in flight (deduplication).
var AirlineRouteFetching = {};

// Base URL of the route cache server. When empty, routes are requested
// from the same origin (/route/<callsign>), which 404s unless a cache
// server is running; lookups then fail quietly and are not repeated.
function getAirlineRouteBaseUrl() {
    if (typeof AirlineLogoCacheUrl === "string" && AirlineLogoCacheUrl.length > 0) {
        return AirlineLogoCacheUrl.replace(/\/+$/, "");
    }
    return "";
}

// Normalize a callsign for route lookup: trimmed, uppercased, no
// internal spaces. Returns null for callsigns that are not flight
// numbers (e.g. registrations, empty).
function normalizeRouteCallsign(flight) {
    if (flight === null || flight === undefined) {
        return null;
    }
    var callsign = String(flight).trim().toUpperCase().replace(/\s+/g, "");
    if (callsign.length < 3 || callsign.length > 10) {
        return null;
    }
    // Flight numbers are designator + digits (or digits after a
    // registration-style prefix); skip pure-alphabetic callsigns.
    if (!/[0-9]/.test(callsign)) {
        return null;
    }
    // Skip callsigns that look like aircraft registrations (patterns
    // from operators.js); private aircraft have no scheduled route.
    if (typeof AirlineRegistrationPatterns !== "undefined") {
        for (var i = 0; i < AirlineRegistrationPatterns.length; ++i) {
            if (AirlineRegistrationPatterns[i].test(callsign)) {
                return null;
            }
        }
    }
    return callsign;
}

// Synchronous route lookup for a flight. Returns
// { dep: <ICAO>, arr: <ICAO> }, null when the route is unknown, or
// null while the first lookup is still in flight.
function getRouteForFlight(flight) {
    if (AirlineRoutesEnabled === false) {
        return null;
    }
    var callsign = normalizeRouteCallsign(flight);
    if (callsign === null) {
        return null;
    }
    if (callsign in AirlineRouteCache) {
        return AirlineRouteCache[callsign];
    }
    if (!(callsign in AirlineRouteFetching)) {
        fetchAirlineRoute(callsign);
    }
    return null;
}

function fetchAirlineRoute(callsign) {
    AirlineRouteFetching[callsign] = true;
    fetch(getAirlineRouteBaseUrl() + "/route/" + callsign, { cache: "no-store" })
        .then(function (response) {
            if (!response.ok) {
                AirlineRouteCache[callsign] = null;
                return;
            }
            return response.json();
        })
        .then(function (data) {
            if (data !== undefined && data !== null && typeof data.dep === "string" && typeof data.arr === "string") {
                AirlineRouteCache[callsign] = { dep: data.dep, arr: data.arr };
            } else if (data !== undefined) {
                AirlineRouteCache[callsign] = null;
            }
        })
        .catch(function () {
            AirlineRouteCache[callsign] = null;
        })
        .then(function () {
            delete AirlineRouteFetching[callsign];
        });
}

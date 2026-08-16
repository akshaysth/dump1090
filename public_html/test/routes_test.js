// -*- mode: javascript; indent-tabs-mode: nil; c-basic-offset: 8 -*-

// Part of dump1090, a Mode S message decoder for RTLSDR devices.
//
// routes_test.js: exercises the route lookup logic from routes.js.
// Open test/routes_test.html in a browser served from the webmap
// (a route cache server must be reachable for the live lookup checks).
//
// Copyright (c) 2026 dump1090 contributors
//
// This file is free software: you may copy, redistribute and/or modify it
// under the terms of the GNU General Public License as published by the
// Free Software Foundation, either version 2 of the License, or (at your
// option) any later version.

"use strict";

// Config values the test needs; normally provided by config.js.
var AirlineLogoCacheUrl = "";
var AirlineRoutesEnabled = true;

var results = [];

function check(condition, description) {
    results.push({ pass: !!condition, description: description });
}

function setup_routes_test() {
    // operators.js (for AirlineRegistrationPatterns) is loaded by the
    // HTML before this script; routes.js is loaded there too.
    run_tests();
}

function run_tests() {
    // Callsign normalization.
    check(normalizeRouteCallsign("EDV4978") === "EDV4978", "normalize 'EDV4978' -> EDV4978");
    check(normalizeRouteCallsign("EDV4978 ") === "EDV4978", "normalize padded 'EDV4978 ' -> EDV4978");
    check(normalizeRouteCallsign("aca1070") === "ACA1070", "normalize lowercase 'aca1070' -> ACA1070");
    check(normalizeRouteCallsign("EDV") === null, "no-digit callsign 'EDV' -> null");
    check(normalizeRouteCallsign("") === null, "empty callsign -> null");
    check(normalizeRouteCallsign(null) === null, "null callsign -> null");
    check(normalizeRouteCallsign("12345") === "12345", "numeric '12345' passes normalize (route lookup will 404)");

    // Registrations are skipped without a fetch.
    check(getRouteForFlight("N925MP") === null, "registration 'N925MP' -> null (skipped)");
    check(getRouteForFlight("CFAKD") === null, "registration 'CFAKD' -> null (skipped)");
    check(!("N925MP" in AirlineRouteFetching), "no fetch started for 'N925MP'");
    check(!("CFAKD" in AirlineRouteFetching), "no fetch started for 'CFAKD'");

    // Cached route lookup (sync).
    AirlineRouteCache["TEST1"] = { dep: "KAAA", arr: "KBBB" };
    var r = getRouteForFlight("TEST1 ");
    check(r !== null && r.dep === "KAAA" && r.arr === "KBBB", "cached route returned for padded callsign");
    check(r !== null && r.dep === "KAAA", "cached route dep is KAAA");
    delete AirlineRouteCache["TEST1"];

    // Disabled flag.
    AirlineRoutesEnabled = false;
    AirlineRouteCache["TEST2"] = { dep: "KAAA", arr: "KBBB" };
    check(getRouteForFlight("TEST2") === null, "routes disabled -> null even when cached");
    delete AirlineRouteCache["TEST2"];
    AirlineRoutesEnabled = true;

    // Live lookup against the route cache server (same origin /route/).
    // Uses a callsign from the live feed area; adsbdb returns a route.
    var live = getRouteForFlight("AAL1534");
    check(live === null, "live route 'AAL1534' is null while fetching");
    check("AAL1534" in AirlineRouteFetching, "live route fetch in flight for 'AAL1534'");
    check(!("AAL1534" in AirlineRouteCache), "live route not cached yet");

    window.setTimeout(function () {
        var r2 = getRouteForFlight("AAL1534");
        check(r2 !== null && typeof r2.dep === "string" && typeof r2.arr === "string",
              "live route 'AAL1534' resolved to " + (r2 !== null ? r2.dep + "->" + r2.arr : "null"));
        check(r2 !== null && r2.dep.length === 4 && r2.arr.length === 4,
              "live route codes are 4-char ICAO codes");
        check(r2 !== null && typeof r2.depLat === "number" && typeof r2.arrLat === "number",
              "live route carries airport coordinates");
        check(!("AAL1534" in AirlineRouteFetching), "fetch dedup flag cleared after completion");

        // Direction adjustment (shuttle flights reuse a callsign for
        // both directions): use the live KONT->KDFW route coordinates.
        var shuttleRoute = getRouteForFlight("AAL1534");
        var fwd = routeBearing(shuttleRoute.depLat, shuttleRoute.depLon, shuttleRoute.arrLat, shuttleRoute.arrLon);
        var planeForward = { flight: "AAL1534", position: [shuttleRoute.depLon, shuttleRoute.depLat], track: fwd };
        var planeReversed = { flight: "AAL1534", position: [shuttleRoute.arrLon, shuttleRoute.arrLat], track: (fwd + 180) % 360 };
        var rFwd = getRouteForPlane(planeForward);
        check(rFwd !== null && rFwd.dep === shuttleRoute.dep && rFwd.arr === shuttleRoute.arr,
              "plane tracking along route keeps dep/arr as stored");
        var rRev = getRouteForPlane(planeReversed);
        check(rRev !== null && rRev.dep === shuttleRoute.arr && rRev.arr === shuttleRoute.dep,
              "plane tracking the reverse way swaps dep/arr");

        // No coordinates (legacy payload) -> no adjustment.
        AirlineRouteCache["LEGACY1"] = { dep: "KAAA", arr: "KBBB" };
        var rLegacy = getRouteForPlane({ flight: "LEGACY1", position: [0, 0], track: 270 });
        check(rLegacy !== null && rLegacy.dep === "KAAA" && rLegacy.arr === "KBBB",
              "legacy route without coordinates is not adjusted");
        delete AirlineRouteCache["LEGACY1"];

        // Unknown route: memoized null, no refetch.
        var u1 = getRouteForFlight("ZZZ9999");
        check(u1 === null, "unknown route 'ZZZ9999' null while fetching");
        window.setTimeout(function () {
            var u2 = getRouteForFlight("ZZZ9999");
            check(u2 === null, "unknown route 'ZZZ9999' stays null");
            check(AirlineRouteCache["ZZZ9999"] === null, "unknown route memoized as null");
            check(!("ZZZ9999" in AirlineRouteFetching), "unknown route fetch flag cleared");
            print_results();
        }, 3000);
    }, 3000);
}

function print_results() {
    var output = "";
    var failed = 0;
    for (var i = 0; i < results.length; ++i) {
        if (!results[i].pass) {
            ++failed;
        }
        output += (results[i].pass ? "PASS  " : "FAIL  ") + results[i].description + "\n";
    }
    output += "\n" + (results.length - failed) + " passed, " + failed + " failed\n";
    var container = document.getElementById("results");
    container.className = failed === 0 ? "pass" : "fail";
    container.textContent = output;
}

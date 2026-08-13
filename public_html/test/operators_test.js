// -*- mode: javascript; indent-tabs-mode: nil; c-basic-offset: 8 -*-

// Part of dump1090, a Mode S message decoder for RTLSDR devices.
//
// operators_test.js: exercises the operator resolution and tooltip
// logic from operators.js. Open test/operators_test.html in a browser.
//
// Copyright (c) 2026 dump1090 contributors
//
// This file is free software: you may copy, redistribute and/or modify it
// under the terms of the GNU General Public License as published by the
// Free Software Foundation, either version 2 of the License, or (at your
// option) any later version.

"use strict";

// Config values the test needs; normally provided by config.js.
var AirlineLogosEnabled = true;
var AirlineLogoUrlTemplate = "https://example.test/logos/{icao}.png";
var AirlineLogoCacheUrl = "";

var results = [];

function check(condition, description) {
    results.push({ pass: !!condition, description: description });
}

function setup_operators_test() {
    var script = document.createElement("script");
    script.src = "../operators.js";
    script.onload = run_tests;
    document.body.appendChild(script);
}

function run_tests() {
    // Callsign prefix parsing.
    var op = operatorFromCallsign("EDV4978");
    check(op !== null && op.icao === "EDV" && op.name === "Endeavor Air", "EDV4978 -> Endeavor Air");
    check(op !== null && op.name === "Endeavor Air", "EDV operator name is Endeavor Air");

    op = operatorFromCallsign("EDV4978 ");
    check(op !== null && op.icao === "EDV", "padded callsign 'EDV4978 ' -> EDV");

    op = operatorFromCallsign("aca855");
    check(op !== null && op.icao === "ACA" && op.name === "Air Canada", "lowercase 'aca855' -> Air Canada");

    op = operatorFromCallsign("KLM10A");
    check(op !== null && op.icao === "KLM", "'KLM10A' -> KLM");

    op = operatorFromCallsign("N925MP");
    check(op === null, "registration-as-callsign 'N925MP' -> null");

    op = operatorFromCallsign("CFHHD578");
    check(op === null, "unknown prefix 'CFHHD578' -> null");

    op = operatorFromCallsign("12345");
    check(op === null, "numeric callsign -> null");

    op = operatorFromCallsign("");
    check(op === null, "empty callsign -> null");

    op = operatorFromCallsign(null);
    check(op === null, "null callsign -> null");

    // Layered resolution: database operator wins over callsign prefix.
    op = resolveOperator({ flight: "UAL1234", operatorIcao: "DAL", operatorName: "Delta Air Lines" });
    check(op !== null && op.icao === "DAL" && op.name === "Delta Air Lines", "database operator overrides callsign prefix");

    op = resolveOperator({ flight: "UAL1234", operatorIcao: "DAL", operatorName: "" });
    check(op !== null && op.icao === "DAL" && op.name === "DAL", "database operator falls back to ICAO code for name");

    op = resolveOperator({ flight: "UAL1234", operatorIcao: null, operatorName: null });
    check(op !== null && op.icao === "UAL", "callsign prefix used when no database operator");

    op = resolveOperator({ flight: null, operatorIcao: null, operatorName: null });
    check(op === null, "no flight, no database operator -> null");

    // Logo URLs.
    var url = getAirlineLogoUrl("UAL");
    check(url === "https://example.test/logos/UAL.png", "template URL substitutes {icao}");

    AirlineLogoCacheUrl = "http://cache.test:8001/";
    url = getAirlineLogoUrl("UAL");
    check(url === "http://cache.test:8001/logos/UAL.png", "cache URL used when AirlineLogoCacheUrl set (trailing slash stripped)");
    AirlineLogoCacheUrl = "";

    // Tooltip DOM behaviour.
    initializeAirlineLogoTooltip();
    check(AirlineLogoTooltip !== null, "tooltip element created");
    check(AirlineLogoTooltip.className.indexOf("hidden") !== -1, "tooltip starts hidden");

    var cell = document.createElement("td");
    cell.style.position = "absolute";
    cell.style.left = "100px";
    cell.style.top = "100px";
    document.body.appendChild(cell);
    showAirlineLogoTooltip(cell, "UAL", "United Airlines");
    check(AirlineLogoTooltip.className.indexOf("hidden") === -1, "tooltip visible after show");
    var img = AirlineLogoTooltip.querySelector("img");
    check(img !== null && img.src === "https://example.test/logos/UAL.png", "tooltip contains logo image with correct src");
    check(AirlineLogoTooltip.querySelector(".airline-operator-name").textContent === "United Airlines", "tooltip contains operator name");
    check(AirlineLogoTooltip.style.left !== "" && AirlineLogoTooltip.style.top !== "", "tooltip positioned");
    var box = AirlineLogoTooltip.getBoundingClientRect();
    check(box.left >= 0 && box.top >= 0 && box.left + box.width <= window.innerWidth + 1 && box.top + box.height <= window.innerHeight + 1, "tooltip within viewport");

    hideAirlineLogoTooltip();
    check(AirlineLogoTooltip.className.indexOf("hidden") !== -1, "tooltip hidden after hide");

    // Missing logo: image error handler removes the img, name remains.
    showAirlineLogoTooltip(cell, "UAL", "United Airlines");
    img = AirlineLogoTooltip.querySelector("img");
    img.dispatchEvent(new Event("error"));
    check(AirlineLogoTooltip.querySelector("img") === null, "broken logo image removed on error");
    check(AirlineLogoTooltip.querySelector(".airline-operator-name") !== null, "operator name remains when logo fails");
    hideAirlineLogoTooltip();

    document.body.removeChild(cell);

    print_results();
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

// -*- mode: javascript; indent-tabs-mode: nil; c-basic-offset: 8 -*-

// Part of dump1090, a Mode S message decoder for RTLSDR devices.
//
// operators.js: resolve the operator of an aircraft and show the
// operator's logo in a fixed-size tooltip when hovering over the
// aircraft's ident in the aircraft table.
//
// Copyright (c) 2026 dump1090 contributors
//
// This file is free software: you may copy, redistribute and/or modify it
// under the terms of the GNU General Public License as published by the
// Free Software Foundation, either version 2 of the License, or (at your
// option) any later version.
//
// This file is distributed in the hope that it will be useful, but
// WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

"use strict";

// Operator resolution happens in two layers:
//
//   1. Per-aircraft operator data supplied by the aircraft database.
//      The standard dump1090 database does not carry operator data
//      today; when it does, set plane.operatorIcao / plane.operatorName
//      (see planeObject.js) and that data wins.
//
//   2. The callsign prefix, matched against the table of ICAO airline
//      designators below (e.g. "UAL1234" -> United Airlines).
//
// resolveOperator() is called from script.js for every visible table
// row on each refresh; the result is stored on the row element as
// data-operator-icao / data-operator-name attributes.

// ICAO airline designator -> operator display name.
// Add entries for operators you see in your area; unknown prefixes
// resolve to null and no tooltip is shown.
var AirlineOperators = {
    // United States
    "AAL": "American Airlines",
    "AAY": "Allegiant Air",
    "ABX": "ABX Air",
    "AMF": "Ameriflight",
    "ASA": "Alaska Airlines",
    "ASH": "Mesa Airlines",
    "AWI": "Air Wisconsin",
    "CKS": "Kalitta Air",
    "DAL": "Delta Air Lines",
    "EDV": "Endeavor Air",
    "EJA": "NetJets",
    "EJM": "Executive Jet Management",
    "ENY": "Envoy Air",
    "FFT": "Frontier Airlines",
    "FDX": "FedEx Express",
    "GJS": "GoJet Airlines",
    "GTI": "Atlas Air",
    "HAL": "Hawaiian Airlines",
    "JBU": "JetBlue Airways",
    "JIA": "PSA Airlines",
    "LXJ": "Flexjet",
    "MTN": "Mountain Air Cargo",
    "NCR": "National Airlines",
    "NKS": "Spirit Airlines",
    "PAC": "Polar Air Cargo",
    "PDT": "Piedmont Airlines",
    "QXE": "Horizon Air",
    "RPA": "Republic Airways",
    "RCH": "US Air Force (Reach)",
    "SKW": "SkyWest Airlines",
    "SWA": "Southwest Airlines",
    "UAL": "United Airlines",
    "UPS": "UPS Airlines",

    // Canada
    "ACA": "Air Canada",
    "ANT": "Air North",
    "CFC": "Canadian Armed Forces",
    "CJT": "Cargojet",
    "FLE": "Flair Airlines",
    "JZA": "Jazz Aviation",
    "MAL": "Morningstar Air Express",
    "MPE": "Canadian North",
    "POE": "Porter Airlines",
    "PVL": "PAL Airlines",
    "ROU": "Air Canada Rouge",
    "TSC": "Air Transat",
    "TWY": "Tradewind Aviation",
    "WEN": "WestJet Encore",
    "WJA": "WestJet",

    // Europe
    "AFR": "Air France",
    "AUA": "Austrian Airlines",
    "BAW": "British Airways",
    "BEL": "Brussels Airlines",
    "DLH": "Lufthansa",
    "FIN": "Finnair",
    "IBE": "Iberia",
    "ICE": "Icelandair",
    "ITY": "ITA Airways",
    "KLM": "KLM Royal Dutch Airlines",
    "NJE": "NetJets Europe",
    "SAS": "SAS Scandinavian Airlines",
    "SWR": "Swiss International Air Lines",
    "TAP": "TAP Air Portugal",
    "THY": "Turkish Airlines",
    "VIR": "Virgin Atlantic",

    // Middle East / Africa / Asia / Latin America
    "AIC": "Air India",
    "ANA": "All Nippon Airways",
    "AVA": "Avianca",
    "CAL": "China Airlines",
    "CCA": "Air China",
    "CES": "China Eastern Airlines",
    "CMP": "Copa Airlines",
    "CPA": "Cathay Pacific",
    "CSN": "China Southern Airlines",
    "ELY": "El Al",
    "ETD": "Etihad Airways",
    "ETH": "Ethiopian Airlines",
    "EVA": "EVA Air",
    "JAL": "Japan Airlines",
    "KAL": "Korean Air",
    "MSR": "EgyptAir",
    "QTR": "Qatar Airways",
    "RJA": "Royal Jordanian",
    "SIA": "Singapore Airlines",
    "SVA": "Saudia",
    "UAE": "Emirates"
};

// Resolve the operator of an aircraft, or null if unknown.
// Returns { icao: <ICAO airline designator>, name: <display name> }.
function resolveOperator(plane) {
    if (!AirlineLogosEnabled) {
        return null;
    }

    // Layer 1: operator data supplied by the aircraft database.
    if (plane.operatorIcao !== null && plane.operatorIcao !== undefined && plane.operatorIcao !== "") {
        return {
            icao: plane.operatorIcao,
            name: (plane.operatorName !== null && plane.operatorName !== undefined && plane.operatorName !== "") ? plane.operatorName : plane.operatorIcao
        };
    }

    // Layer 2: callsign prefix.
    return operatorFromCallsign(plane.flight);
}

// Match the leading alphabetic part of a callsign against the
// designator table. Returns the same shape as resolveOperator().
function operatorFromCallsign(flight) {
    if (flight === null || flight === undefined) {
        return null;
    }

    var match = String(flight).trim().match(/^[A-Za-z]{2,3}/);
    if (match === null) {
        return null;
    }

    var icao = match[0].toUpperCase();
    var name = AirlineOperators[icao];
    if (name === undefined) {
        return null;
    }

    return { icao: icao, name: name };
}

// Logo URL for an operator, or "" when no logo is available.
// AirlineLogoUrlTemplate and AirlineLogoCacheUrl are set in config.js.
function getAirlineLogoUrl(icao) {
    if (typeof AirlineLogoCacheUrl === "string" && AirlineLogoCacheUrl.length > 0) {
        return AirlineLogoCacheUrl.replace(/\/+$/, "") + "/logos/" + icao + ".png";
    }
    if (typeof AirlineLogoUrlTemplate === "string" && AirlineLogoUrlTemplate.length > 0) {
        return AirlineLogoUrlTemplate.replace("{icao}", icao);
    }
    return "";
}

// ---------------------------------------------------------------------
// Hover tooltip

var AirlineLogoTooltip = null;

// Attach the hover tooltip to the ident cells of the aircraft table.
// Called from script.js initialize().
function initializeAirlineLogoTooltip() {
    if (!AirlineLogosEnabled) {
        return;
    }

    AirlineLogoTooltip = document.createElement("div");
    AirlineLogoTooltip.className = "airline-logo-tooltip hidden";
    document.body.appendChild(AirlineLogoTooltip);

    var table = document.getElementById("planes_table");
    if (table === null) {
        return;
    }

    table.addEventListener("mouseover", function (event) {
        var node = event.target;
        while (node !== null && node !== table && node.tagName !== "TD") {
            node = node.parentNode;
        }
        if (node === null || node === table || node.cellIndex !== 2) {
            hideAirlineLogoTooltip();
            return;
        }

        var row = node.parentNode;
        var icao = row.getAttribute("data-operator-icao");
        if (icao === null) {
            hideAirlineLogoTooltip();
            return;
        }

        var name = row.getAttribute("data-operator-name");
        if (name === null) {
            name = icao;
        }
        showAirlineLogoTooltip(node, icao, name);
    });

    table.addEventListener("mouseout", function (event) {
        var node = event.relatedTarget;
        while (node !== null && node !== table) {
            node = node.parentNode;
        }
        if (node === null) {
            hideAirlineLogoTooltip();
        }
    });

    window.addEventListener("scroll", hideAirlineLogoTooltip, true);
    window.addEventListener("resize", hideAirlineLogoTooltip);
}

function showAirlineLogoTooltip(cell, icao, name) {
    if (AirlineLogoTooltip._visible && AirlineLogoTooltip._icao === icao && AirlineLogoTooltip._cell === cell) {
        return;
    }

    AirlineLogoTooltip.innerHTML = "";
    AirlineLogoTooltip._icao = icao;
    AirlineLogoTooltip._cell = cell;

    var url = getAirlineLogoUrl(icao);
    if (url.length > 0) {
        var img = document.createElement("img");
        img.alt = name;
        img.src = url;
        img.addEventListener("error", function () {
            img.remove();
        });
        AirlineLogoTooltip.appendChild(img);
    }

    var label = document.createElement("div");
    label.className = "airline-operator-name";
    label.textContent = name;
    AirlineLogoTooltip.appendChild(label);

    AirlineLogoTooltip.classList.remove("hidden");
    positionAirlineLogoTooltip(cell);
    AirlineLogoTooltip._visible = true;
}

function positionAirlineLogoTooltip(cell) {
    var rect = cell.getBoundingClientRect();
    var width = AirlineLogoTooltip.offsetWidth;
    var height = AirlineLogoTooltip.offsetHeight;

    var left = rect.left;
    if (left + width > window.innerWidth - 8) {
        left = window.innerWidth - width - 8;
    }
    if (left < 8) {
        left = 8;
    }

    var top = rect.bottom + 6;
    if (top + height > window.innerHeight - 8) {
        top = rect.top - height - 6;
    }
    if (top < 8) {
        top = 8;
    }

    AirlineLogoTooltip.style.left = left + "px";
    AirlineLogoTooltip.style.top = top + "px";
}

function hideAirlineLogoTooltip() {
    if (AirlineLogoTooltip === null) {
        return;
    }
    AirlineLogoTooltip.classList.add("hidden");
    AirlineLogoTooltip._visible = false;
    AirlineLogoTooltip._icao = null;
    AirlineLogoTooltip._cell = null;
}

# SkyAware Features

## Customize display via URL query strings

Syntax: <ip_address>/skyaware/?parameter=value

Examples:

    http://<ip_address>/skyaware/?sidebar=hide

    http://<ip_address>/skyaware/?altitudeChart=hide

    http://<ip_address>/skyaware/?rangeRings=hide

    http://<ip_address>/skyaware/?ringCount=3&ringBaseDistance=100&ringInterval=50

| Parameter | Possible Values |
| :---------: | :---------: |
| banner  | show/hide |
| altitudeChart | show/hide |
| aircraftTrails | show/hide |
| map | show/hide | 
| sidebar | show/hide | 
| zoomOut | 0 - 5 | 
| zoomIn | 0 - 5 | 
| moveNorth | 0 - 5 | 
| moveSouth | 0 - 5 | 
| moveWest | 0 - 5 | 
| moveEast | 0 - 5 | 
| displayUnits | nautical/imperial/metric |
| rangeRings | show/hide | 
| ringCount | integer |
| ringBaseDistance | integer |
| ringInterval | integer |



## New World/US/Europe Basemaps and Overlays

Click the OpenLayers icon on the bottom right of the map to select baselayers and overlays

## Ability to show/hide columns in the aircraft table

The "Select Columns" button on the aircraft table allows you to choose which columns to show for your preferred display

## Airline logos in the aircraft table

Hovering over an aircraft's ident (callsign) in the aircraft table shows
the operator's logo and name in a fixed-size tooltip.

The operator is resolved in two layers:

 1. per-aircraft operator data supplied by the aircraft database (the
    standard dump1090 database does not carry operator data yet; when it
    does, set `operatorIcao` / `operatorName` on the PlaneObject and it
    wins), then
 2. the callsign prefix, matched against the ICAO designator table in
    `operators.js` (`AirlineOperators`), generated from the Wikipedia
    "List of airline codes" by `tools/update-airline-operators.py`.
    Curated display-name fixes and local additions go in
    `AirlineOperatorOverrides`; regenerate the table with:

```sh
tools/update-airline-operators.py
```

Callsigns that are aircraft registrations (e.g. Canadian `CFAKD` or US
`N554JM`, broadcast without the hyphen) are excluded via
`AirlineRegistrationPatterns` so they never resolve to an operator.

### Flight routes (departure / arrival)

The departure and arrival ICAO airport codes of a flight are resolved
from its callsign and shown in the aircraft table (Departure/Arrival
columns, enabled by default and toggleable in the column settings) and
in the map info cards.

Routes are requested from the route cache server at
`<AirlineLogoCacheUrl>/route/<callsign>` -- the same
`tools/logo-cache-proxy.py` server that caches logos, proxying the
public adsbdb route API (`https://api.adsbdb.com/v0/callsign/<callsign>`)
with 24h disk caching. Without a cache server the requests fail quietly
and no routes are shown. Disable entirely with `AirlineRoutesEnabled`
in config.js.

Logos are fetched from the URL in `AirlineLogoUrlTemplate` (config.js),
with `{icao}` replaced by the operator's ICAO designator.

### Local logo cache

Browsers cannot reliably cache the external logo images themselves on
plain-HTTP receiver sites, so a small cache server is provided:

```sh
install -m 0755 tools/logo-cache-proxy.py /usr/local/bin/dump1090-airline-logo-cache.py
install -m 0644 tools/dump1090-airline-logo-cache.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dump1090-airline-logo-cache
```

Then set in config.js:

```js
AirlineLogoCacheUrl = "http://<receiver-ip>:8001";
```

Each logo is fetched from FlightAware once, stored in
`/var/cache/dump1090-airline-logos`, and served from there afterwards.
Unknown operators are remembered briefly (7 days by default) so they are
not refetched on every hover. Without the cache server, leave
`AirlineLogoCacheUrl` empty and logos are fetched directly from
`AirlineLogoUrlTemplate`.

Run `tools/logo-cache-proxy.py --help` for options (listen address/port,
cache directory, logo URL template, cache expiry).

### Dark theme

The webmap supports light, dark and system themes. "system" follows the
operating system's dark/light preference and updates live when the OS
theme changes. The map base layer switches to the ESRI dark gray canvas
with the dark theme. The choice is made in the settings panel (Theme
selector) and remembered in local storage; the default is set by
`Theme` in config.js ("system", "dark" or "light").

Route direction: callsigns are reused for both directions of a route
(shuttle flights), so the UI adjusts the stored route using the
aircraft's ground track and the airports' coordinates (included in the
route payload) -- when the aircraft is heading the reverse way, the
departure and arrival are swapped. Routes without coordinates (older
cache entries) are shown as stored.

The route source is the FlightAware live flight page for the callsign
(the current schedule, so route changes are picked up within the cache
TTL), with the adsbdb route API as an automatic fallback when the page
cannot be parsed. Both cache servers (logo-cache-proxy.py and
data-proxy.py) implement this; the source URL is configurable via
--route-template / --route-fallback-template.

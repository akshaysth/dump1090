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
 2. the callsign prefix, matched against the table of ICAO airline
    designators in `operators.js` (`AirlineOperators`). Add entries for
    operators you see in your area.

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

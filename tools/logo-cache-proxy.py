#!/usr/bin/env python3
# -*- mode: python; indent-tabs-mode: nil; py-indent-offset: 4 -*-

# Part of dump1090, a Mode S message decoder for RTLSDR devices.
#
# logo-cache-proxy.py: local cache server for airline operator logos.
#
# The dump1090 webmap can show an operator's logo when hovering over an
# aircraft's ident. The logos are fetched from an external URL template
# (see AirlineLogoUrlTemplate in public_html/config.js). Browsers cannot
# reliably cache those images themselves on plain-HTTP receiver sites,
# so this small server fetches each logo once and serves it from a local
# on-disk cache afterwards.
#
# Copyright (c) 2026 dump1090 contributors
#
# This file is free software: you may copy, redistribute and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 2 of the License, or (at your
# option) any later version.
#
# This file is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Local cache server for airline operator logos and flight routes.

Endpoints:
  GET /logos/<ICAO>.png   the logo for operator ICAO, fetched from the
                          URL template on first request and cached on
                          disk afterwards. 404 responses are also cached
                          (briefly) so unknown operators are not refetched
                          on every hover.
  GET /route/<callsign>   the departure/arrival airports of a flight,
                          fetched from the FlightAware live flight page
                          (current schedule per callsign) on first
                          request, with the adsbdb route API as fallback,
                          and cached on disk (24h by default). Unknown
                          routes are cached briefly so they are not
                          refetched on every refresh.
  GET /health             returns 200 when the server is up.

Install (systemd):
  install -m 0755 tools/logo-cache-proxy.py /usr/local/bin/dump1090-airline-logo-cache.py
  install -m 0644 tools/dump1090-airline-logo-cache.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now dump1090-airline-logo-cache

Then set AirlineLogoCacheUrl in public_html/config.js to the server's
base URL, e.g. "http://172.16.1.135:8001". Routes are served from the
same base URL and are enabled by AirlineRoutesEnabled.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

DEFAULT_TEMPLATE = "https://www.flightaware.com/images/airline_logos/180px/{icao}.png"
DEFAULT_CACHE_DIR = "/var/cache/dump1090-airline-logos"
CLIENT_CACHE_SECONDS = 86400      # how long browsers may reuse a response
DEFAULT_404_TTL_SECONDS = 7 * 86400  # retry unknown operators after this
ROUTE_TEMPLATE = "https://www.flightaware.com/live/flight/{callsign}"
ROUTE_FALLBACK_TEMPLATE = "https://api.adsbdb.com/v0/callsign/{callsign}"
DEFAULT_ROUTE_TTL_SECONDS = 24 * 3600  # revalidate routes after this
ROUTE_CLIENT_CACHE_SECONDS = 3600  # how long browsers may reuse a route
# Some logo hosts reject library user agents; use a browser-like one.
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


class LogoCacheServer(ThreadingHTTPServer):
    def __init__(self, address, handler, cache_dir, logo_template, max_age_seconds,
                 not_found_ttl_seconds, route_template, route_fallback_template, route_ttl_seconds):
        super().__init__(address, handler)
        self.cache_dir = cache_dir
        self.logo_template = logo_template
        self.max_age_seconds = max_age_seconds
        self.not_found_ttl_seconds = not_found_ttl_seconds
        self.route_template = route_template
        self.route_fallback_template = route_fallback_template
        self.route_ttl_seconds = route_ttl_seconds


class LogoCacheHandler(BaseHTTPRequestHandler):
    server_version = "dump1090-logo-cache/1.0"

    @property
    def cache_server(self) -> LogoCacheServer:
        return cast(LogoCacheServer, self.server)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        match = re.fullmatch(r"/logos/([A-Za-z0-9]{2,4})\.png", self.path)
        if match is None:
            match = re.fullmatch(r"/route/([A-Za-z0-9]{3,10})", self.path)
            if match is not None:
                self.serve_route(match.group(1).upper())
                return
            self.send_response(404)
            self.end_headers()
            return

        icao = match.group(1).upper()
        self.serve_logo(icao)

    def serve_logo(self, icao):
        os.makedirs(self.cache_server.cache_dir, exist_ok=True)
        cache_file = os.path.join(self.cache_server.cache_dir, icao + ".png")
        miss_file = os.path.join(self.cache_server.cache_dir, icao + ".404")

        # Serve from cache when present and not expired.
        if os.path.exists(cache_file) and self._is_fresh(cache_file, self.cache_server.max_age_seconds):
            self._send_file(cache_file, "HIT")
            return

        # Short-circuit known-missing logos (404 marker still fresh).
        if os.path.exists(miss_file) and self._is_fresh(miss_file, self.cache_server.not_found_ttl_seconds):
            self.send_response(404)
            self.send_header("X-Cache", "HIT (404)")
            self.send_header("Cache-Control", "public, max-age=%d" % CLIENT_CACHE_SECONDS)
            self.end_headers()
            return

        url = self.cache_server.logo_template.replace("{icao}", icao)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status != 200:
                    raise urllib.error.HTTPError(url, response.status, "bad status", response.headers, None)
                data = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                self._mark_missing(miss_file)
                self.send_response(404)
                self.send_header("X-Cache", "MISS (404)")
                self.send_header("Cache-Control", "public, max-age=%d" % CLIENT_CACHE_SECONDS)
                self.end_headers()
                return
            self._server_error("upstream error: %s" % error.code)
            return
        except Exception as error:  # network errors, timeouts
            self._server_error(str(error))
            return

        if len(data) == 0:
            self._server_error("empty upstream response")
            return

        # Replace any stale 404 marker.
        if os.path.exists(miss_file):
            try:
                os.remove(miss_file)
            except OSError:
                pass

        self._write_atomic(cache_file, data)
        self._send_bytes(data, "MISS")

    def serve_route(self, callsign):
        os.makedirs(self.cache_server.cache_dir, exist_ok=True)
        cache_file = os.path.join(self.cache_server.cache_dir, callsign + ".route.json")
        miss_file = os.path.join(self.cache_server.cache_dir, callsign + ".route.404")

        # Serve from cache when present and not expired.
        if os.path.exists(cache_file) and self._is_fresh(cache_file, self.cache_server.route_ttl_seconds):
            self._send_route_file(cache_file, "HIT")
            return

        # Short-circuit known-unknown routes (404 marker still fresh).
        if os.path.exists(miss_file) and self._is_fresh(miss_file, self.cache_server.route_ttl_seconds):
            self._send_route_404("HIT (404)")
            return

        url = self.cache_server.route_template.replace("{callsign}", callsign)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                self._mark_missing(miss_file)
                self._send_route_404("MISS (404)")
                return
            self._server_error("route upstream error: %s" % error.code)
            return
        except Exception as error:  # network errors, timeouts
            self._server_error("route upstream error: %s" % error)
            return

        dep, arr, dep_lat, dep_lon, arr_lat, arr_lon = self._parse_flightaware_route(html)
        if not dep or not arr:
            # Fall back to the adsbdb route API
            fallback_url = self.cache_server.route_fallback_template.replace("{callsign}", callsign)
            request = urllib.request.Request(fallback_url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    data = json.loads(response.read().decode("utf-8", "replace"))
                flightroute = (data.get("response") or {}).get("flightroute") or {}
                origin = flightroute.get("origin") or {}
                destination = flightroute.get("destination") or {}
                dep = origin.get("icao_code")
                arr = destination.get("icao_code")
                dep_lat = origin.get("latitude")
                dep_lon = origin.get("longitude")
                arr_lat = destination.get("latitude")
                arr_lon = destination.get("longitude")
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    self._mark_missing(miss_file)
                    self._send_route_404("MISS (404)")
                    return
                self._server_error("route fallback error: %s" % error.code)
                return
            except Exception as error:
                self._server_error("route fallback error: %s" % error)
                return

        if not dep or not arr:
            self._mark_missing(miss_file)
            self._send_route_404("MISS (incomplete)")
            return

        # Include the airport coordinates so the client can determine
        # the flight direction from the aircraft's track (callsigns
        # like shuttle flights are reused for both directions).
        payload = json.dumps({
            "dep": dep,
            "arr": arr,
            "depLat": dep_lat,
            "depLon": dep_lon,
            "arrLat": arr_lat,
            "arrLon": arr_lon,
        }).encode("utf-8")
        if os.path.exists(miss_file):
            try:
                os.remove(miss_file)
            except OSError:
                pass
        self._write_atomic(cache_file, payload)
        self._send_route_bytes(payload, "MISS")

    def _send_route_file(self, path, cache_state):
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            self._server_error("route cache read error")
            return
        self._send_route_bytes(data, cache_state)

    def _send_route_bytes(self, data, cache_state):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=%d" % ROUTE_CLIENT_CACHE_SECONDS)
        self.send_header("X-Cache", cache_state)
        self.end_headers()
        self.wfile.write(data)

    def _send_route_404(self, cache_state):
        self.send_response(404)
        self.send_header("Cache-Control", "public, max-age=%d" % ROUTE_CLIENT_CACHE_SECONDS)
        self.send_header("X-Cache", cache_state)
        self.end_headers()

    def _parse_flightaware_route(self, html):
        """Extract origin/destination ICAO codes and coordinates from a
        FlightAware flight page. Returns
        (dep, arr, dep_lat, dep_lon, arr_lat, arr_lon)."""
        dep = None
        arr = None
        match = re.search(r"setTargeting\('origin', '([A-Z]{4})'\)", html)
        if match:
            dep = match.group(1)
        match = re.search(r"setTargeting\('destination', '([A-Z]{4})'\)", html)
        if match:
            arr = match.group(1)

        dep_lat = dep_lon = arr_lat = arr_lon = None
        match = re.search(r'"origin":\{[^}]*"coord":\[([-\d.]+),([-\d.]+)\][^}]*"icao":"([A-Z]{4})"', html)
        if match:
            if dep is None:
                dep = match.group(3)
            dep_lat = float(match.group(2))
            dep_lon = float(match.group(1))
        match = re.search(r'"destination":\{[^}]*"coord":\[([-\d.]+),([-\d.]+)\][^}]*"icao":"([A-Z]{4})"', html)
        if match:
            if arr is None:
                arr = match.group(3)
            arr_lat = float(match.group(2))
            arr_lon = float(match.group(1))
        return dep, arr, dep_lat, dep_lon, arr_lat, arr_lon

    def _is_fresh(self, path, ttl_seconds):
        if ttl_seconds <= 0:
            return True
        try:
            return (time.time() - os.path.getmtime(path)) < ttl_seconds
        except OSError:
            return False

    def _mark_missing(self, miss_file):
        try:
            with open(miss_file, "wb"):
                pass
        except OSError:
            pass

    def _write_atomic(self, path, data):
        tmp = path + ".tmp"
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except OSError:
            pass

    def _send_file(self, path, cache_state):
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            self._server_error("cache read error")
            return
        self._send_bytes(data, cache_state)

    def _send_bytes(self, data, cache_state):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=%d" % CLIENT_CACHE_SECONDS)
        self.send_header("X-Cache", cache_state)
        self.end_headers()
        self.wfile.write(data)

    def _server_error(self, detail):
        body = b"logo cache upstream error"
        self.send_response(502)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.log_message("upstream error for %s: %s", self.path, detail)

    def log_message(self, format, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), format % args))


def main():
    parser = argparse.ArgumentParser(description="Cache server for airline operator logos.")
    parser.add_argument("--host", default="0.0.0.0", help="listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="listen port (default: 8001)")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR,
                        help="cache directory (default: %s)" % DEFAULT_CACHE_DIR)
    parser.add_argument("--logo-template", default=DEFAULT_TEMPLATE,
                        help="URL template for logos; {icao} is replaced (default: FlightAware)")
    parser.add_argument("--max-age", type=int, default=0,
                        help="revalidate cached logos after this many seconds (0 = never, default)")
    parser.add_argument("--not-found-ttl", type=int, default=DEFAULT_404_TTL_SECONDS,
                        help="remember unknown operators for this many seconds (default: %d)" % DEFAULT_404_TTL_SECONDS)
    parser.add_argument("--route-template", default=ROUTE_TEMPLATE,
                        help="URL template for routes; {callsign} is replaced (default: FlightAware flight page)")
    parser.add_argument("--route-fallback-template", default=ROUTE_FALLBACK_TEMPLATE,
                        help="URL template used when the primary route source fails (default: adsbdb)")
    parser.add_argument("--route-ttl", type=int, default=DEFAULT_ROUTE_TTL_SECONDS,
                        help="revalidate cached routes after this many seconds (default: %d)" % DEFAULT_ROUTE_TTL_SECONDS)
    args = parser.parse_args()

    server = LogoCacheServer((args.host, args.port), LogoCacheHandler,
                            args.cache_dir, args.logo_template, args.max_age, args.not_found_ttl,
                            args.route_template, args.route_fallback_template, args.route_ttl)

    os.makedirs(args.cache_dir, exist_ok=True)
    print("logo cache server on http://%s:%d (cache: %s)" % (args.host, args.port, args.cache_dir))
    print("template: %s" % args.logo_template)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

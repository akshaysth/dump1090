#!/usr/bin/env python3
# -*- mode: python; indent-tabs-mode: nil; py-indent-offset: 4 -*-

# Part of dump1090, a Mode S message decoder for RTLSDR devices.
#
# data-proxy.py: serve the webmap UI from this machine while pulling the
# aircraft data from a remote dump1090 server.
#
# The webmap fetches its data (data/aircraft.json, data/receiver.json,
# db/*.json, ...) from the same origin it is served from, and dump1090's
# web server does not send CORS headers, so a browser cannot read data
# from another host directly. This small server solves that: files from
# the local public_html directory are served as-is (so you can run the
# development branch or a customized UI), and any request that is not a
# local file is proxied to the remote dump1090 server. Operator logos
# (/logos/) and flight routes (/route/) are served with local caching,
# matching tools/logo-cache-proxy.py.
#
# Usage:
#   tools/data-proxy.py --remote http://172.16.1.135:8000
#
# then open http://127.0.0.1:8080/ in a browser. To let other machines
# reach it, add --host 0.0.0.0.
#
# Copyright (c) 2026 dump1090 contributors
#
# This file is free software: you may copy, redistribute and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 2 of the License, or (at your
# option) any later version.

import argparse
import http.server
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import cast

DEFAULT_SERVE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public_html"))
LOGO_TEMPLATE = "https://www.flightaware.com/images/airline_logos/180px/{icao}.png"
ROUTE_TEMPLATE = "https://www.flightaware.com/live/flight/{callsign}"
ROUTE_FALLBACK_TEMPLATE = "https://api.adsbdb.com/v0/callsign/{callsign}"
DEFAULT_ROUTE_TTL_SECONDS = 24 * 3600  # revalidate cached routes after this
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

TYPES = {
    ".html": "text/html", ".js": "application/javascript", ".css": "text/css",
    ".json": "application/json", ".png": "image/png", ".gif": "image/gif",
    ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".txt": "text/plain", ".gz": "application/gzip", ".woff2": "font/woff2",
}


class DataProxyHandler(http.server.BaseHTTPRequestHandler):
    @property
    def proxy_server(self) -> "DataProxyServer":
        return cast(DataProxyServer, self.server)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/logos/"):
            self.serve_logo(path)
            return
        if path.startswith("/route/"):
            self.serve_route(path)
            return
        self.serve_static_or_proxy(path)

    def serve_static_or_proxy(self, path):
        if path == "/":
            path = "/index.html"
        local = os.path.normpath(os.path.join(self.proxy_server.serve_dir, path.lstrip("/")))
        if not local.startswith(self.proxy_server.serve_dir):
            self.send_error(403)
            return
        if os.path.isfile(local):
            data = open(local, "rb").read()
            self.send_bytes(200, data, TYPES.get(os.path.splitext(local)[1], "application/octet-stream"))
            return
        try:
            req = urllib.request.Request(self.proxy_server.remote + path, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
                self.send_bytes(response.status, data,
                                response.headers.get("Content-Type", "application/octet-stream"))
        except urllib.error.HTTPError as error:
            self.send_error(error.code)
        except Exception as error:
            sys.stderr.write("proxy error %s: %s\n" % (path, error))
            self.send_error(502)

    def serve_logo(self, path):
        match = re.fullmatch(r"/logos/([A-Za-z0-9]{2,4})\.png", path)
        if match is None:
            self.send_error(404)
            return
        icao = match.group(1).upper()
        os.makedirs(self.proxy_server.logo_cache, exist_ok=True)
        cache = os.path.join(self.proxy_server.logo_cache, icao + ".png")
        miss = os.path.join(self.proxy_server.logo_cache, icao + ".404")
        if os.path.exists(cache):
            self.send_bytes(200, open(cache, "rb").read(), "image/png")
            return
        if os.path.exists(miss):
            self.send_error(404)
            return
        url = LOGO_TEMPLATE.replace("{icao}", icao)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                open(miss, "wb").close()
                self.send_error(404)
                return
            self.send_error(502)
            return
        tmp = cache + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, cache)
        self.send_bytes(200, data, "image/png")

    def serve_route(self, path):
        match = re.fullmatch(r"/route/([A-Za-z0-9]{3,10})", path)
        if match is None:
            self.send_error(404)
            return
        callsign = match.group(1).upper()
        os.makedirs(self.proxy_server.route_cache, exist_ok=True)
        cache = os.path.join(self.proxy_server.route_cache, callsign + ".json")
        miss = os.path.join(self.proxy_server.route_cache, callsign + ".404")
        ttl = self.proxy_server.route_ttl_seconds
        now = time.time()
        if os.path.exists(cache) and (ttl <= 0 or now - os.path.getmtime(cache) < ttl):
            self.send_bytes(200, open(cache, "rb").read(), "application/json")
            return
        if os.path.exists(miss) and (ttl <= 0 or now - os.path.getmtime(miss) < ttl):
            self.send_error(404)
            return
        url = ROUTE_TEMPLATE.replace("{callsign}", callsign)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as response:
                html = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                open(miss, "wb").close()
                self.send_error(404)
                return
            sys.stderr.write("route fetch error %s: %s\n" % (callsign, error.code))
            self.send_error(502)
            return
        except Exception as error:
            sys.stderr.write("route fetch error %s: %s\n" % (callsign, error))
            self.send_error(502)
            return
        dep, arr, dep_lat, dep_lon, arr_lat, arr_lon = self._parse_flightaware_route(html)
        if not dep or not arr:
            # Fall back to the adsbdb route API
            fallback_url = ROUTE_FALLBACK_TEMPLATE.replace("{callsign}", callsign)
            try:
                req = urllib.request.Request(fallback_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=15) as response:
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
                    open(miss, "wb").close()
                    self.send_error(404)
                    return
                sys.stderr.write("route fallback error %s: %s\n" % (callsign, error.code))
                self.send_error(502)
                return
            except Exception as error:
                sys.stderr.write("route fallback error %s: %s\n" % (callsign, error))
                self.send_error(502)
                return
        if not dep or not arr:
            open(miss, "wb").close()
            self.send_error(404)
            return
        payload = json.dumps({
            "dep": dep,
            "arr": arr,
            "depLat": dep_lat,
            "depLon": dep_lon,
            "arrLat": arr_lat,
            "arrLon": arr_lon,
        }).encode("utf-8")
        tmp = cache + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(payload)
        os.replace(tmp, cache)
        self.send_bytes(200, payload, "application/json")

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

    def send_bytes(self, status, data, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


class DataProxyServer(http.server.ThreadingHTTPServer):
    def __init__(self, address, handler, serve_dir, remote, logo_cache, route_cache, route_ttl_seconds):
        super().__init__(address, handler)
        self.serve_dir = serve_dir
        self.remote = remote
        self.logo_cache = logo_cache
        self.route_cache = route_cache
        self.route_ttl_seconds = route_ttl_seconds


def main():
    parser = argparse.ArgumentParser(description="Serve the webmap UI with data from a remote dump1090 server.")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="listen port (default: 8080)")
    parser.add_argument("--remote", required=True,
                        help="base URL of the remote dump1090 server, e.g. http://172.16.1.135:8000")
    parser.add_argument("--serve-dir", default=DEFAULT_SERVE_DIR,
                        help="local webmap directory served as-is (default: %s)" % DEFAULT_SERVE_DIR)
    parser.add_argument("--logo-cache", default="/tmp/dump1090-data-proxy-logos",
                        help="logo cache directory (default: /tmp/dump1090-data-proxy-logos)")
    parser.add_argument("--route-cache", default="/tmp/dump1090-data-proxy-routes",
                        help="route cache directory (default: /tmp/dump1090-data-proxy-routes)")
    parser.add_argument("--route-ttl", type=int, default=DEFAULT_ROUTE_TTL_SECONDS,
                        help="revalidate cached routes after this many seconds (default: %d)" % DEFAULT_ROUTE_TTL_SECONDS)
    args = parser.parse_args()

    server = DataProxyServer((args.host, args.port), DataProxyHandler,
                             os.path.abspath(args.serve_dir), args.remote.rstrip("/"),
                             args.logo_cache, args.route_cache, args.route_ttl)
    print("webmap UI on http://%s:%d (files: %s)" % (args.host, args.port, server.serve_dir))
    print("data proxied from %s" % server.remote)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

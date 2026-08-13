#!/usr/bin/env python3
# -*- mode: python; indent-tabs-mode: nil; py-indent-offset: 4 -*-

# Part of dump1090, a Mode S message decoder for RTLSDR devices.
#
# update-airline-operators.py: regenerate the ICAO designator -> operator
# name table in public_html/operators.js.
#
# The table is generated from the Wikipedia "List of airline codes"
# (https://en.wikipedia.org/wiki/List_of_airline_codes), which lists
# IATA/ICAO designators, call signs, countries and comments for airline
# operators. Designators are factual data; the page is used as the data
# source only.
#
# Only rows with a valid three-character ICAO designator (three letters,
# or two letters and one digit) are kept. When a designator has multiple
# rows (historical reallocations), the row that is not marked defunct is
# preferred, then the row with an IATA code.
#
# Usage:
#   tools/update-airline-operators.py                # fetch + regenerate
#   tools/update-airline-operators.py --input data.json  # use pre-fetched,
#                                              # pre-parsed rows (same JSON
#                                              # shape as --output)
#   tools/update-airline-operators.py --output rows.json  # save parsed rows
#
# The generated block in operators.js sits between the
# "// BEGIN GENERATED" and "// END GENERATED" markers; everything else in
# the file, including AirlineOperatorOverrides, is preserved.
#
# Copyright (c) 2026 dump1090 contributors
#
# This file is free software: you may copy, redistribute and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 2 of the License, or (at your
# option) any later version.

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse

OPERATORS_JS = "public_html/operators.js"
BEGIN_MARKER = "// BEGIN GENERATED"
END_MARKER = "// END GENERATED"

API_BASE = "https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json&formatversion=2&page={}"
USER_AGENT = "dump1090 update-airline-operators (data refresh; contact: dump1090 maintainers)"
PAGES = ["List of airline codes (0\u20139)"] + [
    "List of airline codes ({})".format(chr(c)) for c in range(ord("A"), ord("Z") + 1)
]

STRONG_DEFUNCT = re.compile(
    r"defunct|ceased operations|ceased to operate|liquidat|bankrupt|dissolved|insolvent", re.I)
SOFT_DEFUNCT = re.compile(
    r"merged into|merged with|taken over|acquired by|absorbed|no longer allocated", re.I)


def clean_field(text):
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)   # wikilinks
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)     # refs
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)                       # templates
    text = re.sub(r"<[^>]+>", "", text)                              # tags
    return text.replace("'''", "").strip()


def fetch_wikitext():
    wikitext = {}
    for page in PAGES:
        url = API_BASE.format(urllib.parse.quote(page))
        for attempt in range(6):
            out = subprocess.run(
                ["curl", "-sL", "--max-time", "60", "-A", USER_AGENT, url],
                capture_output=True, text=True).stdout
            try:
                wikitext[page] = json.loads(out)["parse"]["wikitext"]
                break
            except Exception:
                time.sleep(4 + attempt * 3)
        else:
            print("warning: failed to fetch %s" % page, file=sys.stderr)
        time.sleep(2.5)
    return wikitext


def parse_wikitext(wikitext):
    rows = []
    for wt in wikitext.values():
        for block in re.split(r"^\|-\s*$", wt, flags=re.M):
            fields = []
            for line in block.splitlines():
                line = line.rstrip()
                if not line.startswith("|"):
                    continue
                if line.startswith(("||", "|+", "|}", "|class")):
                    continue
                fields.append(line[1:].strip())
            if len(fields) < 3:
                continue
            fields = [clean_field(f) for f in fields]
            iata = fields[0].upper()
            icao = fields[1].upper()
            name = fields[2]
            callsign = fields[3] if len(fields) > 3 else ""
            country = fields[4] if len(fields) > 4 else ""
            comments = " ".join(fields[5:]) if len(fields) > 5 else ""
            if not re.fullmatch(r"[A-Za-z]{2}[A-Za-z0-9]", icao):
                continue
            if not name or name in ("\u2014", "-"):
                continue
            rows.append({
                "icao": icao, "iata": iata, "name": name, "callsign": callsign,
                "country": country, "comments": comments,
                "defunct": bool(STRONG_DEFUNCT.search(comments)) or bool(SOFT_DEFUNCT.search(comments)),
            })
    return rows


def dedup(rows):
    best = {}
    for row in rows:
        code = row["icao"]
        if code not in best:
            best[code] = row
            continue
        cur = best[code]

        def better(a, b):
            if a["defunct"] != b["defunct"]:
                return not b["defunct"]
            if bool(a["iata"]) != bool(b["iata"]):
                return bool(b["iata"])
            return False

        if better(cur, row):
            best[code] = row
    return sorted(best.values(), key=lambda r: r["icao"])


def generate_js_block(entries):
    lines = [BEGIN_MARKER]
    lines.append("// Generated by tools/update-airline-operators.py from")
    lines.append("// the Wikipedia \"List of airline codes\". Do not edit by hand.")
    lines.append("var AirlineOperators = {")
    for entry in entries:
        name = entry["name"].replace("\\", "\\\\").replace('"', '\\"')
        lines.append('    "%s": "%s",' % (entry["icao"], name))
    lines.append("};")
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def regenerate(operators_js_path, entries):
    with open(operators_js_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    block = generate_js_block(entries)
    pattern = re.compile(
        r"^// BEGIN GENERATED.*?^// END GENERATED[^\n]*\n",
        flags=re.M | re.S)
    if not pattern.search(source):
        print("error: markers not found in %s" % operators_js_path, file=sys.stderr)
        sys.exit(1)
    updated = pattern.sub(lambda _: block, source, count=1)
    with open(operators_js_path, "w", encoding="utf-8") as handle:
        handle.write(updated)
    print("regenerated %s: %d operators" % (operators_js_path, len(entries)))


def main():
    parser = argparse.ArgumentParser(description="Regenerate the operator table in operators.js")
    parser.add_argument("--input", help="use pre-parsed rows JSON instead of fetching Wikipedia")
    parser.add_argument("--output", help="save parsed rows JSON")
    parser.add_argument("--operators-js", default=OPERATORS_JS,
                        help="path to operators.js (default: %s)" % OPERATORS_JS)
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as handle:
            rows = json.load(handle)
    else:
        print("fetching Wikipedia airline code lists...", file=sys.stderr)
        rows = parse_wikitext(fetch_wikitext())

    entries = dedup(rows)
    print("parsed %d rows, %d unique designators" % (len(rows), len(entries)))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=1)
        print("saved rows to %s" % args.output)

    regenerate(args.operators_js, entries)


if __name__ == "__main__":
    main()

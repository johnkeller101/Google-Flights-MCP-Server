#!/usr/bin/env python3
"""
Test script to diagnose Google Flights MCP issues.

Runs the same code paths as server.py but prints detailed diagnostics
about what fast_flights returns vs what the MCP would format.

Usage (inside the claude-coach container):
  /opt/google-flights-mcp/.venv/bin/python3 /opt/google-flights-mcp/test_mcp.py

Or locally:
  python3 test_mcp.py --origin DEN --destination SFO --date 2026-03-01 --adults 2
  python3 test_mcp.py --origin DEN --destination SFO --date 2026-03-01 --return-date 2026-03-05 --adults 2
"""

import argparse
import datetime
import json
import os
import sys

# Suppress fast_flights stdout noise the same way server.py does
_real_stdout_fd = os.dup(1)
_devnull_fd = os.open(os.devnull, os.O_WRONLY)
os.dup2(_devnull_fd, 1)
os.close(_devnull_fd)
_real_stdout = os.fdopen(_real_stdout_fd, "w", buffering=1)
sys.stdout = _real_stdout

from fast_flights import FlightQuery, Passengers, create_query, get_flights


def dump_flight_raw(f, idx):
    """Print every attribute of a flight object for debugging."""
    print(f"\n{'='*60}")
    print(f"  FLIGHT #{idx}")
    print(f"{'='*60}")
    print(f"  price       = {f.price!r}")
    print(f"  airlines    = {f.airlines!r}")
    print(f"  type        = {f.type!r}")
    print(f"  is_best     = {getattr(f, 'is_best', 'N/A')!r}")

    segments = f.flights or []
    print(f"  segments    = {len(segments)}")

    for si, seg in enumerate(segments):
        print(f"\n  --- Segment {si} ---")
        print(f"    from_airport = {seg.from_airport!r}")
        if seg.from_airport:
            print(f"      .code = {getattr(seg.from_airport, 'code', 'N/A')!r}")
            print(f"      .name = {getattr(seg.from_airport, 'name', 'N/A')!r}")
        print(f"    to_airport   = {seg.to_airport!r}")
        if seg.to_airport:
            print(f"      .code = {getattr(seg.to_airport, 'code', 'N/A')!r}")
            print(f"      .name = {getattr(seg.to_airport, 'name', 'N/A')!r}")
        print(f"    departure    = {seg.departure!r}")
        if seg.departure:
            print(f"      .date = {getattr(seg.departure, 'date', 'N/A')!r}")
            print(f"      .time = {getattr(seg.departure, 'time', 'N/A')!r}")
        print(f"    arrival      = {seg.arrival!r}")
        if seg.arrival:
            print(f"      .date = {getattr(seg.arrival, 'date', 'N/A')!r}")
            print(f"      .time = {getattr(seg.arrival, 'time', 'N/A')!r}")
        print(f"    duration     = {getattr(seg, 'duration', 'N/A')!r}")
        print(f"    airline      = {getattr(seg, 'airline', 'N/A')!r}")
        print(f"    flight_no    = {getattr(seg, 'flight_no', 'N/A')!r}")

    # Dump all other attributes
    known = {'price', 'airlines', 'type', 'is_best', 'flights'}
    other_attrs = {k: v for k, v in vars(f).items() if k not in known and not k.startswith('_')}
    if other_attrs:
        print(f"\n  Other attributes:")
        for k, v in other_attrs.items():
            print(f"    {k} = {v!r}")


def format_datetime(sdt):
    if not sdt or not sdt.time:
        return "??:??"
    hours = sdt.time[0] if sdt.time[0] is not None else 0
    minutes = sdt.time[1] if len(sdt.time) > 1 and sdt.time[1] is not None else 0
    return f"{hours}:{minutes:02d}"


def format_segment(seg):
    dep = format_datetime(seg.departure)
    arr = format_datetime(seg.arrival)
    from_code = (seg.from_airport.code or "?") if seg.from_airport else "?"
    to_code = (seg.to_airport.code or "?") if seg.to_airport else "?"
    return f"{from_code} {dep}->{to_code} {arr}"


def format_flight(f):
    airlines = ", ".join(f.airlines) if f.airlines else (f.type or "Unknown")
    price = f"${f.price}" if f.price is not None else "N/A"
    segments = (f.flights or [])
    route = " / ".join(format_segment(seg) for seg in segments)
    stops = len(segments) - 1
    stop_str = "nonstop" if stops <= 0 else f"{stops} stop"
    duration = segments[0].duration if len(segments) == 1 and segments[0].duration else None
    dur_str = f", {duration}min" if duration else ""
    return f"**{price}** {airlines} | {route} ({stop_str}{dur_str})"


def test_one_way(origin, destination, date, adults, seat, max_stops):
    print(f"\n{'#'*60}")
    print(f"  ONE-WAY TEST: {origin} -> {destination} on {date}")
    print(f"  adults={adults}, seat={seat}, max_stops={max_stops}")
    print(f"{'#'*60}")

    query = create_query(
        flights=[FlightQuery(date=date, from_airport=origin, to_airport=destination)],
        trip="one-way",
        seat=seat,
        passengers=Passengers(adults=adults),
        max_stops=max_stops,
    )
    print(f"\nQuery URL: {query}")

    result = get_flights(query)
    print(f"\nResult type: {type(result)}")
    print(f"Result truthiness: {bool(result)}")

    if result is None:
        print("ERROR: get_flights returned None!")
        return

    flights_list = list(result)
    print(f"Total flights from list(): {len(flights_list)}")

    if not flights_list:
        print("No flights returned.")
        return

    # Raw dump of every flight
    print(f"\n{'='*60}")
    print(f"  RAW FLIGHT DATA ({len(flights_list)} flights)")
    print(f"{'='*60}")
    for i, f in enumerate(flights_list, 1):
        dump_flight_raw(f, i)

    # Now show what the MCP would format
    pax = f" for {adults} passengers" if adults > 1 else ""
    print(f"\n{'='*60}")
    print(f"  MCP FORMATTED OUTPUT")
    print(f"{'='*60}")
    header = f"## {len(flights_list)} One-Way Flights: {origin} -> {destination} on {date} (prices are total{pax})"
    print(header)
    for i, f in enumerate(flights_list, 1):
        formatted = format_flight(f)
        print(f"{i}. {formatted}")

    # Stats
    prices = [f.price for f in flights_list if f.price is not None]
    print(f"\n--- Stats ---")
    print(f"  Flights with price: {len(prices)}/{len(flights_list)}")
    if prices:
        print(f"  Price range: ${min(prices)} - ${max(prices)}")
    airline_set = set()
    for f in flights_list:
        if f.airlines:
            airline_set.update(f.airlines)
    print(f"  Airlines seen: {sorted(airline_set)}")


def test_round_trip(origin, destination, dep_date, ret_date, adults, seat, max_stops):
    print(f"\n{'#'*60}")
    print(f"  ROUND-TRIP TEST: {origin} <-> {destination}")
    print(f"  Depart: {dep_date} | Return: {ret_date}")
    print(f"  adults={adults}, seat={seat}, max_stops={max_stops}")
    print(f"{'#'*60}")

    query = create_query(
        flights=[
            FlightQuery(date=dep_date, from_airport=origin, to_airport=destination),
            FlightQuery(date=ret_date, from_airport=destination, to_airport=origin),
        ],
        trip="round-trip",
        seat=seat,
        passengers=Passengers(adults=adults),
        max_stops=max_stops,
    )
    print(f"\nQuery URL: {query}")

    result = get_flights(query)
    print(f"\nResult type: {type(result)}")
    print(f"Result truthiness: {bool(result)}")

    if result is None:
        print("ERROR: get_flights returned None!")
        return

    flights_list = list(result)
    print(f"Total flights from list(): {len(flights_list)}")

    if not flights_list:
        print("No flights returned.")
        return

    # Raw dump
    print(f"\n{'='*60}")
    print(f"  RAW FLIGHT DATA ({len(flights_list)} flights)")
    print(f"{'='*60}")
    for i, f in enumerate(flights_list, 1):
        dump_flight_raw(f, i)

    # MCP formatted
    pax = f" for {adults} passengers" if adults > 1 else ""
    print(f"\n{'='*60}")
    print(f"  MCP FORMATTED OUTPUT")
    print(f"{'='*60}")
    header = f"## {len(flights_list)} Round-Trip Flights: {origin} <-> {destination} (prices are total round-trip{pax})"
    print(header)
    print(f"Depart: {dep_date} | Return: {ret_date}")
    for i, f in enumerate(flights_list, 1):
        formatted = format_flight(f)
        print(f"{i}. {formatted}")

    # Stats
    prices = [f.price for f in flights_list if f.price is not None]
    print(f"\n--- Stats ---")
    print(f"  Flights with price: {len(prices)}/{len(flights_list)}")
    if prices:
        print(f"  Price range: ${min(prices)} - ${max(prices)}")
    airline_set = set()
    for f in flights_list:
        if f.airlines:
            airline_set.update(f.airlines)
    print(f"  Airlines seen: {sorted(airline_set)}")


def main():
    parser = argparse.ArgumentParser(description="Test Google Flights MCP")
    parser.add_argument("--origin", default="DEN", help="Origin airport code")
    parser.add_argument("--destination", default="SFO", help="Destination airport code")
    parser.add_argument("--date", default=None, help="Departure date (YYYY-MM-DD). Default: 7 days from now")
    parser.add_argument("--return-date", default=None, help="Return date for round-trip (YYYY-MM-DD)")
    parser.add_argument("--adults", type=int, default=1, help="Number of adults")
    parser.add_argument("--seat", default="economy", help="Seat type")
    parser.add_argument("--max-stops", type=int, default=None, help="Max stops (0=nonstop)")
    args = parser.parse_args()

    date = args.date or (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    # Always run one-way test
    test_one_way(args.origin, args.destination, date, args.adults, args.seat, args.max_stops)

    # Run round-trip if return date provided
    if args.return_date:
        test_round_trip(args.origin, args.destination, date, args.return_date, args.adults, args.seat, args.max_stops)
    else:
        # Default: round-trip with return 4 days later
        ret = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=4)).strftime("%Y-%m-%d")
        test_round_trip(args.origin, args.destination, date, ret, args.adults, args.seat, args.max_stops)


if __name__ == "__main__":
    main()

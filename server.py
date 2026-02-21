#!/usr/bin/env python
"""
Google Flights MCP Server

The fast_flights library dumps raw JS data to stdout, which would corrupt
the MCP stdio transport. We save the real stdout fd, then permanently
redirect fd 1 to /dev/null so the library's output is silenced. The MCP
server is given the saved fd to communicate on.
"""
import datetime
import sys
import os
from typing import Optional

# Save real stdout before anything can write to it, then redirect fd 1 to /dev/null.
_real_stdout_fd = os.dup(1)
_devnull_fd = os.open(os.devnull, os.O_WRONLY)
os.dup2(_devnull_fd, 1)
os.close(_devnull_fd)
_real_stdout = os.fdopen(_real_stdout_fd, "w", buffering=1)
sys.stdout = _real_stdout

from fast_flights import FlightQuery, Passengers, create_query, get_flights
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("google-flights-cheapest-finder")


def format_datetime(sdt):
    if not sdt or not sdt.time:
        return "??:??"
    hours = sdt.time[0] if sdt.time[0] is not None else 0
    minutes = sdt.time[1] if len(sdt.time) > 1 and sdt.time[1] is not None else 0
    return f"{hours}:{minutes:02d}"


def format_date(sdt):
    if not sdt or not sdt.date or len(sdt.date) < 3:
        return "????-??-??"
    y = sdt.date[0] if sdt.date[0] is not None else 0
    m = sdt.date[1] if sdt.date[1] is not None else 0
    d = sdt.date[2] if sdt.date[2] is not None else 0
    return f"{y:04d}-{m:02d}-{d:02d}"


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


def map_seat_type(seat_type: str) -> str:
    if not seat_type:
        return "economy"
    mapping = {
        "economy": "economy",
        "business": "business",
        "first": "first",
        "premium": "premium-economy",
        "premium-economy": "premium-economy",
        "premium_economy": "premium-economy",
    }
    return mapping.get(seat_type.lower(), "economy")


@mcp.tool()
async def get_flights_on_date(
    origin: str,
    destination: str,
    date: str,
    adults: int = 1,
    seat_type: str = "economy",
    return_cheapest_only: bool = False,
) -> str:
    """
    Fetches available one-way flights for a specific date between two airports.
    Prices shown are one-way fares per person.
    Can optionally return only the cheapest flight found.

    Args:
        origin: Origin airport code (e.g., "DEN").
        destination: Destination airport code (e.g., "LAX").
        date: The specific date to search (YYYY-MM-DD format).
        adults: Number of adult passengers (default: 1).
        seat_type: Fare class (e.g., "economy", "business", default: "economy").
        return_cheapest_only: If True, returns only the cheapest flight (default: False).
    """
    print(f"MCP Tool: Getting flights {origin}->{destination} for {date}...", file=sys.stderr)
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")

        query = create_query(
            flights=[FlightQuery(date=date, from_airport=origin, to_airport=destination)],
            trip="one-way",
            seat=map_seat_type(seat_type),
            passengers=Passengers(adults=adults),
        )
        result = get_flights(query)

        if result:
            flights_list = list(result)
            if not flights_list:
                return f"No flights found for {origin} -> {destination} on {date}."

            if return_cheapest_only:
                priced = [fl for fl in flights_list if fl.price is not None]
                if priced:
                    flights_list = [min(priced, key=lambda fl: fl.price)]

            lines = [f"## {len(flights_list)} One-Way Flights: {origin} -> {destination} on {date}"]
            for i, f in enumerate(flights_list, 1):
                lines.append(f"{i}. {format_flight(f)}")
            return "\n".join(lines)
        else:
            return f"No flights found for {origin} -> {destination} on {date}."

    except ValueError:
        return f"Error: Invalid date format '{date}'. Please use YYYY-MM-DD."
    except Exception as e:
        print(f"MCP Tool Error in get_flights_on_date: {e}", file=sys.stderr)
        return f"Error searching flights: {e}"


@mcp.tool()
async def get_round_trip_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int = 1,
    seat_type: str = "economy",
    return_cheapest_only: bool = False,
) -> str:
    """
    Fetches available round-trip flights for specific departure and return dates.
    Prices shown are total round-trip fares per person.
    Can optionally return only the cheapest flight found.

    Args:
        origin: Origin airport code (e.g., "DEN").
        destination: Destination airport code (e.g., "LAX").
        departure_date: The specific departure date (YYYY-MM-DD format).
        return_date: The specific return date (YYYY-MM-DD format).
        adults: Number of adult passengers (default: 1).
        seat_type: Fare class (e.g., "economy", "business", default: "economy").
        return_cheapest_only: If True, returns only the cheapest flight (default: False).
    """
    print(f"MCP Tool: Getting round trip {origin}<->{destination} for {departure_date} to {return_date}...", file=sys.stderr)
    try:
        datetime.datetime.strptime(departure_date, "%Y-%m-%d")
        datetime.datetime.strptime(return_date, "%Y-%m-%d")

        query = create_query(
            flights=[
                FlightQuery(date=departure_date, from_airport=origin, to_airport=destination),
                FlightQuery(date=return_date, from_airport=destination, to_airport=origin),
            ],
            trip="round-trip",
            seat=map_seat_type(seat_type),
            passengers=Passengers(adults=adults),
        )
        result = get_flights(query)

        if result:
            flights_list = list(result)
            if not flights_list:
                return f"No round-trip flights found for {origin} <-> {destination}."

            if return_cheapest_only:
                priced = [fl for fl in flights_list if fl.price is not None]
                if priced:
                    flights_list = [min(priced, key=lambda fl: fl.price)]

            lines = [f"## {len(flights_list)} Round-Trip Flights: {origin} <-> {destination} (prices are round-trip)", f"Depart: {departure_date} | Return: {return_date}"]
            for i, f in enumerate(flights_list, 1):
                lines.append(f"{i}. {format_flight(f)}")
            return "\n".join(lines)
        else:
            return f"No round-trip flights found for {origin} <-> {destination}."

    except ValueError:
        return "Error: Invalid date format. Please use YYYY-MM-DD."
    except Exception as e:
        print(f"MCP Tool Error in get_round_trip_flights: {e}", file=sys.stderr)
        return f"Error searching flights: {e}"


@mcp.tool(name="find_all_flights_in_range")
async def find_all_flights_in_range(
    origin: str,
    destination: str,
    start_date_str: str,
    end_date_str: str,
    min_stay_days: Optional[int] = None,
    max_stay_days: Optional[int] = None,
    adults: int = 1,
    seat_type: str = "economy",
    return_cheapest_only: bool = False,
) -> str:
    """
    Finds available round-trip flights within a specified date range.
    Prices shown are total round-trip fares per person.
    Can optionally return only the cheapest flight found for each date pair.

    Args:
        origin: Origin airport code (e.g., "DEN").
        destination: Destination airport code (e.g., "LAX").
        start_date_str: Start date of the search range (YYYY-MM-DD format).
        end_date_str: End date of the search range (YYYY-MM-DD format).
        min_stay_days: Minimum number of days for the stay (optional).
        max_stay_days: Maximum number of days for the stay (optional).
        adults: Number of adult passengers (default: 1).
        seat_type: Fare class (e.g., "economy", "business", default: "economy").
        return_cheapest_only: If True, returns only the cheapest flight for each date pair (default: False).
    """
    search_mode = "cheapest per pair" if return_cheapest_only else "all flights"
    print(f"MCP Tool: Finding {search_mode} {origin}<->{destination} between {start_date_str} and {end_date_str}...", file=sys.stderr)

    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Error: Invalid date format. Please use YYYY-MM-DD."

    if start_date > end_date:
        return "Error: Start date cannot be after end date."

    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date)
        current_date += datetime.timedelta(days=1)

    if not date_list:
        return "Error: No valid dates in the specified range."

    date_pairs_to_check = []
    for i, depart_date in enumerate(date_list):
        for ret_date in date_list[i:]:
            stay_duration = (ret_date - depart_date).days
            valid_stay = True
            if min_stay_days is not None and stay_duration < min_stay_days:
                valid_stay = False
            if max_stay_days is not None and stay_duration > max_stay_days:
                valid_stay = False
            if valid_stay:
                date_pairs_to_check.append((depart_date, ret_date))

    total_combinations = len(date_pairs_to_check)
    print(f"MCP Tool: Checking {total_combinations} date combinations...", file=sys.stderr)

    lines = [f"## Round-Trip Flight Search: {origin} <-> {destination} (prices are round-trip)", f"**Range:** {start_date_str} to {end_date_str}", ""]
    errors = []

    for count, (depart_date, ret_date) in enumerate(date_pairs_to_check, 1):
        if count % 10 == 0:
            print(f"MCP Tool Progress: {count}/{total_combinations}", file=sys.stderr)

        try:
            query = create_query(
                flights=[
                    FlightQuery(date=depart_date.strftime("%Y-%m-%d"), from_airport=origin, to_airport=destination),
                    FlightQuery(date=ret_date.strftime("%Y-%m-%d"), from_airport=destination, to_airport=origin),
                ],
                trip="round-trip",
                seat=map_seat_type(seat_type),
                passengers=Passengers(adults=adults),
            )
            result = get_flights(query)

            if result:
                flights_list = list(result)
                if flights_list:
                    if return_cheapest_only:
                        priced = [fl for fl in flights_list if fl.price is not None]
                        if priced:
                            flights_list = [min(priced, key=lambda fl: fl.price)]

                    dep_str = depart_date.strftime("%Y-%m-%d")
                    ret_str = ret_date.strftime("%Y-%m-%d")
                    stay = (ret_date - depart_date).days
                    lines.append(f"### {dep_str} -> {ret_str} ({stay} days)")
                    for f in flights_list:
                        lines.append(f"- {format_flight(f)}")
                    lines.append("")

        except Exception as e:
            print(f"MCP Tool Error for {depart_date} -> {ret_date}: {type(e).__name__} - {e}", file=sys.stderr)
            err_msg = f"{depart_date.strftime('%Y-%m-%d')} -> {ret_date.strftime('%Y-%m-%d')}: {type(e).__name__}"
            if err_msg not in errors:
                errors.append(err_msg)

    print("MCP Tool: Range search complete.", file=sys.stderr)

    lines.append(f"*Searched {total_combinations} date combination(s), {adults} adult(s), {seat_type}*")
    if errors:
        lines.append(f"\n**Errors:** {len(errors)} date pair(s) failed")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

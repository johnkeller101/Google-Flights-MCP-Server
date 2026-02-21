#!/usr/bin/env python
import json
import datetime
import sys
from typing import Optional

from fast_flights import FlightQuery, Passengers, create_query, get_flights
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("google-flights-cheapest-finder")


def single_flight_to_dict(sf):
    """Converts a SingleFlight segment to a dictionary."""
    return {
        "from_airport": {"name": sf.from_airport.name, "code": sf.from_airport.code},
        "to_airport": {"name": sf.to_airport.name, "code": sf.to_airport.code},
        "departure": format_datetime(sf.departure),
        "arrival": format_datetime(sf.arrival),
        "duration_minutes": sf.duration,
        "plane_type": sf.plane_type,
    }


def format_datetime(sdt):
    """Formats a SimpleDatetime as a readable string."""
    date_part = f"{sdt.date[0]:04d}-{sdt.date[1]:02d}-{sdt.date[2]:02d}"
    time_part = f"{sdt.time[0]:02d}:{sdt.time[1]:02d}"
    return f"{date_part} {time_part}"


def flights_to_dict(flights_obj):
    """Converts a Flights object to a dictionary."""
    result = {
        "airlines": flights_obj.airlines,
        "price": flights_obj.price,
        "type": flights_obj.type,
        "segments": [single_flight_to_dict(sf) for sf in flights_obj.flights],
    }
    if flights_obj.carbon:
        result["carbon_emission_grams"] = flights_obj.carbon.emission
        result["typical_carbon_grams"] = flights_obj.carbon.typical_on_route
    return result


def map_seat_type(seat_type: str) -> str:
    """Maps common seat type names to fast_flights expected values."""
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
                return json.dumps({"message": f"No flights found for {origin} -> {destination} on {date}."})

            if return_cheapest_only:
                cheapest = min(flights_list, key=lambda f: f.price)
                processed = [flights_to_dict(cheapest)]
                result_key = "cheapest_flight"
            else:
                processed = [flights_to_dict(f) for f in flights_list]
                result_key = "flights"

            return json.dumps(
                {
                    "search_parameters": {
                        "origin": origin,
                        "destination": destination,
                        "date": date,
                        "adults": adults,
                        "seat_type": seat_type,
                        "return_cheapest_only": return_cheapest_only,
                    },
                    result_key: processed,
                },
                indent=2,
            )
        else:
            return json.dumps({"message": f"No flights found for {origin} -> {destination} on {date}."})

    except ValueError:
        return json.dumps({"error": {"message": f"Invalid date format: '{date}'. Please use YYYY-MM-DD.", "type": "ValueError"}})
    except Exception as e:
        print(f"MCP Tool Error in get_flights_on_date: {e}", file=sys.stderr)
        return json.dumps({"error": {"message": str(e), "type": type(e).__name__}})


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
                return json.dumps({"message": f"No round trip flights found for {origin} <-> {destination}."})

            if return_cheapest_only:
                cheapest = min(flights_list, key=lambda f: f.price)
                processed = [flights_to_dict(cheapest)]
                result_key = "cheapest_round_trip_option"
            else:
                processed = [flights_to_dict(f) for f in flights_list]
                result_key = "round_trip_options"

            return json.dumps(
                {
                    "search_parameters": {
                        "origin": origin,
                        "destination": destination,
                        "departure_date": departure_date,
                        "return_date": return_date,
                        "adults": adults,
                        "seat_type": seat_type,
                        "return_cheapest_only": return_cheapest_only,
                    },
                    result_key: processed,
                },
                indent=2,
            )
        else:
            return json.dumps({"message": f"No round trip flights found for {origin} <-> {destination}."})

    except ValueError:
        return json.dumps({"error": {"message": "Invalid date format. Use YYYY-MM-DD.", "type": "ValueError"}})
    except Exception as e:
        print(f"MCP Tool Error in get_round_trip_flights: {e}", file=sys.stderr)
        return json.dumps({"error": {"message": str(e), "type": type(e).__name__}})


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
    search_mode = "cheapest flight per pair" if return_cheapest_only else "all flights"
    print(f"MCP Tool: Finding {search_mode} {origin}<->{destination} between {start_date_str} and {end_date_str}...", file=sys.stderr)

    results_data = []
    error_messages = []

    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        return json.dumps({"error": {"message": "Invalid date format. Use YYYY-MM-DD.", "type": "ValueError"}})

    if start_date > end_date:
        return json.dumps({"error": {"message": "Start date cannot be after end date.", "type": "ValueError"}})

    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date)
        current_date += datetime.timedelta(days=1)

    if not date_list:
        return json.dumps({"error": "No valid dates in the specified range."})

    date_pairs_to_check = []
    for i, depart_date in enumerate(date_list):
        for return_date in date_list[i:]:
            stay_duration = (return_date - depart_date).days
            valid_stay = True
            if min_stay_days is not None and stay_duration < min_stay_days:
                valid_stay = False
            if max_stay_days is not None and stay_duration > max_stay_days:
                valid_stay = False
            if valid_stay:
                date_pairs_to_check.append((depart_date, return_date))

    total_combinations = len(date_pairs_to_check)
    print(f"MCP Tool: Checking {total_combinations} valid date combinations in range...", file=sys.stderr)

    for count, (depart_date, return_date) in enumerate(date_pairs_to_check, 1):
        if count % 10 == 0:
            print(f"MCP Tool Progress: {count}/{total_combinations}", file=sys.stderr)

        try:
            query = create_query(
                flights=[
                    FlightQuery(date=depart_date.strftime("%Y-%m-%d"), from_airport=origin, to_airport=destination),
                    FlightQuery(date=return_date.strftime("%Y-%m-%d"), from_airport=destination, to_airport=origin),
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
                        cheapest = min(flights_list, key=lambda f: f.price)
                        results_data.append({
                            "departure_date": depart_date.strftime("%Y-%m-%d"),
                            "return_date": return_date.strftime("%Y-%m-%d"),
                            "cheapest_flight": flights_to_dict(cheapest),
                        })
                    else:
                        results_data.append({
                            "departure_date": depart_date.strftime("%Y-%m-%d"),
                            "return_date": return_date.strftime("%Y-%m-%d"),
                            "flights": [flights_to_dict(f) for f in flights_list],
                        })

        except Exception as e:
            print(f"MCP Tool Error for {depart_date} -> {return_date}: {type(e).__name__} - {e}", file=sys.stderr)
            err_msg = f"Error for {depart_date.strftime('%Y-%m-%d')} -> {return_date.strftime('%Y-%m-%d')}: {type(e).__name__}"
            if err_msg not in error_messages:
                error_messages.append(err_msg)

    print("MCP Tool: Range search complete.", file=sys.stderr)

    results_key = "cheapest_option_per_date_pair" if return_cheapest_only else "all_round_trip_options"
    return json.dumps(
        {
            "search_parameters": {
                "origin": origin,
                "destination": destination,
                "start_date": start_date_str,
                "end_date": end_date_str,
                "min_stay_days": min_stay_days,
                "max_stay_days": max_stay_days,
                "adults": adults,
                "seat_type": seat_type,
                "return_cheapest_only": return_cheapest_only,
            },
            results_key: results_data,
            "errors_encountered": error_messages if error_messages else None,
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

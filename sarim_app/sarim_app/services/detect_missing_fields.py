def detect_missing_fields(data):
    # Must-have passenger-level fields
    REQUIRED_PASSENGER_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]

    # Optional but preferred passenger-level fields
    # OPTIONAL_PASSENGER_FIELDS = ["passenger_number", "pickup_time", "reporting_time"]

    # Must-have outer fields (top-level)
    REQUIRED_TRIP_FIELDS = ["point_of_contact", "booked_by", "billed_to"]

    missing = {
        "bookings": [],   # per-passenger missing data
        "trip_level": []  # top-level missing data
    }

    # --- Check passenger-level fields ---
    bookings = data.get("bookings", [])
    if isinstance(bookings, dict):
        bookings = [bookings]

    for idx, b in enumerate(bookings):
        missing_fields = []

        # required passenger fields
        for f in REQUIRED_PASSENGER_FIELDS:
            if not b.get(f):
                missing_fields.append(f)

        # number fallback logic (use POC number if no passenger number)
        if not b.get("passenger_number"):
            if not data.get("point_of_contact", {}).get("number"):
                missing_fields.append("passenger_number")

        # pickup_time/reporting_time fallback
        if not b.get("pickup_time") and not b.get("reporting_time"):
            missing_fields.append("pickup_time/reporting_time")

        if missing_fields:
            missing["bookings"].append({
                "index": idx + 1,
                "missing_fields": missing_fields
            })

    # --- Check outer fields ---
    for f in REQUIRED_TRIP_FIELDS:
        if not data.get(f) or not any(data[f].values()):
            missing["trip_level"].append(f)

    return missing
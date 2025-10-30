def detect_missing_fields(data):
    """
    Detect missing fields per booking row.
    Works with booking_number-based mapping and avoids permanent #TEMP IDs.
    """

    REQUIRED_PASSENGER_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]
    missing = {"bookings": []}

    bookings = data.get("bookings", [])
    if isinstance(bookings, dict):
        bookings = [bookings]

    for idx, b in enumerate(bookings):
        missing_fields = []

        # Passenger-level required fields
        for f in REQUIRED_PASSENGER_FIELDS:
            if not b.get(f):
                missing_fields.append(f)

        # Passenger number check
        if not b.get("passenger_number") and not data.get("point_of_contact", {}).get("number"):
            missing_fields.append("passenger_number")

        # Pickup time / Reporting time check
        if not b.get("pickup_time") and not b.get("reporting_time"):
            missing_fields.append("pickup_time/reporting_time")

        # ✅ Booking number: only TEMP if nothing assigned yet
        booking_number = b.get("booking_number")
        if not booking_number or booking_number.strip() == "":
            booking_number = f"#TEMP{idx + 1}"

        # ✅ Add entry only if something is missing
        if missing_fields:
            missing["bookings"].append({
                "booking_number": booking_number,
                "missing_fields": missing_fields
            })

    return missing


# def detect_missing_fields(data):
#     """
#     Detects missing fields for each booking (child table row).
#     Trip-level fields are intentionally ignored in this version.
#     Works cleanly with booking_number-based mapping.
#     """

#     REQUIRED_PASSENGER_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]

#     missing = {"bookings": []}

#     # --- Normalize booking data ---
#     bookings = data.get("bookings", [])
#     if isinstance(bookings, dict):
#         bookings = [bookings]

#     # --- Loop through each booking ---
#     for idx, b in enumerate(bookings):
#         missing_fields = []

#         # Required passenger-level fields
#         for f in REQUIRED_PASSENGER_FIELDS:
#             if not b.get(f):
#                 missing_fields.append(f)

#         # passenger_number check
#         if not b.get("passenger_number") and not data.get("point_of_contact", {}).get("number"):
#             missing_fields.append("passenger_number")

#         # pickup_time / reporting_time check
#         if not b.get("pickup_time") and not b.get("reporting_time"):
#             missing_fields.append("pickup_time/reporting_time")

#         # ✅ use exact booking_number if exists
#         booking_number = b.get("booking_number")
#         if not booking_number:
#             # fallback only if not assigned yet
#             booking_number = f"#TEMP{idx + 1}"

#         # only add if something missing
#         if missing_fields:
#             missing["bookings"].append({
#                 "booking_number": booking_number,
#                 "missing_fields": missing_fields
#             })

#     return missing


# def detect_missing_fields(data):
#     """
#     Detects missing fields for each booking (child table row).
#     Trip-level fields are intentionally ignored in this version.
#     """

#     REQUIRED_PASSENGER_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]

#     missing = {
#         "bookings": []   # per-passenger missing data only
#     }

#     # --- Normalize booking data ---
#     bookings = data.get("bookings", [])
#     if isinstance(bookings, dict):
#         bookings = [bookings]

#     # --- Loop through each booking ---
#     for idx, b in enumerate(bookings):
#         missing_fields = []

#         # Required passenger-level fields
#         for f in REQUIRED_PASSENGER_FIELDS:
#             if not b.get(f):
#                 missing_fields.append(f)

#         # passenger_number fallback logic
#         if not b.get("passenger_number"):
#             # optional fallback on point_of_contact number if you want:
#             if not data.get("point_of_contact", {}).get("number"):
#                 missing_fields.append("passenger_number")

#         # pickup_time/reporting_time fallback
#         if not b.get("pickup_time") and not b.get("reporting_time"):
#             missing_fields.append("pickup_time/reporting_time")

#         # identify booking_number (if assigned)
#         booking_number = b.get("booking_number") or f"{idx + 1}"

#         if missing_fields:
#             missing["bookings"].append({
#                 "index": idx + 1,
#                 "booking_number": booking_number,
#                 "missing_fields": missing_fields
#             })

#     return missing

# def detect_missing_fields(data):
#     # Must-have passenger-level fields
#     REQUIRED_PASSENGER_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]

#     # Optional but preferred passenger-level fields
#     # OPTIONAL_PASSENGER_FIELDS = ["passenger_number", "pickup_time", "reporting_time"]

#     # Must-have outer fields (top-level)
#     REQUIRED_TRIP_FIELDS = ["point_of_contact", "booked_by", "billed_to"]

#     missing = {
#         "bookings": [],   # per-passenger missing data
#         "trip_level": []  # top-level missing data
#     }

#     # --- Check passenger-level fields ---
#     bookings = data.get("bookings", [])
#     if isinstance(bookings, dict):
#         bookings = [bookings]

#     for idx, b in enumerate(bookings):
#         missing_fields = []

#         # required passenger fields
#         for f in REQUIRED_PASSENGER_FIELDS:
#             if not b.get(f):
#                 missing_fields.append(f)

#         # number fallback logic (use POC number if no passenger number)
#         if not b.get("passenger_number"):
#             if not data.get("point_of_contact", {}).get("number"):
#                 missing_fields.append("passenger_number")

#         # pickup_time/reporting_time fallback
#         if not b.get("pickup_time") and not b.get("reporting_time"):
#             missing_fields.append("pickup_time/reporting_time")

#         if missing_fields:
#             missing["bookings"].append({
#                 "index": idx + 1,
#                 "missing_fields": missing_fields
#             })

#     # --- Check outer fields ---
#     for f in REQUIRED_TRIP_FIELDS:
#         if not data.get(f) or not any(data[f].values()):
#             missing["trip_level"].append(f)

#     return missing

# def detect_missing_fields(data):
#     REQUIRED_BOOKING_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]

#     missing = {"bookings": []}

#     bookings = data.get("bookings", [])
#     if isinstance(bookings, dict):
#         bookings = [bookings]

#     for idx, b in enumerate(bookings):
#         missing_fields = []
#         for field in REQUIRED_BOOKING_FIELDS:
#             if not b.get(field):
#                 missing_fields.append(field)

#         if not b.get("pickup_time") and not b.get("reporting_time"):
#             missing_fields.append("pickup_time/reporting_time")

#         if not b.get("passenger_number"):
#             missing_fields.append("passenger_number")

#         if missing_fields:
#             missing["bookings"].append({
#                 "index": idx + 1,
#                 "missing_fields": missing_fields
#             })

#     return missing

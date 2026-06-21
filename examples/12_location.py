# -*- coding: utf-8 -*-
"""Location examples — demonstrates every LocationMixin method (all read-only)."""
from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    writes_disabled_note,
)

cl = login(get_client())

section("Search examples")

# Search for venues near a lat/lng coordinate, filtered by a text query
show("location_search", cl.location_search(lat=13.7563, lng=100.5018, query="cafe"))

# Same coordinate search but return only the single best-matching venue
show("location_search_one", cl.location_search_one(lat=13.7563, lng=100.5018, query="cafe"))

# Search for places by free-text query (Facebook places search)
places = cl.fbsearch_places("Bangkok")
show("fbsearch_places", len(places))

# Resolve a numeric location_pk from the first place returned (guard if empty)
location_pk = None
if places:
    first = places[0]
    place = first.get("location") or first
    location_pk = place.get("pk") or place.get("external_id") or first.get("external_id")
show("resolved location_pk", location_pk)

section("Read examples (by location_pk)")
if location_pk:
    # Fetch info about a location by its location_pk
    show("location_info", cl.location_info(location_pk))

    # Fetch complaint / report info for a location
    show("location_complaint_info", cl.location_complaint_info(location_pk))

    # Fetch the current stories tagged with this location
    show("location_story", cl.location_story(location_pk))

    # Fetch locations related to this location
    show("location_related", cl.location_related(location_pk))

    # Fetch up to 20 of the top posts (ranked tab) tagged at this location
    show("location_medias_top", len(cl.location_medias_top(location_pk, amount=20)))

    # Fetch up to 20 of the latest posts (recent tab) tagged at this location
    show("location_medias_recent", len(cl.location_medias_recent(location_pk, amount=20)))
else:
    show("location_pk", "no place found — skipping location_pk-based reads")

section("Build helper")
if places:
    # Build a JSON 'location' payload (for tagging when posting) from a place dict
    show("location_build", cl.location_build(places[0]))
else:
    show("location_build", "no place found — skipping location_build")

section("Write examples (guarded)")
if RUN_WRITES:
    # LocationMixin read/build methods only — no write methods in this category
    writes_disabled_note()
else:
    writes_disabled_note()

print("\nLocation examples done.")

#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 32
TIMEOUT_SECONDS = 180
OUTPUT_FILE = "campus_events_100_generated_sql_db32.sql"

QUESTIONS: List[str] = [
    "List scheduled events in rooms whose capacity is lower than expected attendance.",
    "Find departments where every organizer has created at least one event.",
    "List attendees who registered for events outside their own department's college.",
    "Find events with no feedback but at least one industry sponsor.",
    "List organizers whose events received feedback from every attendee affiliation.",
    "Find rooms that hosted cancelled events and also hosted completed events later.",
    "List sponsors that funded events in every campus zone.",
    "Find attendees whose latest registration was cancelled but who previously checked in to an event.",
    "List events where total sponsor amount exceeds expected attendance.",
    "Find departments whose attendees registered for all event types represented in events.",
    "List buildings whose rooms have hosted every event status.",
    "Find events where every registered attendee checked in.",
    "List organizers whose average event rating is above the average rating for organizers in the same department.",
    "Find attendees who gave high ratings to events sponsored by government sponsors.",
    "List rooms where the number of registrations exceeded room capacity.",
    "Find events with at least one sponsor but no checked-in attendees.",
    "List departments whose organizers have scheduled events in every building.",
    "Find sponsors whose total contribution is above the average sponsor contribution.",
    "List attendees who registered for both workshop and social events.",
    "Find events whose latest feedback rating is below 3.",
    "List rooms that never hosted a cancelled event but hosted at least one completed event.",
    "Find organizers whose events have more distinct sponsor types than distinct attendee affiliations.",
    "List events where checked-in attendees are fewer than waitlisted registrations.",
    "Find departments where every event organized by that department has feedback.",
    "List attendees who checked in to all events for at least one organizer.",
    "Find sponsors that funded events attended by every class year.",
    "List events whose feedback average is higher than the average feedback for the same event type.",
    "Find buildings where all rooms have hosted at least one event.",
    "List organizers who have cancelled events but no completed events.",
    "Find attendees who registered for events in every campus zone.",
    "List events with no sponsor but at least one feedback rating of 5.",
    "Find rooms whose average event expected attendance is above their capacity.",
    "List departments whose attendees gave feedback in all comment topics.",
    "Find sponsors that funded only scheduled events.",
    "List events where the organizer's department differs from the majority attendee department.",
    "Find attendees whose checked-in registration count is greater than their cancelled registration count.",
    "List rooms where the latest event is scheduled.",
    "Find event types where every event has at least one sponsor.",
    "List organizers with events in rooms from more than one campus zone.",
    "Find departments whose organizers received higher average ratings than the overall average rating.",
    "List events with industry sponsor amount greater than community sponsor amount.",
    "Find attendees who registered for an event but never submitted feedback for that event.",
    "List sponsors whose funded events have average rating above 4.",
    "Find events whose sponsor count is above the average sponsor count per event.",
    "List buildings with rooms that hosted events from every department.",
    "Find organizers whose events are all scheduled or completed, with no cancelled events.",
    "List attendees who checked in to events sponsored by all sponsor types.",
    "Find events where expected attendance is greater than checked-in registrations.",
    "List rooms with no registrations for any event.",
    "Find departments where student organizers scheduled more events than faculty organizers.",
    "List events that have feedback from attendees in a different department than the organizer.",
    "Find sponsors that funded events with no feedback lower than 3.",
    "List attendees who registered for the same event type in at least three different buildings.",
    "Find rooms where total checked-in registrations exceed total capacity across hosted events.",
    "List organizers whose latest event was cancelled.",
    "Find events that have sponsors but no registrations.",
    "List departments with attendees who checked in to every event type.",
    "Find sponsor types whose total sponsored amount is above the average total amount per sponsor type.",
    "List events whose average feedback is the highest within their event type, including ties.",
    "Find attendees who registered for all events in their own department.",
    "List buildings where no room has ever hosted a cancelled event.",
    "Find departments whose events attracted attendees from every affiliation.",
    "List sponsors that funded events in more departments than the average sponsor.",
    "Find events where all feedback ratings are 4 or higher.",
    "List rooms whose cancelled-event count is higher than completed-event count.",
    "Find organizers who scheduled events in every room type.",
    "List attendees whose average feedback rating is below the average rating for their department.",
    "Find events with a university sponsor and at least one guest attendee.",
    "List departments whose attendees never registered for cancelled events.",
    "Find sponsors whose events have more checked-in attendees than total expected attendance.",
    "List events where the highest feedback rating came after the event date.",
    "Find attendees who were waitlisted for an event but later checked in to another event of the same type.",
    "List organizers whose events received feedback on every comment topic.",
    "Find rooms where the average rating of events is higher than the building average.",
    "List departments whose organizers have no events with low ratings.",
    "Find sponsors that funded events where every registered attendee checked in.",
    "List events whose sponsor amount is above the average sponsor amount for the same sponsor type.",
    "Find attendees who registered for events organized by every staff level.",
    "List buildings where every room type has hosted at least one event.",
    "Find events with more feedback submissions than checked-in registrations.",
    "List organizers whose events have no waitlisted registrations.",
    "Find departments whose attendees have average rating above the overall average rating.",
    "List sponsors that funded events in all colleges represented by organizer departments.",
    "Find events whose checked-in count is higher than the average checked-in count for events in the same room type.",
    "List rooms that hosted events from more than three departments.",
    "Find attendees who checked in to events in every building campus zone.",
    "List organizers whose scheduled events have no sponsor.",
    "Find departments where every attendee has registered for at least one event.",
    "List events with both government and industry sponsors.",
    "Find sponsors that funded events whose latest registration was cancelled.",
    "List rooms where every event has at least one checked-in attendee.",
    "Find attendees who registered for events with every sponsor type.",
    "List departments whose organizers have events with total sponsorship above department average.",
    "Find events where the number of distinct attendee departments exceeds the number of distinct sponsors.",
    "List sponsors that never funded cancelled events.",
    "Find organizers with more completed events than scheduled events.",
    "List buildings whose average room capacity is above the average expected attendance of events hosted there.",
    "Find attendees whose latest feedback was for an event they checked in to.",
    "List events with no checked-in attendees but at least one sponsor.",
    "Find departments where all organizers are staff or faculty and every organizer has at least one event."
]


def post_query(question: str) -> Dict[str, Any]:
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/database/{DATABASE_ID}/execute_sql",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql")
    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    sql = response.get("sql")
    if isinstance(sql, str) and sql.strip():
        return sql.strip()
    return "-- NO SQL GENERATED"


def normalize_sql(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        return "-- NO SQL GENERATED;"
    if sql.startswith("--"):
        return sql
    return sql if sql.endswith(";") else sql + ";"


def main() -> None:
    output_path = Path(OUTPUT_FILE)
    with output_path.open("w", encoding="utf-8") as out:
        for question in QUESTIONS:
            try:
                sql = normalize_sql(extract_sql(post_query(question)))
            except Exception as exc:
                sql = f"-- ERROR: {type(exc).__name__}: {exc}"
            print(sql)
            print()
            out.write(sql + "\n\n")


if __name__ == "__main__":
    main()

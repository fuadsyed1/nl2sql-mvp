SELECT e.event_id, e.event_title, e.event_date
FROM events e
JOIN rooms r ON e.room_id = r.room_id
WHERE e.status = 'scheduled'
  AND r.capacity < e.expected_attendance;

SELECT d.department_name
FROM departments d
JOIN organizers o ON d.department_id = o.department_id
JOIN events e ON o.organizer_id = e.organizer_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(DISTINCT o.organizer_id) = (
    SELECT COUNT(*)
    FROM organizers o2
    WHERE o2.department_id = d.department_id
);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN organizers o ON e.organizer_id = o.organizer_id
JOIN departments d_att ON a.department_id = d_att.department_id
JOIN departments d_org ON o.department_id = d_org.department_id
WHERE d_att.college != d_org.college;

SELECT e.event_id, e.event_title
FROM events e
INNER JOIN event_sponsors es ON e.event_id = es.event_id
INNER JOIN sponsors s ON es.sponsor_id = s.sponsor_id
WHERE s.sponsor_type = 'industry'
  AND NOT EXISTS (
    SELECT 1
    FROM event_feedback ef
    WHERE ef.event_id = e.event_id
  )
GROUP BY e.event_id, e.event_title
HAVING COUNT(es.event_sponsor_id) >= 1;

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
JOIN event_feedback ef ON e.event_id = ef.event_id
JOIN attendees a ON ef.attendee_id = a.attendee_id
GROUP BY o.organizer_id, o.organizer_name
HAVING COUNT(DISTINCT a.affiliation) = (
    SELECT COUNT(DISTINCT affiliation)
    FROM attendees
);

SELECT DISTINCT r1.room_id, r1.room_name
FROM rooms r1
JOIN events e1 ON r1.room_id = e1.room_id
JOIN events e2 ON r1.room_id = e2.room_id
WHERE e1.status = 'cancelled'
  AND e2.status = 'completed'
  AND e2.event_date > e1.event_date;

SELECT s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN rooms r ON e.room_id = r.room_id
JOIN buildings b ON r.building_id = b.building_id
GROUP BY s.sponsor_id, s.sponsor_name
HAVING COUNT(DISTINCT b.campus_zone) = (SELECT COUNT(DISTINCT campus_zone) FROM buildings);

WITH ranked_registrations AS (
    SELECT 
        r.attendee_id,
        r.registration_status,
        r.checked_in,
        r.registered_at,
        ROW_NUMBER() OVER (PARTITION BY r.attendee_id ORDER BY r.registered_at DESC) AS rn
    FROM registrations r
)
SELECT 
    a.attendee_id,
    a.attendee_name
FROM attendees a
JOIN ranked_registrations latest ON a.attendee_id = latest.attendee_id AND latest.rn = 1
JOIN ranked_registrations prev ON a.attendee_id = prev.attendee_id AND prev.rn > 1
WHERE latest.registration_status = 'cancelled'
  AND prev.checked_in = 'yes';

SELECT e.event_id, e.event_title
FROM events e
JOIN event_sponsors es ON e.event_id = es.event_id
GROUP BY e.event_id, e.event_title
HAVING SUM(es.amount) > e.expected_attendance;

SELECT d.department_id, d.department_name
FROM departments d
JOIN attendees a ON d.department_id = a.department_id
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(DISTINCT e.event_type) = (SELECT COUNT(DISTINCT event_type) FROM events);

SELECT b.building_name
FROM buildings b
JOIN rooms r ON b.building_id = r.building_id
JOIN events e ON r.room_id = e.room_id
GROUP BY b.building_id, b.building_name
HAVING COUNT(DISTINCT e.status) = (SELECT COUNT(DISTINCT status) FROM events);

SELECT "events"."event_id", "events"."event_title", COUNT(*) AS "total_registrations", COUNT("registrations"."checked_in") AS "checked_in_count" FROM "events" LEFT JOIN "registrations" ON "events"."event_id" = "registrations"."event_id" GROUP BY "events"."event_id", "events"."event_title" HAVING "total_registrations" = "checked_in_count";

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
JOIN event_feedback ef ON e.event_id = ef.event_id
WHERE ef.rating > (
    SELECT AVG(ef2.rating)
    FROM organizers o2
    JOIN events e2 ON o2.organizer_id = e2.organizer_id
    JOIN event_feedback ef2 ON e2.event_id = ef2.event_id
    WHERE o2.department_id = o.department_id
)
GROUP BY o.organizer_id, o.organizer_name, o.department_id;

SELECT DISTINCT a.attendee_id, a.attendee_name
FROM attendees a
JOIN event_feedback ef ON a.attendee_id = ef.attendee_id
JOIN events e ON ef.event_id = e.event_id
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
WHERE s.sponsor_type = 'government'
  AND ef.rating >= 4;

SELECT r.room_id, r.room_name
FROM rooms r
JOIN registrations reg ON r.room_id = (
    SELECT e.room_id
    FROM events e
    WHERE e.event_id = reg.event_id
)
GROUP BY r.room_id, r.room_name
HAVING COUNT(reg.registration_id) > r.capacity;

SELECT e.event_id, e.event_title
FROM events e
WHERE EXISTS (
    SELECT 1
    FROM event_sponsors es
    WHERE es.event_id = e.event_id
)
AND NOT EXISTS (
    SELECT 1
    FROM registrations r
    WHERE r.event_id = e.event_id
    AND r.checked_in = 'yes'
);

SELECT d.department_name
FROM departments d
JOIN organizers o ON d.department_id = o.department_id
JOIN events e ON o.organizer_id = e.organizer_id
JOIN rooms r ON e.room_id = r.room_id
JOIN buildings b ON r.building_id = b.building_id
WHERE e.status = 'scheduled'
GROUP BY d.department_id
HAVING COUNT(DISTINCT b.building_id) = (SELECT COUNT(*) FROM buildings);

SELECT s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
GROUP BY s.sponsor_id
HAVING SUM(es.amount) > (
    SELECT AVG(total_contribution)
    FROM (
        SELECT SUM(es2.amount) AS total_contribution
        FROM event_sponsors es2
        GROUP BY es2.sponsor_id
    )
);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
WHERE EXISTS (
    SELECT 1
    FROM registrations r
    JOIN events e ON r.event_id = e.event_id
    WHERE r.attendee_id = a.attendee_id
      AND e.event_type = 'workshop'
)
AND EXISTS (
    SELECT 1
    FROM registrations r
    JOIN events e ON r.event_id = e.event_id
    WHERE r.attendee_id = a.attendee_id
      AND e.event_type = 'social'
);

WITH latest_feedback AS (
  SELECT 
    ef.event_id,
    ef.rating,
    ROW_NUMBER() OVER (PARTITION BY ef.event_id ORDER BY ef.submitted_at DESC) AS rn
  FROM event_feedback ef
)
SELECT 
  e.event_id,
  e.event_title
FROM events e
JOIN latest_feedback lf ON e.event_id = lf.event_id
WHERE lf.rn = 1 AND lf.rating < 3;

SELECT r.room_id, r.room_name
FROM rooms r
WHERE EXISTS (
    SELECT 1
    FROM events e
    WHERE e.room_id = r.room_id
    AND e.status = 'completed'
)
AND NOT EXISTS (
    SELECT 1
    FROM events e
    WHERE e.room_id = r.room_id
    AND e.status = 'cancelled'
);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
JOIN registrations r ON e.event_id = r.event_id
JOIN attendees a ON r.attendee_id = a.attendee_id
GROUP BY o.organizer_id, o.organizer_name
HAVING COUNT(DISTINCT s.sponsor_type) > COUNT(DISTINCT a.affiliation);

SELECT e.event_id, e.event_title
FROM events e
JOIN registrations r ON e.event_id = r.event_id
GROUP BY e.event_id, e.event_title
HAVING SUM(CASE WHEN r.checked_in = 'yes' THEN 1 ELSE 0 END) < SUM(CASE WHEN r.registration_status = 'waitlisted' THEN 1 ELSE 0 END);

SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM organizers o
    JOIN events e ON o.organizer_id = e.organizer_id
    WHERE o.department_id = d.department_id
      AND NOT EXISTS (
        SELECT 1
        FROM event_feedback ef
        WHERE ef.event_id = e.event_id
      )
);

SELECT DISTINCT a.attendee_id, a.attendee_name
FROM attendees a
WHERE EXISTS (
    SELECT 1
    FROM organizers o
    WHERE NOT EXISTS (
        SELECT 1
        FROM events e
        WHERE e.organizer_id = o.organizer_id
        AND NOT EXISTS (
            SELECT 1
            FROM registrations r
            WHERE r.event_id = e.event_id
            AND r.attendee_id = a.attendee_id
            AND r.checked_in = 'yes'
        )
    )
);

SELECT s.sponsor_id, s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN registrations r ON e.event_id = r.event_id
JOIN attendees a ON r.attendee_id = a.attendee_id
GROUP BY s.sponsor_id, s.sponsor_name
HAVING COUNT(DISTINCT a.class_year) = (SELECT COUNT(DISTINCT class_year) FROM attendees);

SELECT e.event_id, e.event_title
FROM events e
JOIN event_feedback ef ON e.event_id = ef.event_id
GROUP BY e.event_id, e.event_title, e.event_type
HAVING AVG(ef.rating) > (
    SELECT AVG(ef2.rating)
    FROM events e2
    JOIN event_feedback ef2 ON e2.event_id = ef2.event_id
    WHERE e2.event_type = e.event_type
);

SELECT b.building_name
FROM buildings b
JOIN rooms r ON b.building_id = r.building_id
JOIN events e ON r.room_id = e.room_id
GROUP BY b.building_id, b.building_name
HAVING COUNT(DISTINCT r.room_id) = (
    SELECT COUNT(DISTINCT r2.room_id)
    FROM rooms r2
    WHERE r2.building_id = b.building_id
);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
WHERE EXISTS (
    SELECT 1
    FROM events e
    WHERE e.organizer_id = o.organizer_id
      AND e.status = 'cancelled'
)
AND NOT EXISTS (
    SELECT 1
    FROM events e
    WHERE e.organizer_id = o.organizer_id
      AND e.status = 'completed'
);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN rooms ro ON e.room_id = ro.room_id
JOIN buildings b ON ro.building_id = b.building_id
GROUP BY a.attendee_id, a.attendee_name
HAVING COUNT(DISTINCT b.campus_zone) = (SELECT COUNT(DISTINCT campus_zone) FROM buildings);

SELECT e.event_id, e.event_title
FROM events e
JOIN event_feedback ef ON e.event_id = ef.event_id
WHERE ef.rating = 5
  AND NOT EXISTS (
    SELECT 1
    FROM event_sponsors es
    WHERE es.event_id = e.event_id
  )
GROUP BY e.event_id, e.event_title
HAVING COUNT(ef.rating) >= 1;

SELECT r.room_id, r.room_name
FROM rooms r
JOIN events e ON r.room_id = e.room_id
GROUP BY r.room_id, r.room_name
HAVING AVG(e.expected_attendance) > r.capacity;

SELECT d.department_name
FROM departments d
JOIN attendees a ON d.department_id = a.department_id
JOIN event_feedback ef ON a.attendee_id = ef.attendee_id
GROUP BY d.department_id
HAVING COUNT(DISTINCT ef.comment_topic) = (SELECT COUNT(DISTINCT comment_topic) FROM event_feedback);

SELECT DISTINCT "sponsors"."sponsor_name" FROM "event_sponsors" INNER JOIN "events" ON "event_sponsors"."event_id" = "events"."event_id" INNER JOIN "sponsors" ON "event_sponsors"."sponsor_id" = "sponsors"."sponsor_id" WHERE "events"."status" = ?;

SELECT e.event_id, e.event_title
FROM events e
JOIN organizers o ON e.organizer_id = o.organizer_id
JOIN departments d ON o.department_id = d.department_id
JOIN registrations r ON e.event_id = r.event_id
JOIN attendees a ON r.attendee_id = a.attendee_id
WHERE d.department_name != (
    SELECT a2.department_id
    FROM registrations r2
    JOIN attendees a2 ON r2.attendee_id = a2.attendee_id
    WHERE r2.event_id = e.event_id
    GROUP BY a2.department_id
    ORDER BY COUNT(*) DESC
    LIMIT 1
)
GROUP BY e.event_id, e.event_title;

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
GROUP BY a.attendee_id, a.attendee_name
HAVING SUM(CASE WHEN r.checked_in = 'yes' THEN 1 ELSE 0 END) > SUM(CASE WHEN r.registration_status = 'cancelled' THEN 1 ELSE 0 END);

WITH latest_scheduled AS (
  SELECT e.room_id, e.event_date,
         ROW_NUMBER() OVER (PARTITION BY e.room_id ORDER BY e.event_date DESC) AS rn
  FROM events e
  WHERE e.status = 'scheduled'
)
SELECT r.room_id, r.room_name
FROM rooms r
JOIN latest_scheduled ls ON r.room_id = ls.room_id
WHERE ls.rn = 1;

SELECT DISTINCT "events"."event_type", COUNT(*) AS "sponsor_count" FROM "events" LEFT JOIN "event_sponsors" ON "events"."event_id" = "event_sponsors"."event_id" GROUP BY "events"."event_type" HAVING "sponsor_count" >= ?;

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
JOIN rooms r ON e.room_id = r.room_id
JOIN buildings b ON r.building_id = b.building_id
GROUP BY o.organizer_id, o.organizer_name
HAVING COUNT(DISTINCT b.campus_zone) > 1;

SELECT d.department_name
FROM departments d
JOIN organizers o ON d.department_id = o.department_id
JOIN events e ON o.organizer_id = e.organizer_id
JOIN event_feedback ef ON e.event_id = ef.event_id
GROUP BY d.department_id
HAVING AVG(ef.rating) > (SELECT AVG(rating) FROM event_feedback);

SELECT "events"."event_id", "events"."event_title", SUM("event_sponsors"."amount") AS "industry_amount" FROM "event_sponsors" INNER JOIN "events" ON "event_sponsors"."event_id" = "events"."event_id" INNER JOIN "sponsors" ON "event_sponsors"."sponsor_id" = "sponsors"."sponsor_id" WHERE "sponsors"."sponsor_type" = ? GROUP BY "events"."event_id", "events"."event_title";

SELECT DISTINCT "attendees"."attendee_id", "attendees"."attendee_name" FROM "attendees" INNER JOIN "event_feedback" ON "attendees"."attendee_id" = "event_feedback"."attendee_id" INNER JOIN "registrations" ON "attendees"."attendee_id" = "registrations"."attendee_id" WHERE NOT EXISTS (SELECT 1 FROM "event_feedback" WHERE "registrations"."event_id" = "event_feedback"."event_id" AND "registrations"."attendee_id" = "event_feedback"."attendee_id" AND "registrations"."event_id" = "registrations"."event_id" AND "registrations"."attendee_id" = "registrations"."attendee_id");

SELECT "sponsors"."sponsor_id", "sponsors"."sponsor_name", AVG("event_feedback"."rating") AS "avg_rating" FROM "event_sponsors" INNER JOIN "events" ON "event_sponsors"."event_id" = "events"."event_id" INNER JOIN "event_feedback" ON "events"."event_id" = "event_feedback"."event_id" INNER JOIN "sponsors" ON "event_sponsors"."sponsor_id" = "sponsors"."sponsor_id" GROUP BY "sponsors"."sponsor_id", "sponsors"."sponsor_name" HAVING "avg_rating" > ?;

SELECT e.event_id, e.event_title
FROM events e
JOIN event_sponsors es ON e.event_id = es.event_id
GROUP BY e.event_id, e.event_title
HAVING COUNT(es.event_id) > (
    SELECT AVG(sponsor_count)
    FROM (
        SELECT COUNT(*) AS sponsor_count
        FROM event_sponsors
        GROUP BY event_id
    )
);

SELECT b.building_name
FROM buildings b
JOIN rooms r ON b.building_id = r.building_id
JOIN events e ON r.room_id = e.room_id
JOIN organizers o ON e.organizer_id = o.organizer_id
JOIN departments d ON o.department_id = d.department_id
GROUP BY b.building_id, b.building_name
HAVING COUNT(DISTINCT d.department_name) = (SELECT COUNT(*) FROM departments);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
WHERE NOT EXISTS (
    SELECT 1
    FROM events e
    WHERE e.organizer_id = o.organizer_id
      AND e.status = 'cancelled'
);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
WHERE r.checked_in = 'yes'
GROUP BY a.attendee_id, a.attendee_name
HAVING COUNT(DISTINCT s.sponsor_type) = (SELECT COUNT(DISTINCT sponsor_type) FROM sponsors);

SELECT e.event_id, e.event_title
FROM events e
WHERE e.expected_attendance > (
    SELECT COUNT(*)
    FROM registrations r
    WHERE r.event_id = e.event_id
      AND r.checked_in = 'yes'
);

SELECT r.room_id, r.room_name, r.building_id, r.capacity, r.room_type
FROM rooms r
WHERE NOT EXISTS (
    SELECT 1
    FROM registrations reg
    JOIN events e ON reg.event_id = e.event_id
    WHERE e.room_id = r.room_id
);

SELECT d.department_name
FROM departments d
JOIN organizers o ON d.department_id = o.department_id
JOIN events e ON o.organizer_id = e.organizer_id
GROUP BY d.department_id, d.department_name
HAVING SUM(CASE WHEN o.staff_level = 'student' THEN 1 ELSE 0 END) > SUM(CASE WHEN o.staff_level = 'faculty' THEN 1 ELSE 0 END);

SELECT e.event_id, e.event_title
FROM events e
JOIN event_feedback ef ON e.event_id = ef.event_id
JOIN attendees a ON ef.attendee_id = a.attendee_id
JOIN organizers o ON e.organizer_id = o.organizer_id
WHERE EXISTS (
    SELECT 1
    FROM departments d_attendee
    JOIN departments d_organizer ON 1=1
    WHERE a.department_id = d_attendee.department_id
      AND o.department_id = d_organizer.department_id
      AND d_attendee.department_id != d_organizer.department_id
);

SELECT s.sponsor_id, s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN event_feedback ef ON e.event_id = ef.event_id
GROUP BY s.sponsor_id, s.sponsor_name
HAVING MIN(ef.rating) >= 3;

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN rooms rm ON e.room_id = rm.room_id
JOIN buildings b ON rm.building_id = b.building_id
GROUP BY a.attendee_id, a.attendee_name, e.event_type
HAVING COUNT(DISTINCT b.building_id) >= 3;

SELECT r.room_id, r.room_name
FROM rooms r
JOIN events e ON r.room_id = e.room_id
JOIN registrations reg ON e.event_id = reg.event_id
WHERE reg.checked_in = 'yes'
GROUP BY r.room_id, r.room_name
HAVING COUNT(*) > r.capacity;

WITH latest_events AS (
  SELECT 
    e.organizer_id,
    e.event_date,
    e.status,
    ROW_NUMBER() OVER (PARTITION BY e.organizer_id ORDER BY e.event_date DESC) AS rn
  FROM events e
)
SELECT 
  o.organizer_id,
  o.organizer_name
FROM organizers o
JOIN latest_events le ON o.organizer_id = le.organizer_id
WHERE le.rn = 1 AND le.status = 'cancelled';

SELECT e.event_id, e.event_title
FROM events e
WHERE EXISTS (
    SELECT 1
    FROM event_sponsors es
    WHERE es.event_id = e.event_id
)
AND NOT EXISTS (
    SELECT 1
    FROM registrations r
    WHERE r.event_id = e.event_id
);

SELECT d.department_name
FROM departments d
JOIN attendees a ON d.department_id = a.department_id
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
WHERE r.checked_in = 'yes'
GROUP BY d.department_id
HAVING COUNT(DISTINCT e.event_type) = (SELECT COUNT(DISTINCT event_type) FROM events);

SELECT s.sponsor_type
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
GROUP BY s.sponsor_type
HAVING SUM(es.amount) > (
    SELECT AVG(total_amount)
    FROM (
        SELECT SUM(es2.amount) AS total_amount
        FROM sponsors s2
        JOIN event_sponsors es2 ON s2.sponsor_id = es2.sponsor_id
        GROUP BY s2.sponsor_type
    )
);

WITH event_avg AS (
  SELECT 
    e.event_id,
    e.event_title,
    e.event_type,
    AVG(ef.rating) AS avg_rating
  FROM events e
  JOIN event_feedback ef ON e.event_id = ef.event_id
  GROUP BY e.event_id, e.event_title, e.event_type
),
max_avg_per_type AS (
  SELECT 
    event_type,
    MAX(avg_rating) AS max_avg_rating
  FROM event_avg
  GROUP BY event_type
)
SELECT 
  ea.event_id,
  ea.event_title,
  ea.event_type
FROM event_avg ea
JOIN max_avg_per_type mat ON ea.event_type = mat.event_type
WHERE ea.avg_rating = mat.max_avg_rating;

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN departments d ON a.department_id = d.department_id
GROUP BY a.attendee_id, a.attendee_name
HAVING COUNT(DISTINCT e.event_id) = (
    SELECT COUNT(*)
    FROM events e2
    JOIN organizers o ON e2.organizer_id = o.organizer_id
    WHERE o.department_id = a.department_id
);

SELECT DISTINCT "buildings"."building_name" FROM "rooms" INNER JOIN "buildings" ON "rooms"."building_id" = "buildings"."building_id" INNER JOIN "events" ON "rooms"."room_id" = "events"."room_id" WHERE NOT EXISTS (SELECT 1 FROM "rooms" WHERE "buildings"."building_id" = "rooms"."building_id" AND "rooms"."room_id" = "events"."room_id" AND "events"."status" = ?);

SELECT d.department_name
FROM departments d
JOIN attendees a ON d.department_id = a.department_id
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(DISTINCT a.affiliation) = 5
   AND COUNT(DISTINCT CASE WHEN a.affiliation = 'faculty' THEN 1 END) = 1
   AND COUNT(DISTINCT CASE WHEN a.affiliation = 'graduate' THEN 1 END) = 1
   AND COUNT(DISTINCT CASE WHEN a.affiliation = 'guest' THEN 1 END) = 1
   AND COUNT(DISTINCT CASE WHEN a.affiliation = 'staff' THEN 1 END) = 1
   AND COUNT(DISTINCT CASE WHEN a.affiliation = 'undergraduate' THEN 1 END) = 1;

SELECT s.sponsor_id, s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN organizers o ON e.organizer_id = o.organizer_id
JOIN departments d ON o.department_id = d.department_id
GROUP BY s.sponsor_id, s.sponsor_name
HAVING COUNT(DISTINCT d.department_id) > (
    SELECT AVG(dept_count)
    FROM (
        SELECT s2.sponsor_id, COUNT(DISTINCT d2.department_id) AS dept_count
        FROM sponsors s2
        JOIN event_sponsors es2 ON s2.sponsor_id = es2.sponsor_id
        JOIN events e2 ON es2.event_id = e2.event_id
        JOIN organizers o2 ON e2.organizer_id = o2.organizer_id
        JOIN departments d2 ON o2.department_id = d2.department_id
        GROUP BY s2.sponsor_id
    )
);

SELECT e.event_id, e.event_title
FROM events e
JOIN event_feedback ef ON e.event_id = ef.event_id
GROUP BY e.event_id, e.event_title
HAVING MIN(ef.rating) >= 4;

SELECT r.room_id, r.room_name
FROM rooms r
JOIN events e ON r.room_id = e.room_id
GROUP BY r.room_id, r.room_name
HAVING SUM(CASE WHEN e.status = 'cancelled' THEN 1 ELSE 0 END) > SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
JOIN rooms r ON e.room_id = r.room_id
GROUP BY o.organizer_id, o.organizer_name
HAVING COUNT(DISTINCT r.room_type) = (SELECT COUNT(DISTINCT room_type) FROM rooms);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN event_feedback ef ON a.attendee_id = ef.attendee_id
JOIN departments d ON a.department_id = d.department_id
GROUP BY a.attendee_id, a.attendee_name, a.department_id
HAVING AVG(ef.rating) < (
    SELECT AVG(ef2.rating)
    FROM event_feedback ef2
    JOIN attendees a2 ON ef2.attendee_id = a2.attendee_id
    WHERE a2.department_id = a.department_id
);

SELECT DISTINCT e.event_id, e.event_title
FROM events e
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
JOIN registrations r ON e.event_id = r.event_id
JOIN attendees a ON r.attendee_id = a.attendee_id
WHERE s.sponsor_type = 'university'
  AND a.affiliation = 'guest';

SELECT "departments"."department_id", "departments"."department_name" FROM "attendees" INNER JOIN "departments" ON "attendees"."department_id" = "departments"."department_id" INNER JOIN "registrations" ON "attendees"."attendee_id" = "registrations"."attendee_id" INNER JOIN "events" ON "registrations"."event_id" = "events"."event_id" WHERE NOT EXISTS (SELECT 1 FROM "registrations" INNER JOIN "events" ON "registrations"."event_id" = "events"."event_id" WHERE "attendees"."attendee_id" = "registrations"."attendee_id" AND "attendees"."department_id" = "departments"."department_id" AND "events"."status" = ?) GROUP BY "departments"."department_id", "departments"."department_name";

SELECT s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN registrations r ON e.event_id = r.event_id
WHERE r.checked_in = 'yes'
GROUP BY s.sponsor_id, s.sponsor_name
HAVING COUNT(r.registration_id) > SUM(e.expected_attendance);

SELECT e.event_id, e.event_title
FROM events e
JOIN event_feedback ef ON e.event_id = ef.event_id
WHERE ef.submitted_at > e.event_date
  AND ef.rating = (
    SELECT MAX(ef2.rating)
    FROM event_feedback ef2
    WHERE ef2.event_id = e.event_id
  );

SELECT DISTINCT a1.attendee_id, a1.attendee_name
FROM attendees a1
JOIN registrations r1 ON a1.attendee_id = r1.attendee_id
JOIN events e1 ON r1.event_id = e1.event_id
JOIN registrations r2 ON a1.attendee_id = r2.attendee_id
JOIN events e2 ON r2.event_id = e2.event_id
WHERE r1.registration_status = 'waitlisted'
  AND r2.checked_in = 'yes'
  AND e1.event_type = e2.event_type
  AND e1.event_id != e2.event_id;

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
JOIN event_feedback ef ON e.event_id = ef.event_id
GROUP BY o.organizer_id, o.organizer_name
HAVING COUNT(DISTINCT ef.comment_topic) = (SELECT COUNT(DISTINCT comment_topic) FROM event_feedback);

SELECT r.room_id, r.room_name
FROM rooms r
JOIN events e ON r.room_id = e.room_id
JOIN event_feedback ef ON e.event_id = ef.event_id
JOIN buildings b ON r.building_id = b.building_id
GROUP BY r.room_id, r.room_name
HAVING AVG(ef.rating) > (
    SELECT AVG(ef2.rating)
    FROM events e2
    JOIN event_feedback ef2 ON e2.event_id = ef2.event_id
    JOIN rooms r2 ON e2.room_id = r2.room_id
    WHERE r2.building_id = r.building_id
);

SELECT d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM organizers o
    JOIN events e ON o.organizer_id = e.organizer_id
    JOIN event_feedback ef ON e.event_id = ef.event_id
    WHERE o.department_id = d.department_id
      AND ef.rating < 4
);

SELECT "sponsors"."sponsor_id", "sponsors"."sponsor_name", COUNT(*) AS "total_registrations", COUNT("registrations"."checked_in") AS "checked_in_count" FROM "event_sponsors" INNER JOIN "events" ON "event_sponsors"."event_id" = "events"."event_id" INNER JOIN "registrations" ON "events"."event_id" = "registrations"."event_id" INNER JOIN "sponsors" ON "event_sponsors"."sponsor_id" = "sponsors"."sponsor_id" GROUP BY "sponsors"."sponsor_id", "sponsors"."sponsor_name" HAVING "total_registrations" = "checked_in_count";

SELECT e.event_id, e.event_title
FROM events e
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
WHERE es.amount > (
    SELECT AVG(es2.amount)
    FROM event_sponsors es2
    JOIN sponsors s2 ON es2.sponsor_id = s2.sponsor_id
    WHERE s2.sponsor_type = s.sponsor_type
);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN organizers o ON e.organizer_id = o.organizer_id
GROUP BY a.attendee_id, a.attendee_name
HAVING COUNT(DISTINCT o.staff_level) = (SELECT COUNT(DISTINCT staff_level) FROM organizers);

SELECT "buildings"."building_id", "buildings"."building_name", COUNT("rooms"."room_type") AS "distinct_room_types_in_building", COUNT("events"."event_id") AS "events_per_room_type" FROM "rooms" INNER JOIN "buildings" ON "rooms"."building_id" = "buildings"."building_id" INNER JOIN "events" ON "rooms"."room_id" = "events"."room_id" GROUP BY "buildings"."building_id", "buildings"."building_name" HAVING "events_per_room_type" >= ?;

SELECT e.event_id, e.event_title
FROM events e
JOIN event_feedback ef ON e.event_id = ef.event_id
JOIN registrations r ON e.event_id = r.event_id
GROUP BY e.event_id, e.event_title
HAVING COUNT(ef.feedback_id) > SUM(CASE WHEN r.checked_in = 'yes' THEN 1 ELSE 0 END);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
WHERE NOT EXISTS (
    SELECT 1
    FROM events e
    JOIN registrations r ON e.event_id = r.event_id
    WHERE e.organizer_id = o.organizer_id
      AND r.registration_status = 'waitlisted'
);

SELECT d.department_name
FROM departments d
JOIN attendees a ON d.department_id = a.department_id
JOIN event_feedback ef ON a.attendee_id = ef.attendee_id
GROUP BY d.department_id
HAVING AVG(ef.rating) > (SELECT AVG(rating) FROM event_feedback);

SELECT s.sponsor_id, s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN organizers o ON e.organizer_id = o.organizer_id
JOIN departments d ON o.department_id = d.department_id
GROUP BY s.sponsor_id, s.sponsor_name
HAVING COUNT(DISTINCT d.college) = (
    SELECT COUNT(DISTINCT d2.college)
    FROM organizers o2
    JOIN departments d2 ON o2.department_id = d2.department_id
);

WITH event_checked_in_counts AS (
    SELECT 
        e.event_id,
        e.event_title,
        r.room_type,
        COUNT(CASE WHEN reg.checked_in = 'yes' THEN 1 END) AS checked_in_count
    FROM events e
    JOIN rooms r ON e.room_id = r.room_id
    JOIN registrations reg ON e.event_id = reg.event_id
    GROUP BY e.event_id, e.event_title, r.room_type
),
room_type_averages AS (
    SELECT 
        room_type,
        AVG(checked_in_count) AS avg_checked_in
    FROM event_checked_in_counts
    GROUP BY room_type
)
SELECT 
    ecc.event_id,
    ecc.event_title
FROM event_checked_in_counts ecc
JOIN room_type_averages rta ON ecc.room_type = rta.room_type
WHERE ecc.checked_in_count > rta.avg_checked_in;

SELECT r.room_id, r.room_name
FROM rooms r
JOIN events e ON r.room_id = e.room_id
JOIN organizers o ON e.organizer_id = o.organizer_id
JOIN departments d ON o.department_id = d.department_id
GROUP BY r.room_id, r.room_name
HAVING COUNT(DISTINCT d.department_id) > 3;

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN rooms ro ON e.room_id = ro.room_id
JOIN buildings b ON ro.building_id = b.building_id
WHERE r.checked_in = 'yes'
GROUP BY a.attendee_id, a.attendee_name
HAVING COUNT(DISTINCT b.campus_zone) = (SELECT COUNT(DISTINCT campus_zone) FROM buildings);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
WHERE e.status = 'scheduled'
AND NOT EXISTS (
    SELECT 1
    FROM event_sponsors es
    WHERE es.event_id = e.event_id
);

SELECT d.department_name
FROM departments d
JOIN attendees a ON d.department_id = a.department_id
JOIN registrations r ON a.attendee_id = r.attendee_id
GROUP BY d.department_id
HAVING COUNT(DISTINCT a.attendee_id) = (
    SELECT COUNT(DISTINCT a2.attendee_id)
    FROM attendees a2
    WHERE a2.department_id = d.department_id
);

SELECT e.event_id, e.event_title
FROM events e
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
WHERE s.sponsor_type IN ('government', 'industry')
GROUP BY e.event_id, e.event_title
HAVING COUNT(DISTINCT s.sponsor_type) = 2;

SELECT DISTINCT s.sponsor_id, s.sponsor_name
FROM sponsors s
JOIN event_sponsors es ON s.sponsor_id = es.sponsor_id
JOIN events e ON es.event_id = e.event_id
JOIN registrations r ON e.event_id = r.event_id
WHERE r.registration_status = 'cancelled'
  AND r.registration_id = (
    SELECT MAX(r2.registration_id)
    FROM registrations r2
    WHERE r2.event_id = e.event_id
  );

SELECT r.room_id, r.room_name
FROM rooms r
WHERE NOT EXISTS (
  SELECT 1
  FROM events e
  WHERE e.room_id = r.room_id
    AND NOT EXISTS (
      SELECT 1
      FROM registrations reg
      WHERE reg.event_id = e.event_id
        AND reg.checked_in = 'yes'
    )
);

SELECT a.attendee_id, a.attendee_name
FROM attendees a
JOIN registrations r ON a.attendee_id = r.attendee_id
JOIN events e ON r.event_id = e.event_id
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
GROUP BY a.attendee_id, a.attendee_name
HAVING COUNT(DISTINCT s.sponsor_type) = (SELECT COUNT(DISTINCT sponsor_type) FROM sponsors);

SELECT d.department_name
FROM departments d
JOIN organizers o ON d.department_id = o.department_id
JOIN events e ON o.organizer_id = e.organizer_id
JOIN event_sponsors es ON e.event_id = es.event_id
GROUP BY d.department_id, d.department_name
HAVING SUM(es.amount) > (
    SELECT AVG(dept_total)
    FROM (
        SELECT d2.department_id, SUM(es2.amount) AS dept_total
        FROM departments d2
        JOIN organizers o2 ON d2.department_id = o2.department_id
        JOIN events e2 ON o2.organizer_id = e2.organizer_id
        JOIN event_sponsors es2 ON e2.event_id = es2.event_id
        GROUP BY d2.department_id
    )
);

SELECT e.event_id, e.event_title
FROM events e
JOIN registrations r ON e.event_id = r.event_id
JOIN attendees a ON r.attendee_id = a.attendee_id
JOIN departments d ON a.department_id = d.department_id
JOIN event_sponsors es ON e.event_id = es.event_id
JOIN sponsors s ON es.sponsor_id = s.sponsor_id
GROUP BY e.event_id, e.event_title
HAVING COUNT(DISTINCT d.department_id) > COUNT(DISTINCT s.sponsor_id);

SELECT DISTINCT "sponsors"."sponsor_name" FROM "event_sponsors" INNER JOIN "events" ON "event_sponsors"."event_id" = "events"."event_id" INNER JOIN "sponsors" ON "event_sponsors"."sponsor_id" = "sponsors"."sponsor_id" WHERE NOT EXISTS (SELECT 1 FROM "events" WHERE "event_sponsors"."event_id" = "events"."event_id" AND "event_sponsors"."sponsor_id" = "sponsors"."sponsor_id" AND "events"."status" = ?);

SELECT o.organizer_id, o.organizer_name
FROM organizers o
JOIN events e ON o.organizer_id = e.organizer_id
GROUP BY o.organizer_id, o.organizer_name
HAVING SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) > SUM(CASE WHEN e.status = 'scheduled' THEN 1 ELSE 0 END);

SELECT b.building_name
FROM buildings b
JOIN rooms r ON b.building_id = r.building_id
JOIN events e ON r.room_id = e.room_id
GROUP BY b.building_id, b.building_name
HAVING AVG(r.capacity) > (
    SELECT AVG(e2.expected_attendance)
    FROM events e2
    JOIN rooms r2 ON e2.room_id = r2.room_id
    WHERE r2.building_id = b.building_id
);

WITH ranked_feedback AS (
    SELECT
        ef.attendee_id,
        ef.event_id,
        ef.rating,
        ROW_NUMBER() OVER (PARTITION BY ef.attendee_id ORDER BY ef.submitted_at DESC) AS rn
    FROM event_feedback ef
)
SELECT
    a.attendee_id,
    a.attendee_name
FROM attendees a
JOIN ranked_feedback rf ON a.attendee_id = rf.attendee_id
JOIN registrations r ON rf.event_id = r.event_id AND a.attendee_id = r.attendee_id
JOIN events e ON rf.event_id = e.event_id
WHERE rf.rn = 1
  AND r.checked_in = 'yes';

SELECT e.event_id, e.event_title
FROM events e
JOIN registrations r ON e.event_id = r.event_id
JOIN event_sponsors es ON e.event_id = es.event_id
GROUP BY e.event_id, e.event_title
HAVING SUM(CASE WHEN r.checked_in = 'yes' THEN 1 ELSE 0 END) = 0
   AND COUNT(es.event_sponsor_id) >= 1;

SELECT d.department_name
FROM departments d
JOIN organizers o ON d.department_id = o.department_id
JOIN events e ON o.organizer_id = e.organizer_id
WHERE o.staff_level IN ('staff', 'faculty')
GROUP BY d.department_id
HAVING COUNT(DISTINCT o.organizer_id) = (
    SELECT COUNT(*)
    FROM organizers o2
    WHERE o2.department_id = d.department_id
)
AND NOT EXISTS (
    SELECT 1
    FROM organizers o3
    WHERE o3.department_id = d.department_id
    AND o3.staff_level NOT IN ('staff', 'faculty')
);


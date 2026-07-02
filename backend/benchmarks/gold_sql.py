"""
benchmarks/gold_sql.py

Gold SQL for the three benchmark question sets. Each entry pins the question
text (so index drift is detected) and one reference SQLite query whose result
set defines semantic correctness. Where a question is ambiguous, the most
literal reading was chosen; adjust an entry here to re-grade — the evaluator
(benchmarks/gold_eval.py) compares result SETS, not SQL text, so gold style
never has to match generated style.

Benchmarks:
  petfood_50  database_id 28
  clinic_20   database_id 29
  cyber_20    database_id 30 (schema-only DB -> graded on a seeded eval copy)
"""

__all__ = ["GOLD", "get_gold"]


def _e(question, sql, note=None):
    return {"question": question, "sql": sql.strip(), "note": note}


PETFOOD_50 = [
    _e("List all owners in Moscow, Idaho who have the lowest annual income among Moscow owners, and among those lowest-income owners return only the owner or owners with the largest number of pets.",
       """
WITH m AS (SELECT * FROM owners WHERE city='Moscow' AND state='Idaho'),
low AS (SELECT * FROM m WHERE annual_income=(SELECT MIN(annual_income) FROM m)),
cnt AS (SELECT low.owner_id, low.owner_name, COUNT(p.pet_id) AS n
        FROM low LEFT JOIN pets p ON p.owner_id=low.owner_id
        GROUP BY low.owner_id, low.owner_name)
SELECT owner_id, owner_name FROM cnt WHERE n=(SELECT MAX(n) FROM cnt)
"""),
    _e("List all pet owners and their pets who do not live at the same address, using an outer join so owners without pets are still visible.",
       """
SELECT o.owner_name, p.pet_name
FROM owners o LEFT JOIN pets p
  ON p.owner_id=o.owner_id AND p.pet_address<>o.household_address
""", "address = owners.household_address vs pets.pet_address"),
    _e("List pets who never ate any food whose food type and flavor match a food type and flavor they actively love.",
       """
SELECT p.pet_id, p.pet_name FROM pets p
WHERE NOT EXISTS (
  SELECT 1 FROM feeding_history fh
  JOIN foods f ON f.food_id=fh.food_id
  JOIN pet_likes l ON l.pet_id=p.pet_id AND l.active='yes'
       AND l.food_type=f.food_type AND l.flavor=f.flavor
  WHERE fh.pet_id=p.pet_id)
"""),
    _e("List the brands and food names each pet could potentially eat if their owner has bought that food type for the pet's species and the pet has no allergy note for that flavor.",
       """
SELECT DISTINCT p.pet_name, f.brand, f.food_name
FROM pets p JOIN foods f ON f.species_target=p.species
WHERE EXISTS (SELECT 1 FROM purchases pu JOIN foods f2 ON f2.food_id=pu.food_id
              WHERE pu.owner_id=p.owner_id AND f2.food_type=f.food_type
                AND f2.species_target=p.species)
AND NOT EXISTS (SELECT 1 FROM pet_likes l WHERE l.pet_id=p.pet_id
                AND l.flavor=f.flavor AND l.allergy_note<>'none')
"""),
    _e("List the highest priced food for each brand without using GROUP BY; use a correlated subquery or anti-join style condition.",
       """
SELECT f.brand, f.food_name, f.price FROM foods f
WHERE NOT EXISTS (SELECT 1 FROM foods g WHERE g.brand=f.brand AND g.price>f.price)
"""),
    _e("Find owners who bought food for a species they do not own, and list the mismatched food species beside the species of their pets.",
       """
SELECT DISTINCT o.owner_name, f.species_target, p.species
FROM owners o
JOIN purchases pu ON pu.owner_id=o.owner_id
JOIN foods f ON f.food_id=pu.food_id
JOIN pets p ON p.owner_id=o.owner_id
WHERE NOT EXISTS (SELECT 1 FROM pets p2 WHERE p2.owner_id=o.owner_id
                  AND p2.species=f.species_target)
"""),
    _e("For every owner, list the pet that ate the lowest percentage of served food, but include owners whose pets have no feeding history.",
       """
WITH pa AS (SELECT p.owner_id, p.pet_id, p.pet_name, AVG(fh.ate_amount_percent) AS avg_pct
            FROM pets p JOIN feeding_history fh ON fh.pet_id=p.pet_id
            GROUP BY p.owner_id, p.pet_id, p.pet_name),
mn AS (SELECT owner_id, MIN(avg_pct) AS m FROM pa GROUP BY owner_id)
SELECT o.owner_name, pa.pet_name
FROM owners o
LEFT JOIN mn ON mn.owner_id=o.owner_id
LEFT JOIN pa ON pa.owner_id=o.owner_id AND pa.avg_pct=mn.m
"""),
    _e("List pets whose owners bought a food brand that matches the pet's preferred brand, but the pet was never actually fed any food from that brand.",
       """
SELECT DISTINCT p.pet_id, p.pet_name
FROM pets p
JOIN pet_likes l ON l.pet_id=p.pet_id
JOIN purchases pu ON pu.owner_id=p.owner_id
JOIN foods f ON f.food_id=pu.food_id AND f.brand=l.preferred_brand
WHERE NOT EXISTS (SELECT 1 FROM feeding_history fh JOIN foods f2 ON f2.food_id=fh.food_id
                  WHERE fh.pet_id=p.pet_id AND f2.brand=l.preferred_brand)
"""),
    _e("Find food brands where every purchased food item from that brand was bought by owners outside Moscow, Idaho.",
       """
SELECT DISTINCT f.brand FROM foods f JOIN purchases pu ON pu.food_id=f.food_id
WHERE f.brand NOT IN (
  SELECT f2.brand FROM foods f2
  JOIN purchases pu2 ON pu2.food_id=f2.food_id
  JOIN owners o ON o.owner_id=pu2.owner_id
  WHERE o.city='Moscow' AND o.state='Idaho')
"""),
    _e("List owners whose total spending is above the average spending of owners in their own city, without using GROUP BY in the outer query.",
       """
WITH t AS (SELECT o.owner_id, o.owner_name, o.city, SUM(pu.total_amount) AS total
           FROM owners o JOIN purchases pu ON pu.owner_id=o.owner_id
           GROUP BY o.owner_id, o.owner_name, o.city)
SELECT owner_id, owner_name FROM t
WHERE total > (SELECT AVG(t2.total) FROM t t2 WHERE t2.city=t.city)
"""),
    _e("Find pets that have at least two loved food profiles but were fed fewer than two distinct food brands.",
       """
SELECT p.pet_id, p.pet_name FROM pets p
WHERE (SELECT COUNT(*) FROM pet_likes l WHERE l.pet_id=p.pet_id) >= 2
AND (SELECT COUNT(DISTINCT f.brand) FROM feeding_history fh
     JOIN foods f ON f.food_id=fh.food_id WHERE fh.pet_id=p.pet_id) < 2
"""),
    _e("List foods that were purchased by an owner but are incompatible with every pet owned by that owner based on species_target.",
       """
SELECT DISTINCT o.owner_name, f.food_name
FROM owners o
JOIN purchases pu ON pu.owner_id=o.owner_id
JOIN foods f ON f.food_id=pu.food_id
WHERE EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id)
AND NOT EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id
                AND p.species=f.species_target)
"""),
    _e("For each species, list the most expensive food that has been purchased at least once and has stock below the median stock for that species.",
       """
WITH ranked AS (
  SELECT f.*, ROW_NUMBER() OVER (PARTITION BY species_target ORDER BY stock_quantity) AS rn,
         COUNT(*) OVER (PARTITION BY species_target) AS cnt
  FROM foods f),
med AS (SELECT species_target, stock_quantity AS m FROM ranked WHERE rn=(cnt+1)/2),
cand AS (SELECT f.* FROM foods f JOIN med ON med.species_target=f.species_target
         WHERE f.stock_quantity < med.m
         AND EXISTS (SELECT 1 FROM purchases pu WHERE pu.food_id=f.food_id))
SELECT c.species_target, c.food_name, c.price FROM cand c
WHERE c.price=(SELECT MAX(c2.price) FROM cand c2 WHERE c2.species_target=c.species_target)
""", "median = lower median of foods.stock_quantity per species_target"),
    _e("List owners who live in the same city as a store where they bought food, but whose pets were fed that food in a different location than home.",
       """
SELECT DISTINCT o.owner_id, o.owner_name
FROM owners o
JOIN purchases pu ON pu.owner_id=o.owner_id AND pu.store_city=o.city
JOIN feeding_history fh ON fh.owner_id=o.owner_id AND fh.food_id=pu.food_id
     AND fh.location<>'home'
"""),
    _e("Find pets who have been fed only foods with allergen_flag = 'no', but have at least one liked profile with allergy_note not equal to 'none'.",
       """
SELECT p.pet_id, p.pet_name FROM pets p
WHERE EXISTS (SELECT 1 FROM feeding_history fh WHERE fh.pet_id=p.pet_id)
AND NOT EXISTS (SELECT 1 FROM feeding_history fh JOIN foods f ON f.food_id=fh.food_id
                WHERE fh.pet_id=p.pet_id AND f.allergen_flag<>'no')
AND EXISTS (SELECT 1 FROM pet_likes l WHERE l.pet_id=p.pet_id AND l.allergy_note<>'none')
"""),
    _e("List pairs of pets owned by the same owner where both love the same flavor but have never been fed the same food_id.",
       """
SELECT DISTINCT p1.pet_name, p2.pet_name
FROM pets p1
JOIN pets p2 ON p1.owner_id=p2.owner_id AND p1.pet_id<p2.pet_id
JOIN pet_likes l1 ON l1.pet_id=p1.pet_id
JOIN pet_likes l2 ON l2.pet_id=p2.pet_id AND l2.flavor=l1.flavor
WHERE NOT EXISTS (SELECT 1 FROM feeding_history a JOIN feeding_history b
                  ON a.food_id=b.food_id
                  WHERE a.pet_id=p1.pet_id AND b.pet_id=p2.pet_id)
"""),
    _e("Find owners whose pets have consumed foods from more brands than the owner has directly purchased.",
       """
SELECT o.owner_id, o.owner_name FROM owners o
WHERE (SELECT COUNT(DISTINCT f.brand) FROM feeding_history fh
       JOIN foods f ON f.food_id=fh.food_id
       JOIN pets p ON p.pet_id=fh.pet_id
       WHERE p.owner_id=o.owner_id)
    > (SELECT COUNT(DISTINCT f2.brand) FROM purchases pu
       JOIN foods f2 ON f2.food_id=pu.food_id WHERE pu.owner_id=o.owner_id)
"""),
    _e("List foods that are the cheapest within their food_type but are still more expensive than the average food purchased by Moscow owners.",
       """
SELECT f.food_name, f.food_type, f.price FROM foods f
WHERE f.price=(SELECT MIN(g.price) FROM foods g WHERE g.food_type=f.food_type)
AND f.price > (SELECT AVG(f2.price) FROM purchases pu
               JOIN owners o ON o.owner_id=pu.owner_id
               JOIN foods f2 ON f2.food_id=pu.food_id
               WHERE o.city='Moscow')
"""),
    _e("Find pets that love a brand but whose owner bought a different brand with the same food_type and flavor.",
       """
SELECT DISTINCT p.pet_id, p.pet_name
FROM pets p
JOIN pet_likes l ON l.pet_id=p.pet_id
JOIN purchases pu ON pu.owner_id=p.owner_id
JOIN foods f ON f.food_id=pu.food_id AND f.brand<>l.preferred_brand
     AND f.food_type=l.food_type AND f.flavor=l.flavor
"""),
    _e("List owners who bought the highest total quantity of food for each city, including ties.",
       """
WITH t AS (SELECT o.owner_id, o.owner_name, o.city, SUM(pu.quantity) AS q
           FROM owners o JOIN purchases pu ON pu.owner_id=o.owner_id
           GROUP BY o.owner_id, o.owner_name, o.city)
SELECT city, owner_name FROM t
WHERE q=(SELECT MAX(t2.q) FROM t t2 WHERE t2.city=t.city)
"""),
    _e("Find owners who have at least one pet with no matching active like record and at least one purchase of a food targeted to that pet's species.",
       """
SELECT DISTINCT o.owner_id, o.owner_name
FROM owners o JOIN pets p ON p.owner_id=o.owner_id
WHERE NOT EXISTS (SELECT 1 FROM pet_likes l WHERE l.pet_id=p.pet_id AND l.active='yes')
AND EXISTS (SELECT 1 FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
            WHERE pu.owner_id=o.owner_id AND f.species_target=p.species)
"""),
    _e("List pet-food pairs where the pet loves the food's flavor and food_type, the food matches species_target, and the owner has never bought that exact food.",
       """
SELECT DISTINCT p.pet_name, f.food_name
FROM pets p
JOIN pet_likes l ON l.pet_id=p.pet_id
JOIN foods f ON f.flavor=l.flavor AND f.food_type=l.food_type
     AND f.species_target=p.species
WHERE NOT EXISTS (SELECT 1 FROM purchases pu WHERE pu.owner_id=p.owner_id
                  AND pu.food_id=f.food_id)
"""),
    _e("Find brands that have food for all species represented in the pets table.",
       """
SELECT f.brand FROM foods f
GROUP BY f.brand
HAVING COUNT(DISTINCT CASE WHEN f.species_target IN (SELECT DISTINCT species FROM pets)
                           THEN f.species_target END)
     = (SELECT COUNT(DISTINCT species) FROM pets)
"""),
    _e("List owners whose pets were fed more total servings than the total quantity of food the owner purchased.",
       """
SELECT o.owner_id, o.owner_name FROM owners o
WHERE (SELECT COALESCE(SUM(fh.servings),0) FROM feeding_history fh
       JOIN pets p ON p.pet_id=fh.pet_id WHERE p.owner_id=o.owner_id)
    > (SELECT COALESCE(SUM(pu.quantity),0) FROM purchases pu
       WHERE pu.owner_id=o.owner_id)
"""),
    _e("Find pets whose favorite brand is the same as the most expensive brand their owner has purchased.",
       """
SELECT DISTINCT p.pet_id, p.pet_name
FROM pets p JOIN pet_likes l ON l.pet_id=p.pet_id
WHERE l.preferred_brand IN (
  SELECT f.brand FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
  WHERE pu.owner_id=p.owner_id
  AND f.price=(SELECT MAX(f2.price) FROM purchases pu2
               JOIN foods f2 ON f2.food_id=pu2.food_id
               WHERE pu2.owner_id=p.owner_id))
"""),
    _e("List foods never purchased but still fed to at least one pet, with the pet and owner names.",
       """
SELECT DISTINCT f.food_name, p.pet_name, o.owner_name
FROM foods f
JOIN feeding_history fh ON fh.food_id=f.food_id
JOIN pets p ON p.pet_id=fh.pet_id
JOIN owners o ON o.owner_id=p.owner_id
WHERE NOT EXISTS (SELECT 1 FROM purchases pu WHERE pu.food_id=f.food_id)
"""),
    _e("Find owners where every pet they own has been fed at least one food matching that pet's species.",
       """
SELECT o.owner_id, o.owner_name FROM owners o
WHERE EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id)
AND NOT EXISTS (
  SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id
  AND NOT EXISTS (SELECT 1 FROM feeding_history fh
                  JOIN foods f ON f.food_id=fh.food_id
                  WHERE fh.pet_id=p.pet_id AND f.species_target=p.species))
"""),
    _e("List pets whose owner bought food after the pet's adoption date, but the pet was fed before the owner's first purchase date.",
       """
SELECT DISTINCT p.pet_id, p.pet_name FROM pets p
WHERE EXISTS (SELECT 1 FROM purchases pu WHERE pu.owner_id=p.owner_id
              AND pu.purchase_date > p.adoption_date)
AND EXISTS (SELECT 1 FROM feeding_history fh WHERE fh.pet_id=p.pet_id
            AND fh.feed_date < (SELECT MIN(pu2.purchase_date) FROM purchases pu2
                                WHERE pu2.owner_id=p.owner_id))
"""),
    _e("Find the second highest priced food within each brand without using LIMIT in a subquery.",
       """
SELECT f.brand, f.food_name, f.price FROM foods f
WHERE (SELECT COUNT(DISTINCT g.price) FROM foods g
       WHERE g.brand=f.brand AND g.price>f.price) = 1
"""),
    _e("List cities where every owner has either no pets or has bought at least one food item.",
       """
SELECT DISTINCT o.city FROM owners o
WHERE NOT EXISTS (
  SELECT 1 FROM owners o2 WHERE o2.city=o.city
  AND EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o2.owner_id)
  AND NOT EXISTS (SELECT 1 FROM purchases pu WHERE pu.owner_id=o2.owner_id))
"""),
    _e("Find owners with pets at different addresses and whose highest single purchase total is below the average purchase total for their city.",
       """
SELECT DISTINCT o.owner_id, o.owner_name FROM owners o
WHERE EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id
              AND p.pet_address<>o.household_address)
AND (SELECT MAX(pu.total_amount) FROM purchases pu WHERE pu.owner_id=o.owner_id)
  < (SELECT AVG(pu2.total_amount) FROM purchases pu2
     JOIN owners o2 ON o2.owner_id=pu2.owner_id WHERE o2.city=o.city)
"""),
    _e("List foods that are loved by at least one pet by flavor/type but rejected in feeding history by another pet with notes = 'refused'.",
       """
SELECT DISTINCT f.food_id, f.food_name
FROM foods f
JOIN pet_likes l ON l.flavor=f.flavor AND l.food_type=f.food_type
JOIN feeding_history fh ON fh.food_id=f.food_id AND fh.notes='refused'
     AND fh.pet_id<>l.pet_id
"""),
    _e("Find pets whose loved flavor appears in foods bought by their owner, but only in foods targeted to a different species.",
       """
SELECT DISTINCT p.pet_id, p.pet_name
FROM pets p JOIN pet_likes l ON l.pet_id=p.pet_id
WHERE EXISTS (SELECT 1 FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
              WHERE pu.owner_id=p.owner_id AND f.flavor=l.flavor)
AND NOT EXISTS (SELECT 1 FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
                WHERE pu.owner_id=p.owner_id AND f.flavor=l.flavor
                AND f.species_target=p.species)
"""),
    _e("List owners who bought food from at least three brands and whose pets were fed food from fewer brands than that.",
       """
WITH ob AS (SELECT pu.owner_id, COUNT(DISTINCT f.brand) AS nb
            FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
            GROUP BY pu.owner_id),
fb AS (SELECT p.owner_id, COUNT(DISTINCT f.brand) AS nb
       FROM feeding_history fh
       JOIN pets p ON p.pet_id=fh.pet_id
       JOIN foods f ON f.food_id=fh.food_id
       GROUP BY p.owner_id)
SELECT o.owner_id, o.owner_name
FROM owners o JOIN ob ON ob.owner_id=o.owner_id
WHERE ob.nb>=3 AND COALESCE((SELECT nb FROM fb WHERE fb.owner_id=o.owner_id),0) < ob.nb
"""),
    _e("Find foods whose price is higher than every other food with the same food_type and species_target.",
       """
SELECT f.food_id, f.food_name FROM foods f
WHERE NOT EXISTS (SELECT 1 FROM foods g
                  WHERE g.food_type=f.food_type AND g.species_target=f.species_target
                  AND g.food_id<>f.food_id AND g.price>=f.price)
"""),
    _e("List pet owners whose pets' feeding history includes a food the owner never purchased.",
       """
SELECT DISTINCT o.owner_id, o.owner_name
FROM owners o
JOIN pets p ON p.owner_id=o.owner_id
JOIN feeding_history fh ON fh.pet_id=p.pet_id
WHERE NOT EXISTS (SELECT 1 FROM purchases pu WHERE pu.owner_id=o.owner_id
                  AND pu.food_id=fh.food_id)
"""),
    _e("Find active liked profiles where no available food matches preferred_brand, food_type, flavor, and pet species.",
       """
SELECT l.like_id, l.pet_id, l.preferred_brand, l.food_type, l.flavor
FROM pet_likes l JOIN pets p ON p.pet_id=l.pet_id
WHERE l.active='yes'
AND NOT EXISTS (SELECT 1 FROM foods f
                WHERE f.brand=l.preferred_brand AND f.food_type=l.food_type
                AND f.flavor=l.flavor AND f.species_target=p.species)
"""),
    _e("List owners whose pets have eaten all food_types that the owner has purchased.",
       """
SELECT o.owner_id, o.owner_name FROM owners o
WHERE EXISTS (SELECT 1 FROM purchases pu WHERE pu.owner_id=o.owner_id)
AND NOT EXISTS (
  SELECT 1 FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
  WHERE pu.owner_id=o.owner_id
  AND NOT EXISTS (SELECT 1 FROM feeding_history fh
                  JOIN pets p ON p.pet_id=fh.pet_id
                  JOIN foods f2 ON f2.food_id=fh.food_id
                  WHERE p.owner_id=o.owner_id AND f2.food_type=f.food_type))
"""),
    _e("Find pets with no feeding history but whose owner has purchased at least one food compatible with the pet species.",
       """
SELECT p.pet_id, p.pet_name FROM pets p
WHERE NOT EXISTS (SELECT 1 FROM feeding_history fh WHERE fh.pet_id=p.pet_id)
AND EXISTS (SELECT 1 FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
            WHERE pu.owner_id=p.owner_id AND f.species_target=p.species)
"""),
    _e("List the owner, pet, and food for cases where the pet ate less than 50 percent of a food that it should love by matching type and flavor.",
       """
SELECT DISTINCT o.owner_name, p.pet_name, f.food_name
FROM feeding_history fh
JOIN pets p ON p.pet_id=fh.pet_id
JOIN owners o ON o.owner_id=p.owner_id
JOIN foods f ON f.food_id=fh.food_id
JOIN pet_likes l ON l.pet_id=p.pet_id AND l.food_type=f.food_type AND l.flavor=f.flavor
WHERE fh.ate_amount_percent < 50
"""),
    _e("Find brands that are purchased by the lowest-income Moscow owners but are not purchased by any highest-income Moscow owners.",
       """
WITH m AS (SELECT * FROM owners WHERE city='Moscow' AND state='Idaho'),
lo AS (SELECT owner_id FROM m WHERE annual_income=(SELECT MIN(annual_income) FROM m)),
hi AS (SELECT owner_id FROM m WHERE annual_income=(SELECT MAX(annual_income) FROM m))
SELECT DISTINCT f.brand
FROM purchases pu JOIN foods f ON f.food_id=pu.food_id
WHERE pu.owner_id IN (SELECT owner_id FROM lo)
AND f.brand NOT IN (SELECT f2.brand FROM purchases pu2
                    JOIN foods f2 ON f2.food_id=pu2.food_id
                    WHERE pu2.owner_id IN (SELECT owner_id FROM hi))
"""),
    _e("List owners for whom the most expensive purchased food is incompatible with every pet they own.",
       """
SELECT DISTINCT o.owner_id, o.owner_name
FROM owners o
JOIN purchases pu ON pu.owner_id=o.owner_id
JOIN foods f ON f.food_id=pu.food_id
WHERE f.price=(SELECT MAX(f2.price) FROM purchases pu2
               JOIN foods f2 ON f2.food_id=pu2.food_id WHERE pu2.owner_id=o.owner_id)
AND EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id)
AND NOT EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id
                AND p.species=f.species_target)
"""),
    _e("Find pet pairs from different owners who live at the same pet address and love the same preferred brand.",
       """
SELECT DISTINCT p1.pet_name, p2.pet_name
FROM pets p1
JOIN pets p2 ON p1.pet_id<p2.pet_id AND p1.owner_id<>p2.owner_id
     AND p1.pet_address=p2.pet_address
JOIN pet_likes l1 ON l1.pet_id=p1.pet_id
JOIN pet_likes l2 ON l2.pet_id=p2.pet_id AND l2.preferred_brand=l1.preferred_brand
"""),
    _e("List foods that could be recommended to a pet because the pet loves the type/flavor and another pet of the same species ate it above 90 percent.",
       """
SELECT DISTINCT p.pet_name, f.food_name
FROM pets p
JOIN pet_likes l ON l.pet_id=p.pet_id
JOIN foods f ON f.food_type=l.food_type AND f.flavor=l.flavor
WHERE EXISTS (SELECT 1 FROM feeding_history fh
              JOIN pets p2 ON p2.pet_id=fh.pet_id
              WHERE fh.food_id=f.food_id AND p2.species=p.species
              AND p2.pet_id<>p.pet_id AND fh.ate_amount_percent>90)
"""),
    _e("Find owners whose pets collectively love more distinct flavors than the number of distinct flavors the owner has purchased.",
       """
SELECT o.owner_id, o.owner_name FROM owners o
WHERE (SELECT COUNT(DISTINCT l.flavor) FROM pet_likes l
       JOIN pets p ON p.pet_id=l.pet_id WHERE p.owner_id=o.owner_id)
    > (SELECT COUNT(DISTINCT f.flavor) FROM purchases pu
       JOIN foods f ON f.food_id=pu.food_id WHERE pu.owner_id=o.owner_id)
"""),
    _e("List brands where the highest priced item was never purchased but a lower priced item from the same brand was purchased.",
       """
SELECT DISTINCT f.brand FROM foods f
WHERE f.price=(SELECT MAX(g.price) FROM foods g WHERE g.brand=f.brand)
AND NOT EXISTS (SELECT 1 FROM purchases pu WHERE pu.food_id=f.food_id)
AND EXISTS (SELECT 1 FROM purchases pu JOIN foods g ON g.food_id=pu.food_id
            WHERE g.brand=f.brand AND g.price<f.price)
"""),
    _e("Find owners who have pets but have never purchased a food matching any of their pets' species.",
       """
SELECT o.owner_id, o.owner_name FROM owners o
WHERE EXISTS (SELECT 1 FROM pets p WHERE p.owner_id=o.owner_id)
AND NOT EXISTS (SELECT 1 FROM purchases pu
                JOIN foods f ON f.food_id=pu.food_id
                JOIN pets p ON p.owner_id=o.owner_id
                WHERE pu.owner_id=o.owner_id AND f.species_target=p.species)
"""),
    _e("List pets whose latest feeding was not vet approved and whose owner has purchased a vet-approved-compatible food type based on another feeding record.",
       """
SELECT DISTINCT p.pet_id, p.pet_name
FROM pets p
JOIN feeding_history lf ON lf.pet_id=p.pet_id
WHERE lf.feed_date=(SELECT MAX(fh.feed_date) FROM feeding_history fh
                    WHERE fh.pet_id=p.pet_id)
AND lf.vet_approved='no'
AND EXISTS (SELECT 1 FROM purchases pu
            JOIN foods f ON f.food_id=pu.food_id
            JOIN feeding_history fh2 ON fh2.pet_id=p.pet_id AND fh2.vet_approved='yes'
            JOIN foods f2 ON f2.food_id=fh2.food_id AND f2.food_type=f.food_type
            WHERE pu.owner_id=p.owner_id)
"""),
    _e("Find food types where the same owner both purchased the cheapest and the most expensive food of that type.",
       """
SELECT DISTINCT f.food_type FROM foods f
WHERE EXISTS (
  SELECT 1 FROM purchases pu1
  JOIN foods c ON c.food_id=pu1.food_id AND c.food_type=f.food_type
  JOIN purchases pu2 ON pu2.owner_id=pu1.owner_id
  JOIN foods e ON e.food_id=pu2.food_id AND e.food_type=f.food_type
  WHERE c.price=(SELECT MIN(x.price) FROM foods x WHERE x.food_type=f.food_type)
    AND e.price=(SELECT MAX(x.price) FROM foods x WHERE x.food_type=f.food_type))
"""),
    _e("List owners, pets, and loved food profiles where an outer join shows no matching purchased food by brand, food_type, and flavor.",
       """
SELECT o.owner_name, p.pet_name, l.preferred_brand, l.food_type, l.flavor
FROM owners o
JOIN pets p ON p.owner_id=o.owner_id
JOIN pet_likes l ON l.pet_id=p.pet_id
LEFT JOIN (SELECT DISTINCT pu.owner_id, f.brand, f.food_type, f.flavor
           FROM purchases pu JOIN foods f ON f.food_id=pu.food_id) pf
  ON pf.owner_id=o.owner_id AND pf.brand=l.preferred_brand
  AND pf.food_type=l.food_type AND pf.flavor=l.flavor
WHERE pf.owner_id IS NULL
"""),
]


CLINIC_20 = [
    _e("List patients whose latest appointment was cancelled but who have at least one unpaid invoice from an earlier appointment.",
       """
SELECT DISTINCT pt.patient_id, pt.patient_name
FROM patients pt
JOIN appointments la ON la.patient_id=pt.patient_id
WHERE la.appointment_date=(SELECT MAX(a.appointment_date) FROM appointments a
                           WHERE a.patient_id=pt.patient_id)
AND la.status='cancelled'
AND EXISTS (SELECT 1 FROM appointments a2
            JOIN invoices i ON i.appointment_id=a2.appointment_id
            WHERE a2.patient_id=pt.patient_id
            AND a2.appointment_date<la.appointment_date
            AND i.payment_status='unpaid')
"""),
    _e("Find doctors who treated patients from a different city and whose average invoice total is higher than the average invoice total for doctors in the same specialty.",
       """
WITH da AS (SELECT d.doctor_id, d.doctor_name, d.specialty, d.clinic_city,
                   AVG(i.total_amount) AS avg_inv
            FROM doctors d
            JOIN appointments a ON a.doctor_id=d.doctor_id
            JOIN invoices i ON i.appointment_id=a.appointment_id
            GROUP BY d.doctor_id, d.doctor_name, d.specialty, d.clinic_city)
SELECT da.doctor_id, da.doctor_name FROM da
WHERE EXISTS (SELECT 1 FROM appointments a
              JOIN patients pt ON pt.patient_id=a.patient_id
              WHERE a.doctor_id=da.doctor_id AND pt.city<>da.clinic_city)
AND da.avg_inv > (SELECT AVG(i2.total_amount)
                  FROM doctors d3
                  JOIN appointments a3 ON a3.doctor_id=d3.doctor_id
                  JOIN invoices i2 ON i2.appointment_id=a3.appointment_id
                  WHERE d3.specialty=da.specialty)
"""),
    _e("List patients who were prescribed a controlled substance but have no lab result marked high for the appointment where it was prescribed.",
       """
SELECT DISTINCT pt.patient_id, pt.patient_name
FROM patients pt
JOIN appointments a ON a.patient_id=pt.patient_id
JOIN prescriptions pr ON pr.appointment_id=a.appointment_id
JOIN medications m ON m.medication_id=pr.medication_id AND m.controlled_substance='yes'
WHERE NOT EXISTS (SELECT 1 FROM lab_results lr
                  WHERE lr.appointment_id=a.appointment_id AND lr.result_flag='high')
"""),
    _e("Find visit types where the same doctor handled both the lowest base fee and the highest base fee appointment of that visit type.",
       """
SELECT DISTINCT a.visit_type FROM appointments a
WHERE EXISTS (
  SELECT 1 FROM appointments lo
  JOIN appointments hi ON hi.doctor_id=lo.doctor_id AND hi.visit_type=lo.visit_type
  WHERE lo.visit_type=a.visit_type
  AND lo.base_fee=(SELECT MIN(x.base_fee) FROM appointments x WHERE x.visit_type=a.visit_type)
  AND hi.base_fee=(SELECT MAX(x.base_fee) FROM appointments x WHERE x.visit_type=a.visit_type))
"""),
    _e("List medications that were prescribed to patients with chronic conditions but never prescribed during urgent visits.",
       """
SELECT DISTINCT m.medication_id, m.medication_name
FROM medications m
JOIN prescriptions pr ON pr.medication_id=m.medication_id
JOIN appointments a ON a.appointment_id=pr.appointment_id
JOIN patients pt ON pt.patient_id=a.patient_id AND pt.chronic_condition='yes'
WHERE NOT EXISTS (SELECT 1 FROM prescriptions pr2
                  JOIN appointments a2 ON a2.appointment_id=pr2.appointment_id
                  WHERE pr2.medication_id=m.medication_id AND a2.visit_type='urgent')
"""),
    _e("Find patients whose total unpaid invoice amount is greater than the total amount paid by insurance for their completed appointments.",
       """
SELECT pt.patient_id, pt.patient_name FROM patients pt
WHERE (SELECT COALESCE(SUM(i.total_amount),0) FROM invoices i
       JOIN appointments a ON a.appointment_id=i.appointment_id
       WHERE a.patient_id=pt.patient_id AND i.payment_status='unpaid')
    > (SELECT COALESCE(SUM(i2.insurance_paid),0) FROM invoices i2
       JOIN appointments a2 ON a2.appointment_id=i2.appointment_id
       WHERE a2.patient_id=pt.patient_id AND a2.status='completed')
"""),
    _e("List doctors who have appointments with every insurance provider represented in the patients table.",
       """
SELECT d.doctor_id, d.doctor_name FROM doctors d
WHERE NOT EXISTS (
  SELECT 1 FROM (SELECT DISTINCT insurance_provider FROM patients) ip
  WHERE NOT EXISTS (SELECT 1 FROM appointments a
                    JOIN patients pt ON pt.patient_id=a.patient_id
                    WHERE a.doctor_id=d.doctor_id
                    AND pt.insurance_provider=ip.insurance_provider))
"""),
    _e("Find patients whose prescription days_supply is higher than every other prescription for the same medication class.",
       """
SELECT DISTINCT pt.patient_id, pt.patient_name
FROM patients pt
JOIN appointments a ON a.patient_id=pt.patient_id
JOIN prescriptions pr ON pr.appointment_id=a.appointment_id
JOIN medications m ON m.medication_id=pr.medication_id
WHERE NOT EXISTS (
  SELECT 1 FROM prescriptions pr2
  JOIN medications m2 ON m2.medication_id=pr2.medication_id
  WHERE m2.medication_class=m.medication_class
  AND pr2.prescription_id<>pr.prescription_id
  AND pr2.days_supply>=pr.days_supply)
"""),
    _e("List pairs of patients in the same city who saw the same doctor on different appointment dates.",
       """
SELECT DISTINCT p1.patient_name, p2.patient_name
FROM appointments a1
JOIN appointments a2 ON a1.doctor_id=a2.doctor_id
     AND a1.appointment_date<>a2.appointment_date
JOIN patients p1 ON p1.patient_id=a1.patient_id
JOIN patients p2 ON p2.patient_id=a2.patient_id
WHERE p1.city=p2.city AND p1.patient_id<p2.patient_id
"""),
    _e("Find appointments where the patient city is different from the doctor clinic city and the invoice is unpaid.",
       """
SELECT a.appointment_id
FROM appointments a
JOIN patients pt ON pt.patient_id=a.patient_id
JOIN doctors d ON d.doctor_id=a.doctor_id
JOIN invoices i ON i.appointment_id=a.appointment_id
WHERE pt.city<>d.clinic_city AND i.payment_status='unpaid'
"""),
    _e("List medications where the most expensive medication in each class was never prescribed, but a cheaper medication from the same class was prescribed.",
       """
SELECT m.medication_id, m.medication_name FROM medications m
WHERE m.unit_cost=(SELECT MAX(x.unit_cost) FROM medications x
                   WHERE x.medication_class=m.medication_class)
AND NOT EXISTS (SELECT 1 FROM prescriptions pr WHERE pr.medication_id=m.medication_id)
AND EXISTS (SELECT 1 FROM prescriptions pr2
            JOIN medications m2 ON m2.medication_id=pr2.medication_id
            WHERE m2.medication_class=m.medication_class AND m2.unit_cost<m.unit_cost)
"""),
    _e("Find patients who had a low lab result after receiving a prescription with refill allowed.",
       """
SELECT DISTINCT pt.patient_id, pt.patient_name
FROM patients pt
JOIN appointments pa ON pa.patient_id=pt.patient_id
JOIN prescriptions pr ON pr.appointment_id=pa.appointment_id AND pr.refill_allowed='yes'
JOIN appointments la ON la.patient_id=pt.patient_id
JOIN lab_results lr ON lr.appointment_id=la.appointment_id AND lr.result_flag='low'
WHERE lr.result_date > pa.appointment_date
"""),
    _e("List doctors whose patients had more distinct abnormal lab test names than the number of distinct medication classes they prescribed.",
       """
SELECT d.doctor_id, d.doctor_name FROM doctors d
WHERE (SELECT COUNT(DISTINCT lr.test_name) FROM appointments a
       JOIN lab_results lr ON lr.appointment_id=a.appointment_id
       WHERE a.doctor_id=d.doctor_id AND lr.result_flag<>'normal')
    > (SELECT COUNT(DISTINCT m.medication_class) FROM appointments a2
       JOIN prescriptions pr ON pr.appointment_id=a2.appointment_id
       JOIN medications m ON m.medication_id=pr.medication_id
       WHERE a2.doctor_id=d.doctor_id)
"""),
    _e("Find patients who have appointments but have never received a prescription for any medication class marked controlled substance.",
       """
SELECT pt.patient_id, pt.patient_name FROM patients pt
WHERE EXISTS (SELECT 1 FROM appointments a WHERE a.patient_id=pt.patient_id)
AND NOT EXISTS (SELECT 1 FROM appointments a
                JOIN prescriptions pr ON pr.appointment_id=a.appointment_id
                JOIN medications m ON m.medication_id=pr.medication_id
                WHERE a.patient_id=pt.patient_id AND m.controlled_substance='yes')
"""),
    _e("List the highest total invoice patient for each city, including ties.",
       """
WITH t AS (SELECT pt.patient_id, pt.patient_name, pt.city, SUM(i.total_amount) AS tot
           FROM patients pt
           JOIN appointments a ON a.patient_id=pt.patient_id
           JOIN invoices i ON i.appointment_id=a.appointment_id
           GROUP BY pt.patient_id, pt.patient_name, pt.city)
SELECT city, patient_name FROM t
WHERE tot=(SELECT MAX(t2.tot) FROM t t2 WHERE t2.city=t.city)
"""),
    _e("Find patients whose latest lab result was high and whose doctor for that appointment has less than five years of experience.",
       """
SELECT DISTINCT pt.patient_id, pt.patient_name
FROM patients pt
JOIN appointments a ON a.patient_id=pt.patient_id
JOIN lab_results lr ON lr.appointment_id=a.appointment_id
JOIN doctors d ON d.doctor_id=a.doctor_id
WHERE lr.result_date=(SELECT MAX(lr2.result_date) FROM lab_results lr2
                      JOIN appointments a2 ON a2.appointment_id=lr2.appointment_id
                      WHERE a2.patient_id=pt.patient_id)
AND lr.result_flag='high' AND d.years_experience<5
"""),
    _e("List appointments with no prescription but with at least one lab result and an unpaid invoice.",
       """
SELECT a.appointment_id FROM appointments a
WHERE NOT EXISTS (SELECT 1 FROM prescriptions pr WHERE pr.appointment_id=a.appointment_id)
AND EXISTS (SELECT 1 FROM lab_results lr WHERE lr.appointment_id=a.appointment_id)
AND EXISTS (SELECT 1 FROM invoices i WHERE i.appointment_id=a.appointment_id
            AND i.payment_status='unpaid')
"""),
    _e("Find doctors who have treated all visit types represented in the appointments table.",
       """
SELECT d.doctor_id, d.doctor_name FROM doctors d
WHERE (SELECT COUNT(DISTINCT a.visit_type) FROM appointments a
       WHERE a.doctor_id=d.doctor_id)
    = (SELECT COUNT(DISTINCT visit_type) FROM appointments)
"""),
    _e("List patients who were prescribed the same medication class by two different doctors.",
       """
SELECT DISTINCT pt.patient_id, pt.patient_name
FROM patients pt
JOIN appointments a1 ON a1.patient_id=pt.patient_id
JOIN prescriptions pr1 ON pr1.appointment_id=a1.appointment_id
JOIN medications m1 ON m1.medication_id=pr1.medication_id
JOIN appointments a2 ON a2.patient_id=pt.patient_id AND a2.doctor_id<>a1.doctor_id
JOIN prescriptions pr2 ON pr2.appointment_id=a2.appointment_id
JOIN medications m2 ON m2.medication_id=pr2.medication_id
     AND m2.medication_class=m1.medication_class
"""),
    _e("Find medication classes where patients with chronic conditions received more prescriptions than patients without chronic conditions.",
       """
SELECT m.medication_class
FROM medications m
JOIN prescriptions pr ON pr.medication_id=m.medication_id
JOIN appointments a ON a.appointment_id=pr.appointment_id
JOIN patients pt ON pt.patient_id=a.patient_id
GROUP BY m.medication_class
HAVING SUM(CASE WHEN pt.chronic_condition='yes' THEN 1 ELSE 0 END)
     > SUM(CASE WHEN pt.chronic_condition='no' THEN 1 ELSE 0 END)
"""),
]


CYBER_20 = [
    _e("List employees whose devices have unresolved critical alerts but who have no passed security training record.",
       """
SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON d.employee_id=e.employee_id
JOIN alerts al ON al.device_id=d.device_id AND al.severity='critical' AND al.resolved='no'
WHERE NOT EXISTS (SELECT 1 FROM training_records tr
                  WHERE tr.employee_id=e.employee_id AND tr.passed='yes')
"""),
    _e("Find device types where the same employee owns both the most vulnerable and least vulnerable device of that type by vulnerability count.",
       """
WITH vc AS (SELECT d.device_id, d.device_type, d.employee_id,
                   (SELECT COUNT(*) FROM device_vulnerabilities dv
                    WHERE dv.device_id=d.device_id) AS n
            FROM devices d)
SELECT DISTINCT v1.device_type
FROM vc v1 JOIN vc v2 ON v2.device_type=v1.device_type AND v2.employee_id=v1.employee_id
WHERE v1.n=(SELECT MAX(x.n) FROM vc x WHERE x.device_type=v1.device_type)
AND v2.n=(SELECT MIN(x.n) FROM vc x WHERE x.device_type=v1.device_type)
"""),
    _e("List devices with vulnerabilities that have an exploit available but no incident has been linked to any alert from that device.",
       """
SELECT DISTINCT d.device_id, d.hostname
FROM devices d
JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id
     AND v.exploit_available='yes'
WHERE NOT EXISTS (SELECT 1 FROM alerts al
                  JOIN incident_alerts ia ON ia.alert_id=al.alert_id
                  WHERE al.device_id=d.device_id)
"""),
    _e("Find departments whose employees have devices affected by all severity levels represented in the vulnerabilities table.",
       """
SELECT e.department
FROM employees e
JOIN devices d ON d.employee_id=e.employee_id
JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id
GROUP BY e.department
HAVING COUNT(DISTINCT v.severity)=(SELECT COUNT(DISTINCT severity) FROM vulnerabilities)
"""),
    _e("List employees whose average device risk score is above the average risk score of employees in their own department.",
       """
SELECT e.employee_id, e.employee_name FROM employees e
WHERE e.risk_score > (SELECT AVG(e2.risk_score) FROM employees e2
                      WHERE e2.department=e.department)
""", "risk_score lives on employees; read as employee risk vs department average"),
    _e("Find vulnerabilities that appear on more distinct operating system families than the number of distinct departments with trained employees.",
       """
SELECT v.vulnerability_id, v.cve_code FROM vulnerabilities v
WHERE (SELECT COUNT(DISTINCT d.os_family) FROM device_vulnerabilities dv
       JOIN devices d ON d.device_id=dv.device_id
       WHERE dv.vulnerability_id=v.vulnerability_id)
    > (SELECT COUNT(DISTINCT e.department) FROM employees e
       WHERE EXISTS (SELECT 1 FROM training_records tr
                     WHERE tr.employee_id=e.employee_id AND tr.passed='yes'))
"""),
    _e("List pairs of devices owned by different employees in the same office city that share the same CVE code.",
       """
SELECT DISTINCT d1.hostname, d2.hostname
FROM devices d1
JOIN employees e1 ON e1.employee_id=d1.employee_id
JOIN devices d2 ON d2.device_id>d1.device_id
JOIN employees e2 ON e2.employee_id=d2.employee_id
     AND e2.employee_id<>e1.employee_id AND e2.office_city=e1.office_city
JOIN device_vulnerabilities dv1 ON dv1.device_id=d1.device_id
JOIN device_vulnerabilities dv2 ON dv2.device_id=d2.device_id
JOIN vulnerabilities v1 ON v1.vulnerability_id=dv1.vulnerability_id
JOIN vulnerabilities v2 ON v2.vulnerability_id=dv2.vulnerability_id
     AND v2.cve_code=v1.cve_code
"""),
    _e("Find employees who opened incidents after their device's last patch date but before their latest unresolved alert time.",
       """
SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN incidents i ON i.opened_by_employee_id=e.employee_id
JOIN devices d ON d.employee_id=e.employee_id
WHERE i.opened_time > d.last_patch_date
AND i.opened_time < (SELECT MAX(al.alert_time) FROM alerts al
                     JOIN devices d2 ON d2.device_id=al.device_id
                     WHERE d2.employee_id=e.employee_id AND al.resolved='no')
"""),
    _e("List devices that have never had a false positive vulnerability record but have at least one unresolved alert.",
       """
SELECT d.device_id, d.hostname FROM devices d
WHERE NOT EXISTS (SELECT 1 FROM device_vulnerabilities dv
                  WHERE dv.device_id=d.device_id AND dv.false_positive='yes')
AND EXISTS (SELECT 1 FROM alerts al WHERE al.device_id=d.device_id AND al.resolved='no')
"""),
    _e("Find incident types where the highest impact incident was opened by an employee with no encrypted device.",
       """
WITH ranked AS (SELECT i.*, CASE i.business_impact WHEN 'high' THEN 3
                                 WHEN 'medium' THEN 2 ELSE 1 END AS imp
                FROM incidents i)
SELECT DISTINCT r.incident_type FROM ranked r
WHERE r.imp=(SELECT MAX(r2.imp) FROM ranked r2 WHERE r2.incident_type=r.incident_type)
AND NOT EXISTS (SELECT 1 FROM devices d
                WHERE d.employee_id=r.opened_by_employee_id AND d.encrypted='yes')
"""),
    _e("List employees whose manager has a lower risk score but whose devices have higher average CVSS score than the manager's devices.",
       """
SELECT e.employee_id, e.employee_name
FROM employees e JOIN employees m ON m.employee_id=e.manager_id
WHERE m.risk_score < e.risk_score
AND (SELECT AVG(v.cvss_score) FROM devices d
     JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
     JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id
     WHERE d.employee_id=e.employee_id)
  > (SELECT AVG(v.cvss_score) FROM devices d
     JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
     JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id
     WHERE d.employee_id=m.employee_id)
"""),
    _e("Find devices whose latest alert is unresolved and whose vulnerability with the highest CVSS score has not been remediated.",
       """
SELECT DISTINCT d.device_id, d.hostname
FROM devices d
JOIN alerts la ON la.device_id=d.device_id
JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id
WHERE la.alert_time=(SELECT MAX(a2.alert_time) FROM alerts a2 WHERE a2.device_id=d.device_id)
AND la.resolved='no'
AND v.cvss_score=(SELECT MAX(v2.cvss_score) FROM device_vulnerabilities dv2
                  JOIN vulnerabilities v2 ON v2.vulnerability_id=dv2.vulnerability_id
                  WHERE dv2.device_id=d.device_id)
AND dv.remediated_date IS NULL
"""),
    _e("List employees who have devices with all vulnerability severities but have not passed every security training course.",
       """
SELECT e.employee_id, e.employee_name FROM employees e
WHERE (SELECT COUNT(DISTINCT v.severity) FROM devices d
       JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
       JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id
       WHERE d.employee_id=e.employee_id)
    = (SELECT COUNT(DISTINCT severity) FROM vulnerabilities)
AND (SELECT COUNT(DISTINCT tr.course_name) FROM training_records tr
     WHERE tr.employee_id=e.employee_id AND tr.passed='yes')
  < (SELECT COUNT(DISTINCT course_name) FROM training_records)
"""),
    _e("Find office cities where every employee either has no device or has at least one encrypted device.",
       """
SELECT DISTINCT e.office_city FROM employees e
WHERE NOT EXISTS (
  SELECT 1 FROM employees e2 WHERE e2.office_city=e.office_city
  AND EXISTS (SELECT 1 FROM devices d WHERE d.employee_id=e2.employee_id)
  AND NOT EXISTS (SELECT 1 FROM devices d2
                  WHERE d2.employee_id=e2.employee_id AND d2.encrypted='yes'))
"""),
    _e("List CVE codes where the highest CVSS occurrence was never remediated but a lower CVSS occurrence was remediated.",
       """
WITH occ AS (SELECT v.cve_code, v.cvss_score, dv.remediated_date
             FROM device_vulnerabilities dv
             JOIN vulnerabilities v ON v.vulnerability_id=dv.vulnerability_id)
SELECT DISTINCT o.cve_code FROM occ o
WHERE o.cvss_score=(SELECT MAX(x.cvss_score) FROM occ x WHERE x.cve_code=o.cve_code)
AND o.remediated_date IS NULL
AND EXISTS (SELECT 1 FROM occ y WHERE y.cve_code=o.cve_code
            AND y.cvss_score<o.cvss_score AND y.remediated_date IS NOT NULL)
"""),
    _e("Find employees whose devices triggered more distinct alert types than the number of distinct courses they passed.",
       """
SELECT e.employee_id, e.employee_name FROM employees e
WHERE (SELECT COUNT(DISTINCT al.alert_type) FROM devices d
       JOIN alerts al ON al.device_id=d.device_id
       WHERE d.employee_id=e.employee_id)
    > (SELECT COUNT(DISTINCT tr.course_name) FROM training_records tr
       WHERE tr.employee_id=e.employee_id AND tr.passed='yes')
"""),
    _e("List incidents whose alerts come from devices owned by employees in a different office city than the employee who opened the incident.",
       """
SELECT DISTINCT i.incident_id
FROM incidents i
JOIN employees opener ON opener.employee_id=i.opened_by_employee_id
JOIN incident_alerts ia ON ia.incident_id=i.incident_id
JOIN alerts al ON al.alert_id=ia.alert_id
JOIN devices d ON d.device_id=al.device_id
JOIN employees owner ON owner.employee_id=d.employee_id
WHERE owner.office_city<>opener.office_city
"""),
    _e("Find devices with no vulnerabilities but with at least one high severity alert.",
       """
SELECT d.device_id, d.hostname FROM devices d
WHERE NOT EXISTS (SELECT 1 FROM device_vulnerabilities dv WHERE dv.device_id=d.device_id)
AND EXISTS (SELECT 1 FROM alerts al WHERE al.device_id=d.device_id AND al.severity='high')
"""),
    _e("List employees where every device they own has been patched after all vulnerabilities on that device were detected.",
       """
SELECT e.employee_id, e.employee_name FROM employees e
WHERE EXISTS (SELECT 1 FROM devices d WHERE d.employee_id=e.employee_id)
AND NOT EXISTS (SELECT 1 FROM devices d
                JOIN device_vulnerabilities dv ON dv.device_id=d.device_id
                WHERE d.employee_id=e.employee_id
                AND dv.detected_date >= d.last_patch_date)
"""),
    _e("Find departments where the same manager supervises both the highest risk and lowest risk employee in that department.",
       """
SELECT DISTINCT e.department FROM employees e
WHERE EXISTS (
  SELECT 1 FROM employees hi
  JOIN employees lo ON lo.department=hi.department AND lo.manager_id=hi.manager_id
  WHERE hi.department=e.department AND hi.manager_id IS NOT NULL
  AND hi.risk_score=(SELECT MAX(x.risk_score) FROM employees x WHERE x.department=e.department)
  AND lo.risk_score=(SELECT MIN(x.risk_score) FROM employees x WHERE x.department=e.department))
"""),
]


GOLD = {
    "petfood_50": {"database_id": 28, "items": PETFOOD_50},
    "clinic_20": {"database_id": 29, "items": CLINIC_20},
    "cyber_20": {"database_id": 30, "items": CYBER_20},
}


def get_gold(benchmark, index_1based, question=None):
    """Gold entry for a benchmark question (1-based index). Verifies the
    question text when provided; returns None when missing/mismatched."""
    bench = GOLD.get(benchmark)
    if not bench or not (1 <= index_1based <= len(bench["items"])):
        return None
    entry = bench["items"][index_1based - 1]
    if question is not None and entry["question"].strip() != str(question).strip():
        return None
    return entry

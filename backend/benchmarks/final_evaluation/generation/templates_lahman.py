"""
final_evaluation/generation/templates_lahman.py

Lahman Baseball (database_id 49) template families.
Per category: 4 easy + 6 medium + 5 hard = 15 semantic templates
(x 4 cases = 60 cases). Column names avoid digit-leading identifiers.
"""

from benchmarks.final_evaluation.generation.genlib import T

DB = 49
TS = []


def add(*ts):
    TS.extend(ts)


# ---------------------------------------------------------------- join
add(
T("j49_batting_people", "join", DB, "easy", "multiset_rows",
  ["two_table_join"],
  "SELECT p.nameFirst, p.nameLast, b.{col} FROM {child} b "
  "JOIN People p ON b.playerID = p.playerID WHERE b.yearID = {yr} "
  "AND b.{col} {op} {n}",
  ["List first and last names with {cdesc} for {yr} where {cdesc} {opw} {n}.",
   "Which players had {cdesc} {opw} {n} in {yr}? Show names and the value.",
   "Show player names and {cdesc} for the {yr} season when it was {opw} {n}.",
   "In {yr}, who recorded {cdesc} {opw} {n}? Include the value."],
  variants=[
   dict(child="Batting", col="HR", yr=2007, op=">=", n=40, opw="at least",
        cdesc="home runs"),
   dict(child="Batting", col="SB", yr=2010, op=">=", n=50, opw="at least",
        cdesc="stolen bases"),
   dict(child="Pitching", col="SO", yr=2015, op=">=", n=250,
        opw="at least", cdesc="strikeouts"),
   dict(child="Pitching", col="SV", yr=2008, op=">=", n=40,
        opw="at least", cdesc="saves"),
  ]),
T("j49_salary_join", "join", DB, "medium", "multiset_rows",
  ["two_table_join", "range_filter"],
  "SELECT p.nameFirst, p.nameLast, s.salary FROM Salaries s "
  "JOIN People p ON s.playerID = p.playerID WHERE s.yearID = {yr} "
  "AND s.teamID = '{team}' AND s.salary > {amt}",
  ["Which {team} players earned more than {amt} in {yr}? Show names and "
   "salary.",
   "List {yr} {team} salaries above {amt} with player names.",
   "Show first name, last name, and salary for {team} players paid over "
   "{amt} in {yr}.",
   "For team {team} in {yr}, who was paid above {amt}?"],
  variants=[
   dict(yr=2010, team="NYA", amt=10000000),
   dict(yr=2015, team="LAN", amt=15000000),
   dict(yr=2005, team="BOS", amt=8000000),
   dict(yr=2012, team="PHI", amt=12000000),
  ]),
T("j49_awards_join", "join", DB, "medium", "multiset_rows",
  ["two_table_join"],
  "SELECT p.nameFirst, p.nameLast, a.yearID FROM AwardsPlayers a "
  "JOIN People p ON a.playerID = p.playerID WHERE a.awardID = '{award}' "
  "AND a.yearID BETWEEN {y1} AND {y2}",
  ["Who won the {award} between {y1} and {y2}? Show names and year.",
   "List {award} winners from {y1} to {y2} with the season.",
   "Show first name, last name, and year for {award} awards {y1}-{y2}.",
   "Which players received the {award} in the {y1}-{y2} window?"],
  variants=[
   dict(award="Most Valuable Player", y1=2000, y2=2010),
   dict(award="Rookie of the Year", y1=1990, y2=2000),
  ]),
T("j49_hof_join", "join", DB, "hard", "multiset_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT p.nameFirst, p.nameLast, h.yearid FROM HallOfFame h "
  "JOIN People p ON h.playerID = p.playerID WHERE h.inducted = 'Y' "
  "AND h.category = '{cat}' AND h.yearid BETWEEN {y1} AND {y2}",
  ["Which {cat}s were inducted into the Hall of Fame between {y1} and "
   "{y2}? Show names and induction year.",
   "List Hall of Fame {cat} inductees from {y1} through {y2}.",
   "Show names and year for {cat}-category HOF inductions in {y1}-{y2}.",
   "Who entered the Hall of Fame as a {cat} between {y1} and {y2}?"],
  variants=[
   dict(cat="Player", y1=2000, y2=2010),
   dict(cat="Manager", y1=1980, y2=2010),
   dict(cat="Player", y1=1990, y2=1999),
  ]),
T("j49_anti", "join", DB, "hard", "multiset_rows",
  ["two_table_join", "null_handling"],
  "SELECT t.name FROM Teams t LEFT JOIN SeriesPost s "
  "ON t.teamID = s.teamIDwinner AND t.yearID = s.yearID "
  "AND s.round = 'WS' WHERE t.yearID = {yr} AND s.teamIDwinner IS NULL",
  ["Which {yr} teams did not win the World Series that year?",
   "List the names of {yr} teams without a {yr} World Series title.",
   "Show every team from {yr} that failed to win the World Series.",
   "In {yr}, which franchises' teams were not WS champions?"],
  variants=[
   dict(yr=2010),
   dict(yr=2015),
  ]),
)

# ------------------------------------------------------ multi_table_join
add(
T("m49_bat_team", "multi_table_join", DB, "easy", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT p.nameFirst, p.nameLast, t.name FROM Batting b "
  "JOIN People p ON b.playerID = p.playerID "
  "JOIN Teams t ON b.teamID = t.teamID AND b.yearID = t.yearID "
  "WHERE b.yearID = {yr} AND b.HR >= {n}",
  ["For {yr}, list players with at least {n} home runs and their team "
   "names.",
   "Which players hit {n}+ homers in {yr}, and for which team?",
   "Show name and team for {yr} players with {n} or more home runs.",
   "In {yr}, who reached {n} home runs? Include the team name."],
  variants=[
   dict(yr=2001, n=45),
   dict(yr=2019, n=40),
   dict(yr=1998, n=45),
   dict(yr=2006, n=40),
  ]),
T("m49_salary_team", "multi_table_join", DB, "medium", "multiset_rows",
  ["three_plus_table_join", "range_filter"],
  "SELECT p.nameFirst, p.nameLast, t.name, s.salary FROM Salaries s "
  "JOIN People p ON s.playerID = p.playerID "
  "JOIN Teams t ON s.teamID = t.teamID AND s.yearID = t.yearID "
  "WHERE s.yearID = {yr} AND s.salary >= {amt} AND t.lgID = '{lg}'",
  ["List {yr} {lg} players earning at least {amt}, with team names and "
   "salaries.",
   "Which {lg} players made {amt}+ in {yr}? Show name, team, salary.",
   "Show player, team, and salary for {lg} salaries of {amt} or more in "
   "{yr}.",
   "In the {yr} {lg}, who earned at least {amt}?"],
  variants=[
   dict(yr=2016, lg="AL", amt=20000000),
   dict(yr=2016, lg="NL", amt=20000000),
   dict(yr=2008, lg="AL", amt=15000000),
   dict(yr=2000, lg="NL", amt=10000000),
  ]),
T("m49_allstar_team", "multi_table_join", DB, "medium", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT p.nameFirst, p.nameLast, t.name FROM AllstarFull a "
  "JOIN People p ON a.playerID = p.playerID "
  "JOIN Teams t ON a.teamID = t.teamID AND a.yearID = t.yearID "
  "WHERE a.yearID = {yr} AND t.lgID = '{lg}'",
  ["Who represented {lg} teams in the {yr} All-Star game? Show player and "
   "team.",
   "List {yr} All-Stars from the {lg} with their team names.",
   "Show name and team for every {yr} {lg} All-Star selection.",
   "Which {lg} players were {yr} All-Stars, and for which teams?"],
  variants=[
   dict(yr=2010, lg="AL"),
   dict(yr=2010, lg="NL"),
  ]),
T("m49_college", "multi_table_join", DB, "hard", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT DISTINCT p.nameFirst, p.nameLast, s.name_full "
  "FROM CollegePlaying c JOIN People p ON c.playerID = p.playerID "
  "JOIN Schools s ON c.schoolID = s.schoolID WHERE s.state = '{st}' "
  "AND c.yearID BETWEEN {y1} AND {y2}",
  ["Which players attended {st} colleges between {y1} and {y2}? Show "
   "player and school.",
   "List players and their {st} schools for college years {y1}-{y2}.",
   "Show distinct player/school pairs for {st} colleges, {y1} to {y2}.",
   "Who played college ball in {st} from {y1} through {y2}?"],
  variants=[
   dict(st="CA", y1=2000, y2=2005),
   dict(st="TX", y1=1995, y2=2000),
   dict(st="FL", y1=2005, y2=2010),
  ]),
T("m49_ws_managers", "multi_table_join", DB, "hard", "multiset_rows",
  ["three_plus_table_join", "multiple_conditions"],
  "SELECT p.nameFirst, p.nameLast, t.name, m.yearID FROM Managers m "
  "JOIN People p ON m.playerID = p.playerID "
  "JOIN Teams t ON m.teamID = t.teamID AND m.yearID = t.yearID "
  "WHERE t.WSWin = 'Y' AND m.yearID BETWEEN {y1} AND {y2}",
  ["Which managers led World Series winners between {y1} and {y2}? Show "
   "manager, team, and year.",
   "List WS-winning managers from {y1} to {y2} with team names.",
   "Show manager name, team, and season for World Series champions "
   "{y1}-{y2}.",
   "Who managed a World Series champion in the {y1}-{y2} window?"],
  variants=[
   dict(y1=2000, y2=2010),
   dict(y1=1990, y2=1999),
  ]),
)

# --------------------------------------------------------------- group_by
add(
T("g49_count_per", "group_by", DB, "easy", "multiset_rows", [],
  "SELECT {gcol}, COUNT(*) FROM {tbl} WHERE {w} GROUP BY {gcol}",
  ["How many {noun}s per {gdesc} {wdesc}?",
   "Count {noun}s by {gdesc} {wdesc}.",
   "For each {gdesc}, count the {noun}s {wdesc}.",
   "Per {gdesc} {wdesc}, how many {noun}s are there?"],
  variants=[
   dict(tbl="Batting", gcol="teamID", w="yearID = 2015",
        gdesc="team", noun="batting record", wdesc="in 2015"),
   dict(tbl="AwardsPlayers", gcol="awardID", w="yearID >= 2010",
        gdesc="award", noun="award win", wdesc="since 2010"),
   dict(tbl="HallOfFame", gcol="votedBy", w="inducted = 'Y'",
        gdesc="voting body", noun="induction", wdesc="among inductees"),
   dict(tbl="People", gcol="birthCountry", w="birthYear >= 1980",
        gdesc="birth country", noun="player", wdesc="born 1980 or later"),
  ]),
T("g49_agg_per", "group_by", DB, "medium", "multiset_rows", [],
  "SELECT {gcol}, {agg} FROM {tbl} WHERE {w} GROUP BY {gcol}",
  ["Per {gdesc}, what is the {adesc} {wdesc}?",
   "Show the {adesc} for each {gdesc} {wdesc}.",
   "Group by {gdesc} and compute the {adesc} {wdesc}.",
   "For every {gdesc} {wdesc}, report the {adesc}."],
  variants=[
   dict(tbl="Salaries", gcol="teamID", agg="SUM(salary)",
        w="yearID = 2016", gdesc="team", adesc="total payroll",
        wdesc="in 2016"),
   dict(tbl="Salaries", gcol="yearID", agg="AVG(salary)",
        w="teamID = 'NYA'", gdesc="season", adesc="average Yankees salary",
        wdesc="for team NYA"),
   dict(tbl="Batting", gcol="teamID", agg="SUM(HR)",
        w="yearID = 2019", gdesc="team", adesc="total home runs",
        wdesc="in 2019"),
   dict(tbl="Pitching", gcol="teamID", agg="SUM(SO)",
        w="yearID = 2015", gdesc="team", adesc="total strikeouts",
        wdesc="in 2015"),
   dict(tbl="Teams", gcol="lgID", agg="AVG(attendance)",
        w="yearID = 2015", gdesc="league", adesc="average attendance",
        wdesc="in 2015"),
   dict(tbl="Batting", gcol="yearID", agg="SUM(HR)",
        w="teamID = 'BOS' AND yearID BETWEEN 2000 AND 2010",
        gdesc="season", adesc="Red Sox home run total",
        wdesc="for 2000-2010"),
  ]),
T("g49_two_key", "group_by", DB, "hard", "multiset_rows", [],
  "SELECT {g1}, {g2}, {agg} FROM {tbl} WHERE {w} GROUP BY {g1}, {g2}",
  ["Break the {adesc} down by {g1d} and {g2d} {wdesc}.",
   "Per {g1d} and {g2d} {wdesc}, what is the {adesc}?",
   "Compute the {adesc} for each ({g1d}, {g2d}) pair {wdesc}.",
   "Show {g1d}, {g2d}, and the {adesc} {wdesc}."],
  variants=[
   dict(tbl="Salaries", g1="yearID", g2="lgID", agg="SUM(salary)",
        w="yearID BETWEEN 2010 AND 2012", g1d="season", g2d="league",
        adesc="total salary spend", wdesc="from 2010 to 2012"),
   dict(tbl="Batting", g1="teamID", g2="yearID", agg="SUM(HR)",
        w="yearID IN (2018, 2019)", g1d="team", g2d="season",
        adesc="home run total", wdesc="for 2018 and 2019"),
   dict(tbl="Pitching", g1="teamID", g2="lgID", agg="SUM(W)",
        w="yearID = 2016", g1d="team", g2d="league",
        adesc="total pitcher wins", wdesc="in 2016"),
   dict(tbl="Fielding", g1="POS", g2="lgID", agg="SUM(E)",
        w="yearID = 2010", g1d="position", g2d="league",
        adesc="total errors", wdesc="in 2010"),
   dict(tbl="AwardsPlayers", g1="awardID", g2="lgID", agg="COUNT(*)",
        w="yearID BETWEEN 2015 AND 2016", g1d="award", g2d="league",
        adesc="number of awards", wdesc="in 2015-2016"),
  ]),
)

# ----------------------------------------------------------------- having
add(
T("h49_count", "having", DB, "easy", "multiset_rows", [],
  "SELECT {gcol}, COUNT(*) FROM {tbl} WHERE {w} GROUP BY {gcol} "
  "HAVING COUNT(*) {op} {n}",
  ["Which {gdesc}s have {opw} {n} {noun}s {wdesc}?",
   "List {gdesc}s with {opw} {n} {noun}s {wdesc}, including the count.",
   "Find {gdesc}s having {opw} {n} {noun}s {wdesc}.",
   "Show {gdesc}s where {noun} count is {opw} {n} {wdesc}."],
  variants=[
   dict(tbl="AwardsPlayers", gcol="playerID", w="awardID = 'Gold Glove'",
        op=">=", n=10, opw="at least", gdesc="player",
        noun="Gold Glove", wdesc=""),
   dict(tbl="AllstarFull", gcol="playerID", w="yearID >= 2000",
        op=">=", n=10, opw="at least", gdesc="player",
        noun="All-Star selection", wdesc="since 2000"),
   dict(tbl="Managers", gcol="playerID", w="1=1", op=">", n=25,
        opw="more than", gdesc="manager", noun="season managed",
        wdesc=""),
   dict(tbl="Batting", gcol="playerID", w="HR >= 40", op=">=", n=5,
        opw="at least", gdesc="player", noun="40-homer season",
        wdesc=""),
  ]),
T("h49_sum", "having", DB, "medium", "multiset_rows", [],
  "SELECT {gcol}, {agg} FROM {tbl} WHERE {w} GROUP BY {gcol} "
  "HAVING {agg} {op} {n}",
  ["Which {gdesc}s have a {adesc} {opw} {n} {wdesc}? Show the value.",
   "List {gdesc}s whose {adesc} is {opw} {n} {wdesc}.",
   "Find {gdesc}s with {adesc} {opw} {n} {wdesc}.",
   "Show the {gdesc}s where the {adesc} {opw} {n} {wdesc}."],
  variants=[
   dict(tbl="Batting", gcol="playerID", agg="SUM(HR)", w="1=1",
        op=">=", n=500, opw="at least", gdesc="player",
        adesc="career home run total", wdesc=""),
   dict(tbl="Salaries", gcol="teamID", agg="SUM(salary)",
        w="yearID = 2015", op=">", n=180000000, opw="above",
        gdesc="team", adesc="2015 payroll", wdesc=""),
   dict(tbl="Pitching", gcol="playerID", agg="SUM(SO)", w="1=1",
        op=">=", n=3000, opw="at least", gdesc="pitcher",
        adesc="career strikeout total", wdesc=""),
   dict(tbl="Batting", gcol="playerID", agg="SUM(SB)", w="1=1",
        op=">=", n=600, opw="at least", gdesc="player",
        adesc="career stolen base total", wdesc=""),
   dict(tbl="Batting", gcol="teamID", agg="SUM(HR)",
        w="yearID = 2019", op=">=", n=250, opw="at least",
        gdesc="team", adesc="2019 home run total", wdesc=""),
   dict(tbl="Teams", gcol="franchID", agg="SUM(attendance)",
        w="yearID BETWEEN 2010 AND 2019", op=">", n=30000000,
        opw="above", gdesc="franchise",
        adesc="total 2010s attendance", wdesc=""),
  ]),
T("h49_avg_filtered", "having", DB, "hard", "multiset_rows",
  ["multiple_conditions"],
  "SELECT {gcol}, {agg} FROM {tbl} WHERE {w} GROUP BY {gcol} "
  "HAVING {agg} {op} {n} AND COUNT(*) >= {minn}",
  ["Which {gdesc}s {wdesc} have {adesc} {opw} {n} across at least {minn} "
   "{noun}s?",
   "List {gdesc}s with {adesc} {opw} {n}, requiring {minn}+ {noun}s "
   "{wdesc}.",
   "Find {gdesc}s ({minn} or more {noun}s {wdesc}) whose {adesc} is "
   "{opw} {n}.",
   "Show {gdesc}s meeting both: {minn}+ {noun}s {wdesc} and {adesc} "
   "{opw} {n}."],
  variants=[
   dict(tbl="Batting", gcol="playerID", agg="AVG(HR)", w="AB >= 400",
        op=">=", n=30, opw="at least", minn=10, gdesc="player",
        adesc="average home runs per qualifying season",
        noun="400-at-bat season", wdesc=""),
   dict(tbl="Salaries", gcol="playerID", agg="AVG(salary)",
        w="yearID >= 2010", op=">", n=15000000, opw="above", minn=5,
        gdesc="player", adesc="average salary",
        noun="salary season", wdesc="since 2010"),
   dict(tbl="Pitching", gcol="playerID", agg="AVG(SO)", w="GS >= 25",
        op=">=", n=200, opw="at least", minn=8, gdesc="pitcher",
        adesc="average strikeouts per full season",
        noun="25-start season", wdesc=""),
   dict(tbl="Teams", gcol="franchID", agg="AVG(W)",
        w="yearID BETWEEN 2000 AND 2019", op=">=", n=90,
        opw="at least", minn=15, gdesc="franchise",
        adesc="average wins", noun="season", wdesc="in 2000-2019"),
   dict(tbl="Managers", gcol="playerID", agg="AVG(W)", w="G >= 100",
        op=">=", n=90, opw="at least", minn=10, gdesc="manager",
        adesc="average wins per full season",
        noun="100-game season", wdesc=""),
  ]),
)

# ------------------------------------------------------------ subquery_cte
add(
T("s49_above_avg", "subquery_cte", DB, "easy", "multiset_rows",
  ["population_comparison"],
  "SELECT {sel} FROM {tbl} WHERE {w} AND {col} > "
  "(SELECT AVG({col}) FROM {tbl} WHERE {w})",
  ["Among {dom}, which rows have {cdesc} above the average? Show {seld}.",
   "List {seld} where {cdesc} beats the {dom} average.",
   "Find {dom} entries with above-average {cdesc}.",
   "Show {seld} for {dom} whose {cdesc} exceeds the group average."],
  variants=[
   dict(tbl="Salaries", w="yearID = 2016", col="salary",
        sel="playerID, salary", seld="player id and salary",
        dom="2016 salaries", cdesc="salary"),
   dict(tbl="Teams", w="yearID = 2015", col="attendance",
        sel="name, attendance", seld="team name and attendance",
        dom="2015 teams", cdesc="attendance"),
   dict(tbl="Batting", w="yearID = 2019 AND AB >= 400", col="HR",
        sel="playerID, HR", seld="player id and home runs",
        dom="2019 qualified batters", cdesc="home run count"),
   dict(tbl="Pitching", w="yearID = 2015 AND GS >= 20", col="SO",
        sel="playerID, SO", seld="player id and strikeouts",
        dom="2015 starters", cdesc="strikeout count"),
  ]),
T("s49_correlated", "subquery_cte", DB, "medium", "multiset_rows",
  ["correlated_subquery", "population_comparison"],
  "SELECT s.playerID, s.salary FROM Salaries s WHERE s.yearID = {yr} "
  "AND s.salary > (SELECT AVG(s2.salary) FROM Salaries s2 "
  "WHERE s2.yearID = s.yearID AND s2.teamID = s.teamID)",
  ["In {yr}, which players out-earned their own team's average salary?",
   "List {yr} players paid above their team average, with the salary.",
   "Who earned more than their team's {yr} average? Show id and salary.",
   "Find {yr} salaries above the same-team average."],
  variants=[
   dict(yr=2016), dict(yr=2010), dict(yr=2005), dict(yr=2000),
   dict(yr=1995), dict(yr=2013),
  ]),
T("s49_cte_totals", "subquery_cte", DB, "hard", "multiset_rows",
  ["nested_aggregation", "population_comparison"],
  "WITH totals AS (SELECT playerID, SUM({m}) AS total FROM {tbl} "
  "WHERE {w} GROUP BY playerID) SELECT playerID, total FROM totals "
  "WHERE total > (SELECT AVG(total) FROM totals)",
  ["Total {mdesc} per player {wdesc}; who is above the average of those "
   "totals?",
   "Which players' career {mdesc} totals {wdesc} beat the average "
   "player's total?",
   "First sum {mdesc} per player {wdesc}, then list players above the "
   "cross-player average.",
   "Find players whose summed {mdesc} {wdesc} exceeds the average "
   "player total."],
  variants=[
   dict(tbl="Batting", m="HR", w="yearID >= 2000", mdesc="home runs",
        wdesc="since 2000"),
   dict(tbl="Salaries", m="salary", w="yearID >= 2010",
        mdesc="salary", wdesc="since 2010"),
   dict(tbl="Pitching", m="SO", w="yearID >= 2010",
        mdesc="strikeouts", wdesc="since 2010"),
   dict(tbl="Batting", m="SB", w="yearID >= 1990",
        mdesc="stolen bases", wdesc="since 1990"),
   dict(tbl="Batting", m="RBI", w="yearID >= 2005", mdesc="RBIs",
        wdesc="since 2005"),
  ]),
)

# --------------------------------------------------------- set_operations
add(
T("o49_league_sets", "set_operations", DB, "easy", "set_rows", [],
  "SELECT playerID FROM {t1} WHERE {w1} {setop} "
  "SELECT playerID FROM {t2} WHERE {w2}",
  ["{setw} of {d1} and {d2}: list the player ids.",
   "Which player ids result from {d1} {setop} {d2}?",
   "Apply {setop} to ({d1}) and ({d2}).",
   "List ids in the {setw} of {d1} and {d2}."],
  variants=[
   dict(t1="Batting", w1="yearID = 2015 AND HR >= 20",
        t2="Batting", w2="yearID = 2016 AND HR >= 20",
        setop="INTERSECT", setw="intersection",
        d1="2015 twenty-homer hitters", d2="2016 twenty-homer hitters"),
   dict(t1="AllstarFull", w1="yearID = 2010",
        t2="AllstarFull", w2="yearID = 2011", setop="INTERSECT",
        setw="intersection", d1="2010 All-Stars", d2="2011 All-Stars"),
   dict(t1="Batting", w1="yearID = 2019 AND HR >= 30",
        t2="AllstarFull", w2="yearID = 2019", setop="EXCEPT",
        setw="difference", d1="2019 thirty-homer hitters",
        d2="2019 All-Stars"),
   dict(t1="Pitching", w1="yearID = 2015 AND W >= 15",
        t2="Pitching", w2="yearID = 2015 AND SO >= 200",
        setop="UNION", setw="union",
        d1="2015 fifteen-game winners", d2="2015 200-strikeout pitchers"),
  ]),
T("o49_award_sets", "set_operations", DB, "medium", "set_rows", [],
  "SELECT playerID FROM AwardsPlayers WHERE awardID = '{a1}' {setop} "
  "SELECT playerID FROM AwardsPlayers WHERE awardID = '{a2}'",
  ["Which players appear in the {setw} of {a1} winners and {a2} "
   "winners?",
   "{setw2} the set of {a1} winners with the set of {a2} winners.",
   "List player ids from ({a1} winners) {setop} ({a2} winners).",
   "Who is in the {setw} of {a1} and {a2} award winners?"],
  variants=[
   dict(a1="Most Valuable Player", a2="Rookie of the Year",
        setop="INTERSECT", setw="intersection", setw2="Intersect"),
   dict(a1="Gold Glove", a2="Silver Slugger", setop="INTERSECT",
        setw="intersection", setw2="Intersect"),
   dict(a1="Most Valuable Player", a2="Gold Glove", setop="EXCEPT",
        setw="difference", setw2="Subtract"),
   dict(a1="Rookie of the Year", a2="Most Valuable Player",
        setop="EXCEPT", setw="difference", setw2="Subtract"),
   dict(a1="Silver Slugger", a2="Gold Glove", setop="UNION",
        setw="union", setw2="Union"),
   dict(a1="Rookie of the Year", a2="Gold Glove", setop="INTERSECT",
        setw="intersection", setw2="Intersect"),
  ]),
T("o49_threeway", "set_operations", DB, "hard", "set_rows",
  ["multiple_conditions"],
  "SELECT playerID FROM {t1} WHERE {w1} {op1} SELECT playerID FROM {t2} "
  "WHERE {w2} {op2} SELECT playerID FROM {t3} WHERE {w3}",
  ["Combine: {d1} {op1w} {d2} {op2w} {d3}. List the ids.",
   "Starting with {d1}, {op1} with {d2}, then {op2} {d3}.",
   "Which players remain from {d1} {op1w} {d2} {op2w} {d3}?",
   "Chain the sets ({d1}) {op1} ({d2}) {op2} ({d3})."],
  variants=[
   dict(t1="Batting", w1="yearID = 2010 AND HR >= 25",
        t2="AllstarFull", w2="yearID = 2010",
        t3="AwardsPlayers", w3="awardID = 'Gold Glove' AND yearID = 2010",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="2010 twenty-five-homer hitters", d2="2010 All-Stars",
        d3="2010 Gold Glove winners"),
   dict(t1="Salaries", w1="yearID = 2015 AND salary > 15000000",
        t2="Batting", w2="yearID = 2015 AND HR >= 30",
        t3="Pitching", w3="yearID = 2015",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="2015 high earners", d2="2015 thirty-homer hitters",
        d3="2015 pitchers"),
   dict(t1="HallOfFame", w1="inducted = 'Y'",
        t2="AwardsPlayers", w2="awardID = 'Most Valuable Player'",
        t3="Managers", w3="1=1",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="Hall of Famers", d2="MVP winners", d3="managers"),
   dict(t1="AllstarFull", w1="yearID = 2000",
        t2="AllstarFull", w2="yearID = 2005",
        t3="AllstarFull", w3="yearID = 2010",
        op1="INTERSECT", op2="INTERSECT", op1w="intersect",
        op2w="intersect", d1="2000 All-Stars", d2="2005 All-Stars",
        d3="2010 All-Stars"),
   dict(t1="Batting", w1="yearID = 2019 AND SB >= 20",
        t2="Batting", w2="yearID = 2019 AND HR >= 20",
        t3="AllstarFull", w3="yearID = 2019",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="2019 twenty-steal players", d2="2019 twenty-homer players",
        d3="2019 All-Stars"),
  ]),
)

# ------------------------------------------------------ order_limit_topk
add(
T("t49_topk", "order_limit_topk", DB, "easy", "ordered_rows", [],
  "SELECT {sel}, {col} FROM {tbl} WHERE {w} ORDER BY {col} DESC, "
  "{tie} ASC LIMIT {k}",
  ["Top {k} {dom} by {cdesc}: show {seld} and the value.",
   "Which {k} {dom} have the highest {cdesc}?",
   "Rank {dom} by {cdesc} descending; return the first {k}.",
   "List the {k} highest-{cdesc} {dom}."],
  variants=[
   dict(tbl="Salaries", w="yearID = 2016", col="salary",
        sel="playerID", tie="playerID", k=10, dom="2016 salaries",
        seld="the player id", cdesc="salary"),
   dict(tbl="Batting", w="yearID = 2019", col="HR", sel="playerID",
        tie="playerID", k=10, dom="2019 batters", seld="the player id",
        cdesc="home run count"),
   dict(tbl="Teams", w="yearID = 2015", col="W", sel="name",
        tie="teamID", k=5, dom="2015 teams", seld="the team name",
        cdesc="win count"),
   dict(tbl="Pitching", w="yearID = 2015 AND GS >= 15", col="SO",
        sel="playerID", tie="playerID", k=10, dom="2015 starters",
        seld="the player id", cdesc="strikeout count"),
  ]),
T("t49_topk_agg", "order_limit_topk", DB, "medium", "ordered_rows",
  ["nested_aggregation"],
  "SELECT {gcol} AS grp, {agg} AS agg_value FROM {tbl} WHERE {w} "
  "GROUP BY {gcol} ORDER BY agg_value DESC, grp ASC LIMIT {k}",
  ["Top {k} {gdesc}s by {adesc} {wdesc}.",
   "Which {k} {gdesc}s lead in {adesc} {wdesc}?",
   "Rank {gdesc}s by {adesc} {wdesc}; return the top {k}.",
   "List the {k} {gdesc}s with the highest {adesc} {wdesc}."],
  variants=[
   dict(tbl="Batting", gcol="playerID", agg="SUM(HR)", w="1=1",
        k=10, gdesc="player", adesc="career home runs", wdesc=""),
   dict(tbl="Salaries", gcol="teamID", agg="SUM(salary)",
        w="yearID = 2016", k=5, gdesc="team", adesc="2016 payroll",
        wdesc=""),
   dict(tbl="Pitching", gcol="playerID", agg="SUM(W)", w="1=1",
        k=10, gdesc="pitcher", adesc="career wins", wdesc=""),
   dict(tbl="Batting", gcol="playerID", agg="SUM(SB)", w="1=1",
        k=10, gdesc="player", adesc="career stolen bases", wdesc=""),
   dict(tbl="AwardsPlayers", gcol="playerID", agg="COUNT(*)",
        w="awardID = 'Gold Glove'", k=10, gdesc="player",
        adesc="Gold Glove count", wdesc=""),
   dict(tbl="Teams", gcol="franchID", agg="SUM(attendance)",
        w="yearID BETWEEN 2010 AND 2019", k=5, gdesc="franchise",
        adesc="2010s attendance", wdesc=""),
  ]),
T("t49_topk_derived", "order_limit_topk", DB, "hard", "ordered_rows",
  ["derived_measure"],
  "SELECT {sel} AS entity, {expr} AS metric FROM {tbl} WHERE {w} "
  "ORDER BY metric DESC, entity ASC LIMIT {k}",
  ["Top {k} {dom} by {mdesc}.",
   "Which {k} {dom} have the best {mdesc}?",
   "Rank {dom} on {mdesc}; show the top {k}.",
   "List the {k} leading {dom} by {mdesc}."],
  variants=[
   dict(tbl="Batting", sel="playerID",
        expr="H * 1.0 / AB", w="yearID = 2019 AND AB >= 400", k=10,
        dom="2019 qualified batters", mdesc="batting average"),
   dict(tbl="Teams", sel="name", expr="W * 1.0 / G",
        w="yearID = 2015", k=5, dom="2015 teams",
        mdesc="win percentage"),
   dict(tbl="Batting", sel="playerID", expr="HR * 1.0 / AB",
        w="yearID = 2019 AND AB >= 400", k=10,
        dom="2019 qualified batters", mdesc="home run rate"),
   dict(tbl="Managers", sel="playerID", expr="W * 1.0 / (W + L)",
        w="G >= 150", k=10, dom="full-season manager stints",
        mdesc="winning percentage"),
   dict(tbl="Pitching", sel="playerID", expr="SO * 1.0 / BB",
        w="yearID = 2015 AND BB >= 20 AND GS >= 15", k=10,
        dom="2015 starters", mdesc="strikeout-to-walk ratio"),
  ]),
)

# ------------------------------------------------------------ aggregation
add(
T("a49_scalar", "aggregation", DB, "easy", "scalar", [],
  "SELECT {agg} FROM {tbl} WHERE {w}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Report {qw2}."],
  variants=[
   dict(agg="COUNT(*)", tbl="People", w="birthCountry = 'D.R.'",
        qw="How many players were born in the Dominican Republic",
        qw2="the number of players born in country code D.R."),
   dict(agg="MAX(salary)", tbl="Salaries", w="yearID = 2016",
        qw="What was the highest salary in 2016",
        qw2="the maximum 2016 salary"),
   dict(agg="SUM(HR)", tbl="Batting", w="yearID = 2019",
        qw="How many home runs were hit in 2019",
        qw2="the total 2019 home run count"),
   dict(agg="AVG(attendance)", tbl="Teams", w="yearID = 2015",
        qw="What was the average team attendance in 2015",
        qw2="the mean 2015 attendance per team"),
  ]),
T("a49_filtered", "aggregation", DB, "medium", "scalar", [],
  "SELECT {agg} FROM {tbl} WHERE {w}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Give {qw2}."],
  variants=[
   dict(agg="AVG(salary)", tbl="Salaries",
        w="yearID = 2016 AND teamID = 'NYA'",
        qw="What was the Yankees' average salary in 2016",
        qw2="the mean 2016 salary on team NYA"),
   dict(agg="SUM(salary)", tbl="Salaries",
        w="yearID = 2015 AND lgID = 'AL'",
        qw="What was the total AL payroll in 2015",
        qw2="the summed 2015 American League salaries"),
   dict(agg="COUNT(*)", tbl="Batting",
        w="yearID = 2019 AND HR >= 30",
        qw="How many 30-homer seasons were there in 2019",
        qw2="the count of 2019 player-seasons with 30+ home runs"),
   dict(agg="MAX(W)", tbl="Teams", w="yearID = 2001",
        qw="What was the most wins by a team in 2001",
        qw2="the maximum team win total in 2001"),
   dict(agg="AVG(HR)", tbl="Batting",
        w="yearID = 2019 AND AB >= 400",
        qw="What was the average homer count among 2019 qualified "
           "batters",
        qw2="the mean 2019 home runs for players with 400+ at-bats"),
   dict(agg="COUNT(*)", tbl="HallOfFame",
        w="inducted = 'Y' AND category = 'Player'",
        qw="How many players have been inducted into the Hall of Fame",
        qw2="the number of Player-category HOF inductions"),
  ]),
T("a49_expr", "aggregation", DB, "hard", "scalar", ["derived_measure"],
  "SELECT {agg} FROM {tbl} WHERE {w}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Determine {qw2}."],
  variants=[
   dict(agg="SUM(H) * 1.0 / SUM(AB)", tbl="Batting",
        w="yearID = 2019 AND AB > 0",
        qw="What was the league-wide batting average in 2019",
        qw2="total hits divided by total at-bats for 2019"),
   dict(agg="SUM(W) * 1.0 / SUM(G)", tbl="Teams", w="yearID = 2015",
        qw="What fraction of 2015 games ended in a home team win "
           "column (wins over games)",
        qw2="summed wins divided by summed games across 2015 teams"),
   dict(agg="AVG(weight * 1.0 / height)", tbl="People",
        w="weight IS NOT NULL AND height IS NOT NULL AND birthYear "
          ">= 1980",
        qw="What is the average weight-to-height ratio of players born "
           "since 1980",
        qw2="the mean weight/height ratio for post-1980 births"),
   dict(agg="MAX(salary) - MIN(salary)", tbl="Salaries",
        w="yearID = 2016",
        qw="What was the salary spread in 2016",
        qw2="the difference between the highest and lowest 2016 salary"),
   dict(agg="COUNT(*) * 1.0 / COUNT(DISTINCT teamID)", tbl="Batting",
        w="yearID = 2015",
        qw="On average, how many 2015 batting records exist per team",
        qw2="2015 batting rows divided by the number of distinct teams"),
  ]),
)

# --------------------------------------------------------- distinct_count
add(
T("d49_simple", "distinct_count", DB, "easy", "scalar", ["distinct"],
  "SELECT COUNT(DISTINCT {col}) FROM {tbl} WHERE {w}",
  ["How many distinct {cdesc}s {wdesc}?",
   "Count the unique {cdesc}s {wdesc}.",
   "How many different {cdesc}s {wdesc}?",
   "What is the number of unique {cdesc}s {wdesc}?"],
  variants=[
   dict(tbl="Batting", col="playerID", w="yearID = 2019",
        cdesc="player", wdesc="batted in 2019"),
   dict(tbl="Teams", col="franchID", w="yearID = 2015",
        cdesc="franchise", wdesc="fielded a team in 2015"),
   dict(tbl="AwardsPlayers", col="awardID", w="1=1",
        cdesc="award type", wdesc="exist in the awards table"),
   dict(tbl="People", col="birthCountry", w="birthCountry IS NOT NULL",
        cdesc="birth country", wdesc="appear among players"),
  ]),
T("d49_filtered", "distinct_count", DB, "medium", "scalar",
  ["distinct"],
  "SELECT COUNT(DISTINCT {col}) FROM {tbl} WHERE {w}",
  ["How many distinct {cdesc}s {wdesc}?",
   "Count unique {cdesc}s {wdesc}.",
   "How many different {cdesc}s {wdesc}?",
   "Give the unique {cdesc} count {wdesc}."],
  variants=[
   dict(tbl="Batting", col="playerID", w="HR >= 40",
        cdesc="player", wdesc="ever hit 40+ homers in a season"),
   dict(tbl="Salaries", col="playerID",
        w="salary > 20000000", cdesc="player",
        wdesc="ever earned above 20 million in a season"),
   dict(tbl="AllstarFull", col="playerID",
        w="yearID BETWEEN 2010 AND 2019", cdesc="player",
        wdesc="made an All-Star roster in the 2010s"),
   dict(tbl="Managers", col="playerID", w="plyrMgr = 'Y'",
        cdesc="person", wdesc="served as player-managers"),
   dict(tbl="Pitching", col="playerID",
        w="yearID = 2015 AND SV >= 30", cdesc="pitcher",
        wdesc="saved 30+ games in 2015"),
   dict(tbl="CollegePlaying", col="schoolID",
        w="yearID >= 2000", cdesc="school",
        wdesc="produced college players since 2000"),
  ]),
T("d49_per_group", "distinct_count", DB, "hard", "multiset_rows",
  ["distinct"],
  "SELECT {gcol}, COUNT(DISTINCT {dcol}) FROM {tbl} WHERE {w} "
  "GROUP BY {gcol}",
  ["Per {gdesc}, how many distinct {ddesc}s {wdesc}?",
   "Count unique {ddesc}s for each {gdesc} {wdesc}.",
   "For every {gdesc}, report the distinct {ddesc} count {wdesc}.",
   "Show each {gdesc} with its number of different {ddesc}s {wdesc}."],
  variants=[
   dict(tbl="Batting", gcol="teamID", dcol="playerID",
        w="yearID = 2015", gdesc="team", ddesc="player",
        wdesc="who batted in 2015"),
   dict(tbl="Salaries", gcol="teamID", dcol="playerID",
        w="yearID = 2016", gdesc="team", ddesc="paid player",
        wdesc="in 2016"),
   dict(tbl="AwardsPlayers", gcol="awardID", dcol="playerID",
        w="yearID >= 2000", gdesc="award", ddesc="winner",
        wdesc="since 2000"),
   dict(tbl="Batting", gcol="playerID", dcol="teamID",
        w="yearID >= 2010", gdesc="player", ddesc="team",
        wdesc="batted for since 2010"),
   dict(tbl="CollegePlaying", gcol="schoolID", dcol="playerID",
        w="yearID >= 1990", gdesc="school", ddesc="player",
        wdesc="since 1990"),
  ]),
)

# --------------------------------------------------------- derived_metric
add(
T("x49_rate_rows", "derived_metric", DB, "easy", "multiset_rows",
  ["derived_measure"],
  "SELECT {idc}, {expr} FROM {tbl} WHERE {w}",
  ["For {dom}, list {idd} and the {mdesc}.",
   "Show {idd} and {mdesc} for {dom}.",
   "Compute the {mdesc} for {dom}.",
   "What is the {mdesc} for each of {dom}? Include {idd}."],
  variants=[
   dict(idc="playerID", expr="H * 1.0 / AB", tbl="Batting",
        w="yearID = 2019 AND AB >= 500", idd="the player id",
        mdesc="batting average", dom="2019 batters with 500+ at-bats"),
   dict(idc="name", expr="W * 1.0 / G", tbl="Teams",
        w="yearID = 2019", idd="the team name",
        mdesc="win percentage", dom="2019 teams"),
   dict(idc="playerID", expr="SO * 1.0 / 9", tbl="Pitching",
        w="yearID = 2015 AND GS >= 30", idd="the pitcher id",
        mdesc="strikeouts per nine-ish start", dom="2015 workhorses"),
   dict(idc="teamID", expr="R - RA", tbl="Teams",
        w="yearID = 2015", idd="the team id",
        mdesc="run differential", dom="2015 teams"),
  ]),
T("x49_grouped", "derived_metric", DB, "medium", "multiset_rows",
  ["derived_measure"],
  "SELECT {gcol}, {agg} FROM {tbl} WHERE {w} GROUP BY {gcol}",
  ["Per {gdesc}, compute the {mdesc} {wdesc}.",
   "Show each {gdesc}'s {mdesc} {wdesc}.",
   "For every {gdesc} {wdesc}, report the {mdesc}.",
   "Group by {gdesc} and calculate the {mdesc} {wdesc}."],
  variants=[
   dict(gcol="teamID", agg="SUM(H) * 1.0 / SUM(AB)", tbl="Batting",
        w="yearID = 2019 AND AB > 0", gdesc="team",
        mdesc="team batting average", wdesc="for 2019"),
   dict(gcol="teamID", agg="SUM(ER) * 27.0 / SUM(IPouts)",
        tbl="Pitching", w="yearID = 2015 AND IPouts > 0",
        gdesc="team", mdesc="earned run average", wdesc="for 2015"),
   dict(gcol="yearID", agg="SUM(R) - SUM(RA)", tbl="Teams",
        w="franchID = 'NYY'", gdesc="season",
        mdesc="Yankees run differential", wdesc=""),
   dict(gcol="playerID", agg="SUM(HR) * 1.0 / SUM(AB)",
        tbl="Batting", w="yearID >= 2015 AND AB > 0",
        gdesc="player", mdesc="home run rate", wdesc="since 2015"),
   dict(gcol="teamID", agg="SUM(salary) / COUNT(*)", tbl="Salaries",
        w="yearID = 2016", gdesc="team", mdesc="mean salary",
        wdesc="in 2016"),
   dict(gcol="franchID", agg="SUM(W) * 1.0 / SUM(G)", tbl="Teams",
        w="yearID BETWEEN 2010 AND 2019", gdesc="franchise",
        mdesc="decade win percentage", wdesc="for the 2010s"),
  ]),
T("x49_salary_per_win", "derived_metric", DB, "hard",
  "multiset_rows", ["derived_measure", "two_table_join",
                    "nested_aggregation"],
  "WITH pay AS (SELECT teamID, SUM(salary) AS payroll FROM Salaries "
  "WHERE yearID = {yr} GROUP BY teamID) "
  "SELECT t.name, p.payroll * 1.0 / t.W AS cost_per_win FROM Teams t "
  "JOIN pay p ON t.teamID = p.teamID WHERE t.yearID = {yr} AND t.W > 0",
  ["For {yr}, what did each team pay per win? Show team and cost per "
   "win.",
   "Compute {yr} payroll divided by wins for every team.",
   "Show each {yr} team's salary cost per victory.",
   "Which {yr} teams paid how much per win? List name and ratio."],
  variants=[
   dict(yr=2016), dict(yr=2010), dict(yr=2005), dict(yr=2013),
   dict(yr=2000),
  ]),
)

TEMPLATES = TS

import csv
import io
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from database import get_db, init_db, get_player_full, search_players
from projection import project_player, height_to_display, TIERS, SCHOOLS

app = Flask(__name__)
app.secret_key = "hoopscout-dev-key"

# Initialize database on import (needed for gunicorn)
init_db()

# Auto-seed if database is empty (needed for Render where DB resets on deploy)
def _auto_seed():
    try:
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        conn.close()
        if count == 0:
            from seed_florida_current import seed_florida
            seed_florida()
    except Exception:
        pass

_auto_seed()

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DC","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH",
    "NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY"
]

POSITIONS = ["PG", "SG", "SF", "PF", "C"]

HS_DIVISIONS = [
    "1A", "2A", "3A", "4A", "5A", "6A", "7A",
    "Class A", "Class B", "Class C", "Class D",
    "Division I", "Division II", "Division III", "Division IV",
    "Division 1", "Division 2", "Division 3",
    "Division II-AA", "Division II-A",
    "Prep School", "Private/Independent", "Charter", "Public", "Other"
]

AAU_LEVELS = ["Nike EYBL", "Adidas 3SSB", "Under Armour", "Puma Pro", "Independent/Regional", "None"]


@app.context_processor
def inject_globals():
    return {
        "us_states": US_STATES,
        "positions": POSITIONS,
        "hs_divisions": HS_DIVISIONS,
        "aau_levels": AAU_LEVELS,
        "tiers": TIERS,
        "height_to_display": height_to_display,
    }


# ── Dashboard ─────────────────────────────────────────────────────
@app.route("/")
def index():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]

    # Counts by position
    by_position = conn.execute(
        "SELECT position, COUNT(*) as cnt FROM players GROUP BY position ORDER BY position"
    ).fetchall()

    # Counts by state
    by_state = conn.execute(
        "SELECT state, COUNT(*) as cnt FROM players WHERE state IS NOT NULL AND state != '' GROUP BY state ORDER BY cnt DESC LIMIT 15"
    ).fetchall()

    # Counts by HS division
    by_division = conn.execute(
        "SELECT c.school_classification, COUNT(*) as cnt FROM competition c WHERE c.school_classification IS NOT NULL AND c.school_classification != '' GROUP BY c.school_classification ORDER BY cnt DESC"
    ).fetchall()

    # Counts by grad year
    by_year = conn.execute(
        "SELECT grad_year, COUNT(*) as cnt FROM players GROUP BY grad_year ORDER BY grad_year"
    ).fetchall()

    # Recent players
    recent = conn.execute(
        "SELECT * FROM players ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    conn.close()
    return render_template("index.html",
        total=total,
        by_position=[dict(r) for r in by_position],
        by_state=[dict(r) for r in by_state],
        by_division=[dict(r) for r in by_division],
        by_year=[dict(r) for r in by_year],
        recent=[dict(r) for r in recent],
    )


# ── Player List / Search ──────────────────────────────────────────
@app.route("/players")
def players_list():
    query = request.args.get("q", "")
    position = request.args.get("position", "")
    state = request.args.get("state", "")
    grad_year = request.args.get("grad_year", "")
    hs_division = request.args.get("hs_division", "")
    sort_by = request.args.get("sort", "name")

    conn = get_db()

    sql = """
        SELECT p.*, c.school_classification
        FROM players p
        LEFT JOIN competition c ON c.player_id = p.id
        WHERE 1=1
    """
    params = []

    if query:
        sql += " AND (p.first_name LIKE ? OR p.last_name LIKE ? OR p.high_school LIKE ? OR p.aau_program LIKE ?)"
        q = f"%{query}%"
        params.extend([q, q, q, q])
    if position:
        sql += " AND p.position = ?"
        params.append(position)
    if state:
        sql += " AND p.state = ?"
        params.append(state)
    if grad_year:
        sql += " AND p.grad_year = ?"
        params.append(int(grad_year))
    if hs_division:
        sql += " AND c.school_classification = ?"
        params.append(hs_division)

    if sort_by == "name":
        sql += " ORDER BY p.last_name, p.first_name"
    elif sort_by == "state":
        sql += " ORDER BY p.state, p.last_name"
    elif sort_by == "position":
        sql += " ORDER BY p.position, p.last_name"
    elif sort_by == "year":
        sql += " ORDER BY p.grad_year, p.last_name"
    elif sort_by == "division":
        sql += " ORDER BY c.school_classification, p.last_name"
    else:
        sql += " ORDER BY p.last_name, p.first_name"

    players = conn.execute(sql, params).fetchall()

    # Get grad years for filter dropdown
    years = conn.execute("SELECT DISTINCT grad_year FROM players ORDER BY grad_year").fetchall()

    conn.close()

    return render_template("players.html",
        players=[dict(p) for p in players],
        query=query, position=position, state=state,
        grad_year=grad_year, hs_division=hs_division, sort_by=sort_by,
        years=[r["grad_year"] for r in years],
    )


# ── Add Player ────────────────────────────────────────────────────
@app.route("/players/add", methods=["GET", "POST"])
def add_player():
    if request.method == "POST":
        conn = get_db()
        f = request.form

        cur = conn.execute("""
            INSERT INTO players (first_name, last_name, position, height_inches, weight,
                                 wingspan_inches, grad_year, high_school, city, state, aau_program, gpa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["first_name"], f["last_name"], f["position"],
            int(f["height_inches"]), int(f["weight"]) if f.get("weight") else None,
            int(f["wingspan_inches"]) if f.get("wingspan_inches") else None,
            int(f["grad_year"]), f.get("high_school"), f.get("city"), f.get("state"),
            f.get("aau_program"), float(f["gpa"]) if f.get("gpa") else None,
        ))
        player_id = cur.lastrowid

        # Stats
        conn.execute("""
            INSERT INTO stats (player_id, season, games_played, ppg, rpg, apg, spg, bpg,
                              fg_pct, three_pct, ft_pct, topg, minutes_pg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player_id, f.get("season", "2025-26"),
            int(f["games_played"]) if f.get("games_played") else 0,
            float(f["ppg"]) if f.get("ppg") else 0,
            float(f["rpg"]) if f.get("rpg") else 0,
            float(f["apg"]) if f.get("apg") else 0,
            float(f["spg"]) if f.get("spg") else 0,
            float(f["bpg"]) if f.get("bpg") else 0,
            float(f["fg_pct"]) if f.get("fg_pct") else 0,
            float(f["three_pct"]) if f.get("three_pct") else 0,
            float(f["ft_pct"]) if f.get("ft_pct") else 0,
            float(f["topg"]) if f.get("topg") else 0,
            float(f["minutes_pg"]) if f.get("minutes_pg") else 0,
        ))

        # Athleticism
        conn.execute("""
            INSERT INTO athleticism (player_id, speed, vertical, agility, strength, endurance,
                                    vertical_inches, lane_agility_sec, sprint_sec)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player_id,
            int(f.get("speed", 5)), int(f.get("vertical", 5)),
            int(f.get("agility", 5)), int(f.get("strength", 5)),
            int(f.get("endurance", 5)),
            float(f["vertical_inches"]) if f.get("vertical_inches") else None,
            float(f["lane_agility_sec"]) if f.get("lane_agility_sec") else None,
            float(f["sprint_sec"]) if f.get("sprint_sec") else None,
        ))

        # Intangibles
        conn.execute("""
            INSERT INTO intangibles (player_id, basketball_iq, motor, coachability,
                                    leadership, clutch, defensive_instincts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            player_id,
            int(f.get("basketball_iq", 5)), int(f.get("motor", 5)),
            int(f.get("coachability", 5)), int(f.get("leadership", 5)),
            int(f.get("clutch", 5)), int(f.get("defensive_instincts", 5)),
        ))

        # Competition
        conn.execute("""
            INSERT INTO competition (player_id, school_classification, state_rank,
                                    conference_strength, schedule_strength, played_nationally, aau_circuit_level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            player_id, f.get("school_classification"),
            int(f["state_rank"]) if f.get("state_rank") else None,
            int(f.get("conference_strength", 5)),
            int(f.get("schedule_strength", 5)),
            1 if f.get("played_nationally") else 0,
            f.get("aau_circuit_level"),
        ))

        conn.commit()
        conn.close()
        return redirect(url_for("player_detail", player_id=player_id))

    return render_template("add_player.html")


# ── Player Detail / Projection ────────────────────────────────────
@app.route("/players/<int:player_id>")
def player_detail(player_id):
    data = get_player_full(player_id)
    if not data:
        return "Player not found", 404

    projection = project_player(data)
    return render_template("player_detail.html", data=data, projection=projection)


# ── Edit Player ───────────────────────────────────────────────────
@app.route("/players/<int:player_id>/edit", methods=["GET", "POST"])
def edit_player(player_id):
    if request.method == "POST":
        conn = get_db()
        f = request.form

        conn.execute("""
            UPDATE players SET first_name=?, last_name=?, position=?, height_inches=?,
            weight=?, wingspan_inches=?, grad_year=?, high_school=?, city=?, state=?,
            aau_program=?, gpa=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            f["first_name"], f["last_name"], f["position"],
            int(f["height_inches"]), int(f["weight"]) if f.get("weight") else None,
            int(f["wingspan_inches"]) if f.get("wingspan_inches") else None,
            int(f["grad_year"]), f.get("high_school"), f.get("city"), f.get("state"),
            f.get("aau_program"), float(f["gpa"]) if f.get("gpa") else None,
            player_id,
        ))

        # Update latest stats
        existing_stat = conn.execute("SELECT id FROM stats WHERE player_id = ? ORDER BY season DESC LIMIT 1", (player_id,)).fetchone()
        if existing_stat:
            conn.execute("""
                UPDATE stats SET season=?, games_played=?, ppg=?, rpg=?, apg=?, spg=?, bpg=?,
                fg_pct=?, three_pct=?, ft_pct=?, topg=?, minutes_pg=?
                WHERE id=?
            """, (
                f.get("season", "2025-26"),
                int(f["games_played"]) if f.get("games_played") else 0,
                float(f["ppg"]) if f.get("ppg") else 0,
                float(f["rpg"]) if f.get("rpg") else 0,
                float(f["apg"]) if f.get("apg") else 0,
                float(f["spg"]) if f.get("spg") else 0,
                float(f["bpg"]) if f.get("bpg") else 0,
                float(f["fg_pct"]) if f.get("fg_pct") else 0,
                float(f["three_pct"]) if f.get("three_pct") else 0,
                float(f["ft_pct"]) if f.get("ft_pct") else 0,
                float(f["topg"]) if f.get("topg") else 0,
                float(f["minutes_pg"]) if f.get("minutes_pg") else 0,
                existing_stat["id"],
            ))

        # Update competition (strengths now come from scout eval averages, only factual fields here)
        conn.execute("""
            UPDATE competition SET school_classification=?, state_rank=?,
            played_nationally=?, aau_circuit_level=?
            WHERE player_id=?
        """, (
            f.get("school_classification"),
            int(f["state_rank"]) if f.get("state_rank") else None,
            1 if f.get("played_nationally") else 0,
            f.get("aau_circuit_level"),
            player_id,
        ))

        conn.commit()
        conn.close()
        return redirect(url_for("player_detail", player_id=player_id))

    data = get_player_full(player_id)
    if not data:
        return "Player not found", 404
    return render_template("edit_player.html", data=data)


# ── Delete Player ─────────────────────────────────────────────────
@app.route("/players/<int:player_id>/delete", methods=["POST"])
def delete_player(player_id):
    conn = get_db()
    conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("players_list"))


# ── Add Scout Note ────────────────────────────────────────────────
@app.route("/players/<int:player_id>/notes", methods=["POST"])
def add_note(player_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO scout_notes (player_id, scout_name, note) VALUES (?, ?, ?)",
        (player_id, request.form.get("scout_name", ""), request.form["note"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("player_detail", player_id=player_id))


# ── Submit Scout Evaluation ───────────────────────────────────────
@app.route("/players/<int:player_id>/evaluate", methods=["GET", "POST"])
def evaluate_player(player_id):
    if request.method == "POST":
        conn = get_db()
        f = request.form

        scout_name = f.get("scout_name", "").strip()
        if not scout_name:
            flash("Scout name is required.", "danger")
            return redirect(url_for("evaluate_player", player_id=player_id))

        conn.execute("""
            INSERT INTO scout_evaluations (
                player_id, scout_name, eval_date,
                speed, vertical, agility, strength, endurance,
                vertical_inches, lane_agility_sec, sprint_sec,
                basketball_iq, motor, coachability, leadership, clutch, defensive_instincts,
                conference_strength, schedule_strength, notes
            ) VALUES (?, ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player_id, scout_name,
            int(f.get("speed", 5)), int(f.get("vertical", 5)),
            int(f.get("agility", 5)), int(f.get("strength", 5)),
            int(f.get("endurance", 5)),
            float(f["vertical_inches"]) if f.get("vertical_inches") else None,
            float(f["lane_agility_sec"]) if f.get("lane_agility_sec") else None,
            float(f["sprint_sec"]) if f.get("sprint_sec") else None,
            int(f.get("basketball_iq", 5)), int(f.get("motor", 5)),
            int(f.get("coachability", 5)), int(f.get("leadership", 5)),
            int(f.get("clutch", 5)), int(f.get("defensive_instincts", 5)),
            int(f.get("conference_strength", 5)), int(f.get("schedule_strength", 5)),
            f.get("notes", "").strip() or None,
        ))
        conn.commit()
        conn.close()
        flash(f"Evaluation by {scout_name} submitted.", "success")
        return redirect(url_for("player_detail", player_id=player_id))

    data = get_player_full(player_id)
    if not data:
        return "Player not found", 404
    return render_template("evaluate.html", data=data)


# ── Delete Scout Evaluation ───────────────────────────────────────
@app.route("/evaluations/<int:eval_id>/delete", methods=["POST"])
def delete_evaluation(eval_id):
    conn = get_db()
    ev = conn.execute("SELECT player_id FROM scout_evaluations WHERE id = ?", (eval_id,)).fetchone()
    if ev:
        conn.execute("DELETE FROM scout_evaluations WHERE id = ?", (eval_id,))
        conn.commit()
        conn.close()
        return redirect(url_for("player_detail", player_id=ev["player_id"]))
    conn.close()
    return "Not found", 404


# ── Compare Players ───────────────────────────────────────────────
@app.route("/compare")
def compare():
    ids = request.args.getlist("ids")
    players = []
    for pid in ids:
        data = get_player_full(int(pid))
        if data:
            proj = project_player(data)
            players.append({"data": data, "projection": proj})

    # Get all players for the selector
    conn = get_db()
    all_players = conn.execute("SELECT id, first_name, last_name, position FROM players ORDER BY last_name").fetchall()
    conn.close()

    return render_template("compare.html", players=players, all_players=[dict(p) for p in all_players], selected_ids=ids)


# ── Browse by State ───────────────────────────────────────────────
@app.route("/browse/state")
def browse_by_state():
    conn = get_db()
    states = conn.execute("""
        SELECT p.state, COUNT(*) as cnt,
               GROUP_CONCAT(DISTINCT p.position) as positions
        FROM players p
        WHERE p.state IS NOT NULL AND p.state != ''
        GROUP BY p.state ORDER BY p.state
    """).fetchall()
    conn.close()
    return render_template("browse_state.html", states=[dict(s) for s in states])


# ── Browse by HS Division ────────────────────────────────────────
@app.route("/browse/division")
def browse_by_division():
    conn = get_db()
    divisions = conn.execute("""
        SELECT c.school_classification as division, COUNT(*) as cnt
        FROM competition c
        WHERE c.school_classification IS NOT NULL AND c.school_classification != ''
        GROUP BY c.school_classification ORDER BY c.school_classification
    """).fetchall()
    conn.close()
    return render_template("browse_division.html", divisions=[dict(d) for d in divisions])


# ── Browse by Position ────────────────────────────────────────────
@app.route("/browse/position")
def browse_by_position():
    conn = get_db()
    positions = conn.execute("""
        SELECT p.position, COUNT(*) as cnt,
               ROUND(AVG(p.height_inches), 1) as avg_height
        FROM players p
        GROUP BY p.position ORDER BY p.position
    """).fetchall()
    conn.close()
    return render_template("browse_position.html", positions=[dict(p) for p in positions])


# ── CSV Import ────────────────────────────────────────────────────
def parse_height(val):
    """Parse height from various formats: 6'2, 6'2\", 6-2, 74, etc."""
    if not val:
        return None
    val = val.strip().replace('"', '').replace('"', '').replace('"', '')
    # Try feet'inches format
    for sep in ["'", "-", "."]:
        if sep in val:
            parts = val.split(sep)
            try:
                feet = int(parts[0].strip())
                inches = int(parts[1].strip()) if parts[1].strip() else 0
                return feet * 12 + inches
            except (ValueError, IndexError):
                continue
    # Try raw inches
    try:
        n = int(val)
        if n > 12:  # already in inches
            return n
        else:  # probably feet only
            return n * 12
    except ValueError:
        return None


CSV_FIELD_MAP = {
    # Player bio
    "first_name": ["first_name", "first", "firstname", "fname"],
    "last_name": ["last_name", "last", "lastname", "lname", "surname"],
    "position": ["position", "pos"],
    "height": ["height", "ht", "height_inches"],
    "weight": ["weight", "wt", "lbs"],
    "grad_year": ["grad_year", "class", "year", "class_year", "graduation_year", "grad"],
    "high_school": ["high_school", "school", "hs", "highschool"],
    "city": ["city", "town"],
    "state": ["state", "st"],
    "gpa": ["gpa", "grade_point"],
    "aau_program": ["aau_program", "aau", "travel_team", "aau_team"],
    # Stats
    "season": ["season", "yr"],
    "games_played": ["games_played", "gp", "games", "g"],
    "minutes_pg": ["minutes_pg", "mpg", "minutes", "min"],
    "ppg": ["ppg", "pts", "points"],
    "rpg": ["rpg", "reb", "rebounds"],
    "apg": ["apg", "ast", "assists"],
    "spg": ["spg", "stl", "steals"],
    "bpg": ["bpg", "blk", "blocks"],
    "fg_pct": ["fg_pct", "fg%", "fg", "fgpct"],
    "three_pct": ["three_pct", "3pt%", "3pt", "3p%", "three", "threepct", "3fg%"],
    "ft_pct": ["ft_pct", "ft%", "ft", "ftpct"],
    "topg": ["topg", "to", "turnovers", "tov"],
    # Competition
    "hs_division": ["hs_division", "division", "classification", "school_classification", "class_size"],
}


def map_csv_headers(headers):
    """Map CSV column headers to our field names (case-insensitive, flexible)."""
    mapping = {}
    for h in headers:
        clean = h.strip().lower().replace(" ", "_").replace("-", "_")
        for field, aliases in CSV_FIELD_MAP.items():
            if clean in aliases:
                mapping[h] = field
                break
    return mapping


@app.route("/import", methods=["GET", "POST"])
def import_csv():
    if request.method == "POST":
        imported = 0
        skipped = 0
        errors = []

        # Handle file upload or pasted text
        csv_text = None
        if "csv_file" in request.files and request.files["csv_file"].filename:
            file = request.files["csv_file"]
            csv_text = file.stream.read().decode("utf-8-sig")
        elif request.form.get("csv_text", "").strip():
            csv_text = request.form["csv_text"]

        if not csv_text:
            flash("No CSV data provided.", "danger")
            return redirect(url_for("import_csv"))

        reader = csv.DictReader(io.StringIO(csv_text))
        header_map = map_csv_headers(reader.fieldnames or [])

        conn = get_db()

        for i, row in enumerate(reader, start=2):
            try:
                # Map row keys to our fields
                data = {}
                for orig_key, our_key in header_map.items():
                    data[our_key] = row.get(orig_key, "").strip()

                # Required fields
                first_name = data.get("first_name", "")
                last_name = data.get("last_name", "")
                position = data.get("position", "").upper()

                if not first_name or not last_name:
                    skipped += 1
                    errors.append(f"Row {i}: Missing name")
                    continue

                if position not in POSITIONS:
                    # Try to infer
                    pos_map = {"POINT GUARD": "PG", "SHOOTING GUARD": "SG", "SMALL FORWARD": "SF",
                               "POWER FORWARD": "PF", "CENTER": "C", "GUARD": "SG", "FORWARD": "SF",
                               "G": "SG", "F": "SF", "C": "C", "WING": "SF", "BIG": "PF"}
                    position = pos_map.get(position, "SG")

                height = parse_height(data.get("height", ""))
                if not height:
                    height = 72  # default 6'0" if not provided

                weight = None
                if data.get("weight"):
                    try:
                        weight = int(float(data["weight"]))
                    except ValueError:
                        pass

                grad_year = 2026
                if data.get("grad_year"):
                    try:
                        grad_year = int(float(data["grad_year"]))
                    except ValueError:
                        pass

                gpa = None
                if data.get("gpa"):
                    try:
                        gpa = float(data["gpa"])
                    except ValueError:
                        pass

                # Insert player
                cur = conn.execute("""
                    INSERT INTO players (first_name, last_name, position, height_inches, weight,
                        wingspan_inches, grad_year, high_school, city, state, aau_program, gpa)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    first_name, last_name, position, height, weight,
                    None, grad_year,
                    data.get("high_school") or None,
                    data.get("city") or None,
                    data.get("state", "").upper()[:2] if data.get("state") else None,
                    data.get("aau_program") or None,
                    gpa,
                ))
                pid = cur.lastrowid

                # Stats
                def to_float(key):
                    v = data.get(key, "")
                    if not v:
                        return 0
                    try:
                        return float(v.replace("%", ""))
                    except ValueError:
                        return 0

                def to_int(key):
                    v = data.get(key, "")
                    if not v:
                        return 0
                    try:
                        return int(float(v))
                    except ValueError:
                        return 0

                season = data.get("season") or f"{grad_year - 1}-{str(grad_year)[2:]}"
                conn.execute("""
                    INSERT INTO stats (player_id, season, games_played, ppg, rpg, apg, spg, bpg,
                        fg_pct, three_pct, ft_pct, topg, minutes_pg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pid, season, to_int("games_played"),
                    to_float("ppg"), to_float("rpg"), to_float("apg"),
                    to_float("spg"), to_float("bpg"),
                    to_float("fg_pct"), to_float("three_pct"), to_float("ft_pct"),
                    to_float("topg"), to_float("minutes_pg"),
                ))

                # Athleticism — defaults, waiting for scout
                conn.execute("""
                    INSERT INTO athleticism (player_id, speed, vertical, agility, strength, endurance)
                    VALUES (?, 5, 5, 5, 5, 5)
                """, (pid,))

                # Intangibles — defaults, waiting for scout
                conn.execute("""
                    INSERT INTO intangibles (player_id, basketball_iq, motor, coachability,
                        leadership, clutch, defensive_instincts)
                    VALUES (?, 5, 5, 5, 5, 5, 5)
                """, (pid,))

                # Competition
                conn.execute("""
                    INSERT INTO competition (player_id, school_classification, state_rank,
                        conference_strength, schedule_strength, played_nationally, aau_circuit_level)
                    VALUES (?, ?, NULL, 5, 5, 0, NULL)
                """, (pid, data.get("hs_division") or None))

                imported += 1

            except Exception as e:
                skipped += 1
                errors.append(f"Row {i}: {str(e)}")
                continue

        conn.commit()
        conn.close()

        if errors:
            flash(f"Imported {imported} players. Skipped {skipped} rows with errors.", "warning")
        else:
            flash(f"Successfully imported {imported} players!", "success")

        return render_template("import.html", imported=imported, skipped=skipped, errors=errors[:20])

    return render_template("import.html", imported=None, skipped=None, errors=None)


# ── CSV Export ────────────────────────────────────────────────────
@app.route("/export")
def export_csv():
    conn = get_db()
    players = conn.execute("""
        SELECT p.*, s.season, s.games_played, s.ppg, s.rpg, s.apg, s.spg, s.bpg,
               s.fg_pct, s.three_pct, s.ft_pct, s.topg, s.minutes_pg,
               c.school_classification
        FROM players p
        LEFT JOIN stats s ON s.player_id = p.id
        LEFT JOIN competition c ON c.player_id = p.id
        ORDER BY p.last_name, p.first_name
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "first_name", "last_name", "position", "height", "weight",
        "grad_year", "high_school", "city", "state", "gpa", "aau_program",
        "hs_division", "season", "gp", "mpg", "ppg", "rpg", "apg", "spg", "bpg",
        "fg%", "3pt%", "ft%", "topg"
    ])

    for p in players:
        d = dict(p)
        h = d["height_inches"]
        ht_str = f"{h // 12}'{h % 12}" if h else ""
        writer.writerow([
            d["first_name"], d["last_name"], d["position"], ht_str, d["weight"] or "",
            d["grad_year"], d["high_school"] or "", d["city"] or "", d["state"] or "",
            d["gpa"] or "", d["aau_program"] or "",
            d["school_classification"] or "",
            d["season"] or "", d["games_played"] or "", d["minutes_pg"] or "",
            d["ppg"] or "", d["rpg"] or "", d["apg"] or "", d["spg"] or "", d["bpg"] or "",
            d["fg_pct"] or "", d["three_pct"] or "", d["ft_pct"] or "", d["topg"] or "",
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=hoopscout_export.csv"}
    )


# ── Clear Database ────────────────────────────────────────────────
@app.route("/clear-db", methods=["POST"])
def clear_db():
    conn = get_db()
    conn.execute("DELETE FROM scout_notes")
    conn.execute("DELETE FROM competition")
    conn.execute("DELETE FROM intangibles")
    conn.execute("DELETE FROM athleticism")
    conn.execute("DELETE FROM stats")
    conn.execute("DELETE FROM players")
    conn.commit()
    conn.close()
    flash("Database cleared. All players removed.", "info")
    return redirect(url_for("index"))


# ── Seed Florida Players ──────────────────────────────────────────
@app.route("/seed-florida", methods=["POST"])
def seed_florida_route():
    from seed_florida_current import seed_florida
    count = seed_florida()
    flash(f"Seeded {count} current Florida players.", "success")
    return redirect(url_for("index"))


# ── API: Projection for AJAX ──────────────────────────────────────
@app.route("/api/projection/<int:player_id>")
def api_projection(player_id):
    data = get_player_full(player_id)
    if not data:
        return jsonify({"error": "not found"}), 404
    return jsonify(project_player(data))


if __name__ == "__main__":
    init_db()
    app.run(debug=False, port=5001)

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "hoops_scout.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            position TEXT NOT NULL,
            height_inches INTEGER NOT NULL,
            weight INTEGER,
            wingspan_inches INTEGER,
            grad_year INTEGER NOT NULL,
            high_school TEXT,
            city TEXT,
            state TEXT,
            aau_program TEXT,
            gpa REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            games_played INTEGER DEFAULT 0,
            ppg REAL DEFAULT 0,
            rpg REAL DEFAULT 0,
            apg REAL DEFAULT 0,
            spg REAL DEFAULT 0,
            bpg REAL DEFAULT 0,
            fg_pct REAL DEFAULT 0,
            three_pct REAL DEFAULT 0,
            ft_pct REAL DEFAULT 0,
            topg REAL DEFAULT 0,
            minutes_pg REAL DEFAULT 0,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)

    # ── NEW: Scout evaluations (replaces old single-row athleticism/intangibles) ──
    # Each row = one scout's full evaluation of one player
    c.execute("""
        CREATE TABLE IF NOT EXISTS scout_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            scout_name TEXT NOT NULL,
            eval_date TEXT DEFAULT (date('now')),
            -- Athleticism
            speed INTEGER CHECK(speed BETWEEN 1 AND 10),
            vertical INTEGER CHECK(vertical BETWEEN 1 AND 10),
            agility INTEGER CHECK(agility BETWEEN 1 AND 10),
            strength INTEGER CHECK(strength BETWEEN 1 AND 10),
            endurance INTEGER CHECK(endurance BETWEEN 1 AND 10),
            -- Measurables (optional hard numbers)
            vertical_inches REAL,
            lane_agility_sec REAL,
            sprint_sec REAL,
            -- Intangibles
            basketball_iq INTEGER CHECK(basketball_iq BETWEEN 1 AND 10),
            motor INTEGER CHECK(motor BETWEEN 1 AND 10),
            coachability INTEGER CHECK(coachability BETWEEN 1 AND 10),
            leadership INTEGER CHECK(leadership BETWEEN 1 AND 10),
            clutch INTEGER CHECK(clutch BETWEEN 1 AND 10),
            defensive_instincts INTEGER CHECK(defensive_instincts BETWEEN 1 AND 10),
            -- Competition assessment
            conference_strength INTEGER CHECK(conference_strength BETWEEN 1 AND 10),
            schedule_strength INTEGER CHECK(schedule_strength BETWEEN 1 AND 10),
            -- Overall scout note for this eval
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)

    # Keep old tables for migration compatibility but they're no longer primary
    c.execute("""
        CREATE TABLE IF NOT EXISTS athleticism (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER UNIQUE NOT NULL,
            speed INTEGER DEFAULT 5 CHECK(speed BETWEEN 1 AND 10),
            vertical INTEGER DEFAULT 5 CHECK(vertical BETWEEN 1 AND 10),
            agility INTEGER DEFAULT 5 CHECK(agility BETWEEN 1 AND 10),
            strength INTEGER DEFAULT 5 CHECK(strength BETWEEN 1 AND 10),
            endurance INTEGER DEFAULT 5 CHECK(endurance BETWEEN 1 AND 10),
            vertical_inches REAL,
            lane_agility_sec REAL,
            sprint_sec REAL,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS intangibles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER UNIQUE NOT NULL,
            basketball_iq INTEGER DEFAULT 5 CHECK(basketball_iq BETWEEN 1 AND 10),
            motor INTEGER DEFAULT 5 CHECK(motor BETWEEN 1 AND 10),
            coachability INTEGER DEFAULT 5 CHECK(coachability BETWEEN 1 AND 10),
            leadership INTEGER DEFAULT 5 CHECK(leadership BETWEEN 1 AND 10),
            clutch INTEGER DEFAULT 5 CHECK(clutch BETWEEN 1 AND 10),
            defensive_instincts INTEGER DEFAULT 5 CHECK(defensive_instincts BETWEEN 1 AND 10),
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS competition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER UNIQUE NOT NULL,
            school_classification TEXT,
            state_rank INTEGER,
            conference_strength INTEGER DEFAULT 5 CHECK(conference_strength BETWEEN 1 AND 10),
            schedule_strength INTEGER DEFAULT 5 CHECK(schedule_strength BETWEEN 1 AND 10),
            played_nationally INTEGER DEFAULT 0,
            aau_circuit_level TEXT,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS scout_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            scout_name TEXT,
            note TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


def get_eval_averages(player_id, conn=None):
    """
    Get averaged scout evaluations for a player.
    Returns dict with averages and individual evaluations list.
    """
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True

    evals = conn.execute(
        "SELECT * FROM scout_evaluations WHERE player_id = ? ORDER BY created_at DESC",
        (player_id,)
    ).fetchall()

    if close_conn:
        conn.close()

    eval_list = [dict(e) for e in evals]
    num_evals = len(eval_list)

    if num_evals == 0:
        return {
            "num_evaluations": 0,
            "evaluations": [],
            "averages": None,
            "scouted": False,
        }

    # Calculate averages for all rating fields
    rating_fields = [
        "speed", "vertical", "agility", "strength", "endurance",
        "basketball_iq", "motor", "coachability", "leadership", "clutch",
        "defensive_instincts", "conference_strength", "schedule_strength",
    ]
    measurable_fields = ["vertical_inches", "lane_agility_sec", "sprint_sec"]

    averages = {}
    for field in rating_fields:
        values = [e[field] for e in eval_list if e[field] is not None]
        averages[field] = round(sum(values) / len(values), 1) if values else None

    for field in measurable_fields:
        values = [e[field] for e in eval_list if e[field] is not None]
        averages[field] = round(sum(values) / len(values), 1) if values else None

    return {
        "num_evaluations": num_evals,
        "evaluations": eval_list,
        "averages": averages,
        "scouted": True,
    }


def get_player_full(player_id):
    conn = get_db()
    player = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if not player:
        conn.close()
        return None

    stats = conn.execute(
        "SELECT * FROM stats WHERE player_id = ? ORDER BY season DESC", (player_id,)
    ).fetchall()

    competition = conn.execute(
        "SELECT * FROM competition WHERE player_id = ?", (player_id,)
    ).fetchone()

    notes = conn.execute(
        "SELECT * FROM scout_notes WHERE player_id = ? ORDER BY created_at DESC",
        (player_id,),
    ).fetchall()

    eval_data = get_eval_averages(player_id, conn)

    conn.close()

    # Build athleticism/intangibles from eval averages for projection engine compatibility
    avgs = eval_data["averages"]
    if avgs and eval_data["scouted"]:
        athleticism = {
            "speed": avgs.get("speed") or 5,
            "vertical": avgs.get("vertical") or 5,
            "agility": avgs.get("agility") or 5,
            "strength": avgs.get("strength") or 5,
            "endurance": avgs.get("endurance") or 5,
            "vertical_inches": avgs.get("vertical_inches"),
            "lane_agility_sec": avgs.get("lane_agility_sec"),
            "sprint_sec": avgs.get("sprint_sec"),
        }
        intangibles = {
            "basketball_iq": avgs.get("basketball_iq") or 5,
            "motor": avgs.get("motor") or 5,
            "coachability": avgs.get("coachability") or 5,
            "leadership": avgs.get("leadership") or 5,
            "clutch": avgs.get("clutch") or 5,
            "defensive_instincts": avgs.get("defensive_instincts") or 5,
        }
        # Update competition strengths from scout averages
        if competition:
            comp_dict = dict(competition)
            if avgs.get("conference_strength"):
                comp_dict["conference_strength"] = round(avgs["conference_strength"])
            if avgs.get("schedule_strength"):
                comp_dict["schedule_strength"] = round(avgs["schedule_strength"])
            competition = comp_dict
    else:
        athleticism = None
        intangibles = None

    return {
        "player": dict(player),
        "stats": [dict(s) for s in stats],
        "athleticism": athleticism,
        "intangibles": intangibles,
        "competition": dict(competition) if competition and not isinstance(competition, dict) else competition,
        "notes": [dict(n) for n in notes],
        "eval_data": eval_data,
    }


def search_players(query="", position="", state="", grad_year="", tier=""):
    conn = get_db()
    sql = "SELECT * FROM players WHERE 1=1"
    params = []

    if query:
        sql += " AND (first_name LIKE ? OR last_name LIKE ? OR high_school LIKE ?)"
        q = f"%{query}%"
        params.extend([q, q, q])
    if position:
        sql += " AND position = ?"
        params.append(position)
    if state:
        sql += " AND state = ?"
        params.append(state)
    if grad_year:
        sql += " AND grad_year = ?"
        params.append(int(grad_year))

    sql += " ORDER BY last_name, first_name"
    players = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(p) for p in players]


if __name__ == "__main__":
    init_db()
    print("Database initialized.")

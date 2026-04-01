"""
Basketball Projection Engine

Calculates a composite score from production, size/athleticism,
competition level, and intangibles — then maps it to a collegiate tier
and suggests conferences/schools.
"""

# ── Tier definitions ──────────────────────────────────────────────
TIERS = {
    1: {
        "label": "D1 High-Major",
        "conferences": ["ACC", "Big Ten", "Big 12", "SEC", "Big East", "AAC", "Mountain West"],
        "min_score": 72,
    },
    2: {
        "label": "D1 Mid-Major",
        "conferences": ["A-10", "WCC", "MVC", "CAA", "Horizon", "MAC", "Sun Belt", "C-USA"],
        "min_score": 58,
    },
    3: {
        "label": "D1 Low-Major",
        "conferences": ["Patriot", "MAAC", "NEC", "America East", "Big South", "SWAC", "MEAC", "Southland"],
        "min_score": 45,
    },
    4: {
        "label": "Division II",
        "conferences": ["PSAC", "GLIAC", "Lone Star", "Gulf South", "CIAA", "Sunshine State"],
        "min_score": 30,
    },
    5: {
        "label": "D3 / NAIA",
        "conferences": ["ODAC", "UAA", "CCIW", "SCIAC", "NACC", "Wolverine-Hoosier"],
        "min_score": 0,
    },
}

# ── Size benchmarks by position (inches) ─────────────────────────
# (ideal_height, min_viable_height, ideal_wingspan)
SIZE_BENCHMARKS = {
    "PG": (74, 70, 78),
    "SG": (77, 73, 81),
    "SF": (79, 76, 83),
    "PF": (81, 78, 85),
    "C":  (83, 80, 87),
}

# ── Competition level multipliers ─────────────────────────────────
COMPETITION_MULTIPLIERS = {
    1: 0.70,   # very weak
    2: 0.78,
    3: 0.85,
    4: 0.90,
    5: 0.95,   # average
    6: 1.00,
    7: 1.05,
    8: 1.10,
    9: 1.15,
    10: 1.20,  # elite (national schedule / top prep)
}

# ── Classification strength mapping ──────────────────────────────
# Maps HS classification to a base competition strength score (1-10)
# Used when no scout evaluations exist to estimate competition level
CLASSIFICATION_STRENGTH = {
    "Prep School": 9,
    "7A": 8, "6A": 7, "5A": 6, "4A": 5, "3A": 5,
    "2A": 4, "1A": 3,
    "Class A": 5, "Class B": 4, "Class C": 3, "Class D": 2,
    "Division I": 7, "Division II": 6, "Division III": 5, "Division IV": 4,
    "Division 1": 7, "Division 2": 6, "Division 3": 5,
    "Division II-AA": 6, "Division II-A": 5,
    "Private/Independent": 6, "Charter": 5, "Public": 5, "Other": 5,
}

# ── AAU circuit level bonuses ─────────────────────────────────────
AAU_BONUSES = {
    "Nike EYBL": 12,
    "Adidas 3SSB": 10,
    "Under Armour": 9,
    "Puma Pro": 8,
    "Independent/Regional": 3,
    "None": 0,
}

# ── School database (sample — expandable) ────────────────────────
SCHOOLS = [
    # Tier 1 — High Major
    {"name": "Villanova", "conference": "Big East", "tier": 1, "state": "PA", "style": "disciplined"},
    {"name": "Creighton", "conference": "Big East", "tier": 1, "state": "NE", "style": "shooting"},
    {"name": "UConn", "conference": "Big East", "tier": 1, "state": "CT", "style": "balanced"},
    {"name": "St. John's", "conference": "Big East", "tier": 1, "state": "NY", "style": "athletic"},
    {"name": "Xavier", "conference": "Big East", "tier": 1, "state": "OH", "style": "balanced"},
    {"name": "Duke", "conference": "ACC", "tier": 1, "state": "NC", "style": "versatile"},
    {"name": "North Carolina", "conference": "ACC", "tier": 1, "state": "NC", "style": "fast-paced"},
    {"name": "Virginia", "conference": "ACC", "tier": 1, "state": "VA", "style": "disciplined"},
    {"name": "Michigan State", "conference": "Big Ten", "tier": 1, "state": "MI", "style": "physical"},
    {"name": "Purdue", "conference": "Big Ten", "tier": 1, "state": "IN", "style": "size-oriented"},
    {"name": "Kansas", "conference": "Big 12", "tier": 1, "state": "KS", "style": "versatile"},
    {"name": "Baylor", "conference": "Big 12", "tier": 1, "state": "TX", "style": "athletic"},
    {"name": "Houston", "conference": "Big 12", "tier": 1, "state": "TX", "style": "defensive"},
    {"name": "Kentucky", "conference": "SEC", "tier": 1, "state": "KY", "style": "athletic"},
    {"name": "Auburn", "conference": "SEC", "tier": 1, "state": "AL", "style": "fast-paced"},
    {"name": "Tennessee", "conference": "SEC", "tier": 1, "state": "TN", "style": "defensive"},
    {"name": "Alabama", "conference": "SEC", "tier": 1, "state": "AL", "style": "shooting"},
    {"name": "Florida", "conference": "SEC", "tier": 1, "state": "FL", "style": "balanced"},
    {"name": "Memphis", "conference": "AAC", "tier": 1, "state": "TN", "style": "athletic"},
    {"name": "San Diego State", "conference": "Mountain West", "tier": 1, "state": "CA", "style": "defensive"},

    # Tier 2 — Mid Major
    {"name": "VCU", "conference": "A-10", "tier": 2, "state": "VA", "style": "pressing"},
    {"name": "Dayton", "conference": "A-10", "tier": 2, "state": "OH", "style": "balanced"},
    {"name": "Saint Louis", "conference": "A-10", "tier": 2, "state": "MO", "style": "disciplined"},
    {"name": "Richmond", "conference": "A-10", "tier": 2, "state": "VA", "style": "shooting"},
    {"name": "George Mason", "conference": "A-10", "tier": 2, "state": "VA", "style": "balanced"},
    {"name": "Gonzaga", "conference": "WCC", "tier": 2, "state": "WA", "style": "versatile"},
    {"name": "Saint Mary's", "conference": "WCC", "tier": 2, "state": "CA", "style": "disciplined"},
    {"name": "Loyola Chicago", "conference": "MVC", "tier": 2, "state": "IL", "style": "disciplined"},
    {"name": "Drake", "conference": "MVC", "tier": 2, "state": "IA", "style": "balanced"},
    {"name": "Bradley", "conference": "MVC", "tier": 2, "state": "IL", "style": "physical"},
    {"name": "Charleston", "conference": "CAA", "tier": 2, "state": "SC", "style": "balanced"},
    {"name": "Hofstra", "conference": "CAA", "tier": 2, "state": "NY", "style": "fast-paced"},
    {"name": "Toledo", "conference": "MAC", "tier": 2, "state": "OH", "style": "balanced"},
    {"name": "Ohio", "conference": "MAC", "tier": 2, "state": "OH", "style": "fast-paced"},
    {"name": "UCF", "conference": "Big 12", "tier": 2, "state": "FL", "style": "athletic"},
    {"name": "USF", "conference": "AAC", "tier": 2, "state": "FL", "style": "athletic"},

    # Tier 3 — Low Major
    {"name": "Colgate", "conference": "Patriot", "tier": 3, "state": "NY", "style": "shooting"},
    {"name": "Bucknell", "conference": "Patriot", "tier": 3, "state": "PA", "style": "disciplined"},
    {"name": "Navy", "conference": "Patriot", "tier": 3, "state": "MD", "style": "physical"},
    {"name": "Iona", "conference": "MAAC", "tier": 3, "state": "NY", "style": "fast-paced"},
    {"name": "Siena", "conference": "MAAC", "tier": 3, "state": "NY", "style": "balanced"},
    {"name": "Fairfield", "conference": "MAAC", "tier": 3, "state": "CT", "style": "balanced"},
    {"name": "Bryant", "conference": "America East", "tier": 3, "state": "RI", "style": "balanced"},
    {"name": "Vermont", "conference": "America East", "tier": 3, "state": "VT", "style": "disciplined"},
    {"name": "UMBC", "conference": "America East", "tier": 3, "state": "MD", "style": "balanced"},
    {"name": "Wagner", "conference": "NEC", "tier": 3, "state": "NY", "style": "balanced"},
    {"name": "Merrimack", "conference": "NEC", "tier": 3, "state": "MA", "style": "physical"},
    {"name": "FGCU", "conference": "ASUN", "tier": 3, "state": "FL", "style": "athletic"},
    {"name": "Jacksonville", "conference": "ASUN", "tier": 3, "state": "FL", "style": "balanced"},
    {"name": "Stetson", "conference": "ASUN", "tier": 3, "state": "FL", "style": "balanced"},

    # Tier 4 — D2
    {"name": "Northwest Missouri State", "conference": "MIAA", "tier": 4, "state": "MO", "style": "balanced"},
    {"name": "West Texas A&M", "conference": "Lone Star", "tier": 4, "state": "TX", "style": "fast-paced"},
    {"name": "Flagler", "conference": "Peach Belt", "tier": 4, "state": "FL", "style": "shooting"},
    {"name": "Bentley", "conference": "NE-10", "tier": 4, "state": "MA", "style": "disciplined"},
    {"name": "Assumption", "conference": "NE-10", "tier": 4, "state": "MA", "style": "balanced"},
    {"name": "Le Moyne", "conference": "NE-10", "tier": 4, "state": "NY", "style": "balanced"},
    {"name": "Dominican (NY)", "conference": "CACC", "tier": 4, "state": "NY", "style": "fast-paced"},
    {"name": "Pace", "conference": "NE-10", "tier": 4, "state": "NY", "style": "balanced"},
    {"name": "Nova Southeastern", "conference": "Sunshine State", "tier": 4, "state": "FL", "style": "balanced"},
    {"name": "Tampa", "conference": "Sunshine State", "tier": 4, "state": "FL", "style": "athletic"},
    {"name": "Barry", "conference": "Sunshine State", "tier": 4, "state": "FL", "style": "balanced"},

    # Tier 5 — D3/NAIA
    {"name": "Randolph-Macon", "conference": "ODAC", "tier": 5, "state": "VA", "style": "balanced"},
    {"name": "Christopher Newport", "conference": "CAC", "tier": 5, "state": "VA", "style": "disciplined"},
    {"name": "Emory", "conference": "UAA", "tier": 5, "state": "GA", "style": "disciplined"},
    {"name": "Wash U", "conference": "UAA", "tier": 5, "state": "MO", "style": "balanced"},
    {"name": "Amherst", "conference": "NESCAC", "tier": 5, "state": "MA", "style": "balanced"},
    {"name": "Williams", "conference": "NESCAC", "tier": 5, "state": "MA", "style": "disciplined"},
]


def height_to_display(inches):
    if not inches:
        return "N/A"
    return f"{inches // 12}'{inches % 12}\""


def calc_production_score(stats):
    """Score production on a 0-100 scale from per-game stats."""
    if not stats:
        return 30  # no stats = below average default

    s = stats[0] if isinstance(stats, list) else stats

    ppg = s.get("ppg", 0) or 0
    rpg = s.get("rpg", 0) or 0
    apg = s.get("apg", 0) or 0
    spg = s.get("spg", 0) or 0
    bpg = s.get("bpg", 0) or 0
    fg_pct = s.get("fg_pct", 0) or 0
    three_pct = s.get("three_pct", 0) or 0
    ft_pct = s.get("ft_pct", 0) or 0

    # Weighted composite — scoring is king but efficiency matters
    raw = (
        ppg * 2.5
        + rpg * 1.8
        + apg * 2.0
        + spg * 2.5
        + bpg * 2.5
        + fg_pct * 0.3
        + three_pct * 0.2
        + ft_pct * 0.15
    )

    # Normalize to 0-100 (a 25ppg/8rpg/5apg elite stat line ≈ 95+)
    score = min(100, raw * 0.85)
    return round(score, 1)


def calc_size_score(player):
    """Score size/measurables on a 0-100 scale relative to position."""
    position = player.get("position", "SG")
    height = player.get("height_inches", 72)
    wingspan = player.get("wingspan_inches")

    ideal_h, min_h, ideal_ws = SIZE_BENCHMARKS.get(position, (77, 73, 81))

    # Height component (0-60)
    if height >= ideal_h + 2:
        h_score = 65  # oversized for position = bonus
    elif height >= ideal_h:
        h_score = 60
    elif height >= min_h:
        h_score = 35 + 25 * ((height - min_h) / max(1, ideal_h - min_h))
    else:
        h_score = max(10, 35 - (min_h - height) * 5)

    # Wingspan component (0-40)
    if wingspan:
        ws_diff = wingspan - height
        if ws_diff >= (ideal_ws - ideal_h):
            w_score = 40
        elif ws_diff >= 2:
            w_score = 28 + 12 * (ws_diff - 2) / max(1, (ideal_ws - ideal_h) - 2)
        else:
            w_score = max(10, 28 - (2 - ws_diff) * 4)
    else:
        w_score = 25  # neutral if unknown

    return round(h_score + w_score, 1)


def calc_athleticism_score(ath):
    """Score athleticism on 0-100 from 1-10 ratings."""
    if not ath:
        return 50  # neutral default

    ratings = [
        ath.get("speed", 5) or 5,
        ath.get("vertical", 5) or 5,
        ath.get("agility", 5) or 5,
        ath.get("strength", 5) or 5,
        ath.get("endurance", 5) or 5,
    ]
    return round(sum(ratings) / len(ratings) * 10, 1)


def calc_intangibles_score(intang):
    """Score intangibles on 0-100 from 1-10 ratings."""
    if not intang:
        return 50

    ratings = [
        intang.get("basketball_iq", 5) or 5,
        intang.get("motor", 5) or 5,
        intang.get("coachability", 5) or 5,
        intang.get("leadership", 5) or 5,
        intang.get("clutch", 5) or 5,
        intang.get("defensive_instincts", 5) or 5,
    ]
    return round(sum(ratings) / len(ratings) * 10, 1)


def _is_scouted(player_data):
    """Check if a player has scout evaluations submitted."""
    eval_data = player_data.get("eval_data")
    if eval_data and eval_data.get("scouted"):
        return True
    return False


def _get_competition_strength(player_data):
    """
    Get competition strength from scout evals or estimate from classification/AAU.
    Returns a multiplier and bonus points.
    """
    comp = player_data.get("competition")
    if not comp:
        return 0.95, 0

    # Competition multiplier
    conf_strength = comp.get("conference_strength")
    sched_strength = comp.get("schedule_strength")

    if conf_strength and sched_strength:
        avg_comp = (conf_strength + sched_strength) / 2
    else:
        # Estimate from classification
        classification = comp.get("school_classification", "")
        avg_comp = CLASSIFICATION_STRENGTH.get(classification, 5)

    mult = COMPETITION_MULTIPLIERS.get(round(avg_comp), 0.95)

    # AAU circuit bonus — playing on a top circuit is a major signal
    aau_level = comp.get("aau_circuit_level", "")
    aau_bonus = AAU_BONUSES.get(aau_level, 0)

    # Played nationally bonus
    national_bonus = 6 if comp.get("played_nationally") else 0

    return mult, aau_bonus + national_bonus


def calc_composite_score(player_data):
    """
    Calculate the overall composite score.

    SCOUTED weights (intangibles are king — separates levels):
      - Intangibles:      30%  (IQ, motor, coachability, leadership, clutch, defense)
      - Athleticism:      25%  (speed, vert, agility, strength, endurance)
      - Production:       25%  (stats adjusted by competition)
      - Size:             20%  (height/wingspan relative to position)

    PRELIMINARY (unscouted) — stats + size + competition context:
      - Production: 45%, Size: 30%, Competition context bonus added
    """
    production = calc_production_score(player_data.get("stats"))
    size = calc_size_score(player_data.get("player", {}))
    athleticism = calc_athleticism_score(player_data.get("athleticism"))
    intangibles = calc_intangibles_score(player_data.get("intangibles"))

    scouted = _is_scouted(player_data)
    mult, context_bonus = _get_competition_strength(player_data)

    adjusted_production = min(100, production * mult)

    if scouted:
        # Full projection — intangibles weigh the most
        composite = (
            intangibles * 0.30
            + athleticism * 0.25
            + adjusted_production * 0.25
            + size * 0.20
        )
    else:
        # Preliminary projection — stats + size + competition context
        # Context bonus (AAU level + national play) accounts for what stats alone miss:
        # A role player at Montverde with Nike EYBL experience is way better than
        # a stat-stuffer at a tiny school
        composite = (
            adjusted_production * 0.45
            + size * 0.30
        )

    # Add competition context bonus (AAU circuit + national play)
    composite += context_bonus

    composite = min(100, composite)

    return {
        "composite": round(composite, 1),
        "production": round(production, 1),
        "adjusted_production": round(adjusted_production, 1),
        "size": round(size, 1),
        "athleticism": round(athleticism, 1),
        "intangibles": round(intangibles, 1),
        "competition_multiplier": round(mult, 2),
        "context_bonus": context_bonus,
        "scouted": scouted,
    }


def get_tier(composite_score):
    """Return the best tier (lowest number) the score qualifies for."""
    for tier_num in sorted(TIERS.keys()):
        if composite_score >= TIERS[tier_num]["min_score"]:
            return tier_num, TIERS[tier_num]["label"]
    return 5, TIERS[5]["label"]


def suggest_schools(player_data, scores, tier, limit=8):
    """Suggest schools based on tier, position, and state proximity."""
    player = player_data.get("player", {})
    state = player.get("state", "")

    # Get schools in the player's tier, +/- 1 tier for flexibility
    candidates = [s for s in SCHOOLS if abs(s["tier"] - tier) <= 1]

    # Score each candidate
    scored = []
    for school in candidates:
        fit = 0
        # Tier match is most important
        if school["tier"] == tier:
            fit += 50
        elif school["tier"] == tier - 1:
            fit += 20  # reach school
        else:
            fit += 35  # safety school

        # State proximity bonus
        if school["state"] == state:
            fit += 25
        # Neighboring state heuristic would go here

        scored.append({**school, "fit_score": fit})

    scored.sort(key=lambda x: (-x["fit_score"], x["name"]))
    return scored[:limit]


def project_player(player_data):
    """Full projection: scores, tier, and school suggestions."""
    scores = calc_composite_score(player_data)
    tier_num, tier_label = get_tier(scores["composite"])
    schools = suggest_schools(player_data, scores, tier_num)

    return {
        "scores": scores,
        "tier": tier_num,
        "tier_label": tier_label,
        "suggested_schools": schools,
    }

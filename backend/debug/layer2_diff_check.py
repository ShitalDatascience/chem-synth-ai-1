import psycopg2
import json
from collections import Counter


# =========================
# CONFIG (NO ARCH CHANGE)
# =========================
DB_CONFIG = {
    "dbname": "chembl",
    "user": "shitalkale",
    "host": "localhost",
    "port": 5432
}

MOLREGNO = 1280  # aspirin


# =========================
# LOAD PYTHON OUTPUT
# =========================
def load_python_output():
    with open("aspirin_output.json", "r") as f:
        return json.load(f)


# =========================
# FETCH SQL DATA (GROUND TRUTH)
# =========================
def fetch_sql_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    query = """
    SELECT
        act.standard_type,
        act.standard_value,
        act.standard_units,
        td.pref_name
    FROM activities act
    JOIN assays a ON act.assay_id = a.assay_id
    JOIN target_dictionary td ON a.tid = td.tid
    WHERE act.molregno = %s
    """

    cur.execute(query, (MOLREGNO,))
    rows = cur.fetchall()
    conn.close()
    return rows


# =========================
# FILTER VALID POTENCY
# =========================
VALID_TYPES = {"IC50", "Ki", "EC50", "AC50", "ED50"}

def filter_valid(rows):
    return [
        r for r in rows
        if r[0] in VALID_TYPES
        and r[1] is not None
        and 0 < float(r[1]) <= 1e9
        and r[2] == "nM"
    ]


# =========================
# COX DETECTION
# =========================
def is_cox(target):
    t = (target or "").lower()
    return (
        "cox" in t or
        "ptgs" in t or
        "cyclooxygenase" in t
    )


def extract_cox(rows):
    return [r for r in rows if is_cox(r[3])]


# =========================
# DIFF ENGINE
# =========================
def run_diff(sql_rows, py_output):

    print("\n========== LAYER 2 FULL DIFF REPORT ==========\n")

    # -------------------------
    # SQL processing
    # -------------------------
    sql_cox = extract_cox(sql_rows)
    sql_valid = filter_valid(sql_cox)

    sql_targets = Counter([r[3] for r in sql_cox])
    sql_types = Counter([r[0] for r in sql_rows])

    # -------------------------
    # Python processing
    # -------------------------
    py_top_targets = py_output["evidence_summary"]["top_targets"]
    py_potency = py_output["evidence_summary"].get("potency_stats_by_target", [])
    py_cell = py_output["evidence_summary"].get("cell_line_activity", [])

    py_targets = Counter([t["target"] for t in py_top_targets])

    # =========================
    # CHECK 1: COX consistency
    # =========================
    print("CHECK 1 - COX DETECTION")

    print("SQL COX targets:")
    for k, v in sql_targets.items():
        print(" -", k, ":", v)

    print("\nPY COX targets:")
    for k, v in py_targets.items():
        if "cox" in k.lower():
            print(" -", k, ":", v)

    cox_ok = any("cox" in k.lower() for k in py_targets)

    # =========================
    # CHECK 2: endpoint validity
    # =========================
    print("\nCHECK 2 - SQL ENDPOINT TYPES")
    for k, v in sql_types.items():
        print(" -", k, ":", v)

    # =========================
    # CHECK 3: potency alignment
    # =========================
    print("\nCHECK 3 - POTENCY COMPARISON")
    print("SQL valid potency rows:", len(sql_valid))
    print("PY potency entries:", len(py_potency))

    potency_ok = abs(len(sql_valid) - len(py_potency)) <= 3

    # =========================
    # CHECK 4: cell line isolation
    # =========================
    print("\nCHECK 4 - CELL LINE EXTRACTION")
    print("Count:", len(py_cell))
    print("Samples:", [c["target"] for c in py_cell[:5]])

    cell_ok = len(py_cell) > 0

    # =========================
    # FINAL REPORT
    # =========================
    print("\n========== FINAL RESULT ==========")

    issues = []

    if not cox_ok:
        issues.append("COX missing in Python output")

    if not potency_ok:
        issues.append("Potency mismatch (SQL vs Python)")

    if not cell_ok:
        issues.append("Cell line extraction missing")

    if issues:
        print("FAIL")
        for i in issues:
            print(" -", i)
    else:
        print("PASS - SQL and Python aligned")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    sql_rows = fetch_sql_data()
    py_output = load_python_output()

    run_diff(sql_rows, py_output)

from flask import Flask, jsonify, request, send_from_directory, render_template
import os, csv, json, sqlite3

app = Flask(__name__)

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "0423_contacts.csv")
IMAGE_ROOT = BASE_DIR
MET_FILE  = os.path.join(BASE_DIR, "met_status.json")

people_data = {}

def name_to_key(full_name, ext=".png"):
    return full_name.strip().replace(" ", "_") + ext

def load_people_data():
    global people_data
    people_data = {}
    if not os.path.exists(DATA_FILE):
        print(f"[WARNING] 找不到 {DATA_FILE}")
        return
    with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k.strip(): v for k, v in row.items()}
            first = row.get("First name", row.get("First Name", "")).strip()
            last  = row.get("Last Name",  row.get("Last name",  "")).strip()
            name  = f"{first} {last}".strip()
            if not name:
                continue
            for ext in (".png", ".jpg"):
                key = name_to_key(name, ext)
                people_data[key] = {
                    "name":      name,
                    "first_name": first,
                    "last_name":  last,
                    "company":   row.get("Company Name",             ""),
                    "role":      row.get("Role",                     ""),
                    "pipeline":  row.get("Sale's pipeline progress", ""),
                    "bd":        row.get("BD in charge",             ""),
                    "isr":       row.get("ISR in charge",            ""),
                    "linkedin":  row.get("Linkedin",                 ""),
                    "app_name":  row.get("App name",                 ""),
                    "mmp":       row.get("MMP",                      ""),
                    "daily_dl":  row.get("Daily downloads",          ""),
                    "dau":       row.get("DAU",                      ""),
                }
    print(f"[INFO] 載入 {len(people_data)//2} 筆")

def load_met():
    if os.path.exists(MET_FILE):
        with open(MET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_met(data):
    with open(MET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

load_people_data()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_folders")
def get_folders():
    folders = sorted([
        f for f in os.listdir(IMAGE_ROOT)
        if os.path.isdir(os.path.join(IMAGE_ROOT, f))
        and any(fn.endswith((".jpg", ".png")) for fn in os.listdir(os.path.join(IMAGE_ROOT, f)))
    ], reverse=True)
    return jsonify(folders)

@app.route("/get_images")
def get_images():
    folder = request.args.get("folder", "")
    folder_path = os.path.join(IMAGE_ROOT, folder)
    if not folder or not os.path.exists(folder_path):
        return jsonify([])

    met = load_met()
    result = []
    for fname in sorted(os.listdir(folder_path)):
        if not fname.endswith((".jpg", ".png")):
            continue
        info = people_data.get(fname, {})
        clean_name = fname.replace(".png","").replace(".jpg","").replace("_"," ")
        dl_raw = info.get("daily_dl","")
        try:
            dl_num = float(str(dl_raw).replace(",",""))
        except Exception:
            dl_num = 0
        result.append({
            "file":       fname,
            "name":       info.get("name",       clean_name),
            "first_name": info.get("first_name", clean_name.split(" ")[0]),
            "last_name":  info.get("last_name",  ""),
            "company":    info.get("company",    ""),
            "role":       info.get("role",       ""),
            "pipeline":   info.get("pipeline",   ""),
            "bd":         info.get("bd",         ""),
            "isr":        info.get("isr",        ""),
            "linkedin":   info.get("linkedin",   ""),
            "app_name":   info.get("app_name",   ""),
            "mmp":        info.get("mmp",        ""),
            "daily_dl":   dl_raw,
            "daily_dl_num": dl_num,
            "dau":        info.get("dau",        ""),
            "img_src":    f"/{folder}/{fname}",
            "met":        met.get(fname, False),
        })
    return jsonify(result)

@app.route("/toggle_met", methods=["POST"])
def toggle_met():
    data = request.get_json()
    fname = data.get("file","")
    if not fname:
        return jsonify({"ok": False})
    met = load_met()
    met[fname] = not met.get(fname, False)
    save_met(met)
    return jsonify({"ok": True, "met": met[fname]})

@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(BASE_DIR, path)

# ──────────────────────────────────────────────
#  TRIP APP — SQLite DB + API
# ──────────────────────────────────────────────
DB_PATH = os.path.join(BASE_DIR, "trip.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_trip_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            name        TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            currency    TEXT    DEFAULT 'KRW',
            payer       TEXT    NOT NULL,
            participants TEXT   NOT NULL DEFAULT '[]',
            day_num     INTEGER DEFAULT 0,
            note        TEXT    DEFAULT ''
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        conn.execute("INSERT OR IGNORE INTO config VALUES ('members', '[]')")
        conn.execute("INSERT OR IGNORE INTO config VALUES ('krw_rate', '0.023')")

init_trip_db()

@app.route('/trip')
def trip():
    return render_template('trip.html')

@app.route('/api/expenses', methods=['GET'])
def api_get_expenses():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM expenses ORDER BY created_at DESC').fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:    d['participants'] = json.loads(d['participants'])
        except: d['participants'] = []
        result.append(d)
    return jsonify(result)

@app.route('/api/expenses', methods=['POST'])
def api_add_expense():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "No data"}), 400
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO expenses (name,amount,currency,payer,participants,day_num,note) VALUES (?,?,?,?,?,?,?)',
                (data['name'], float(data['amount']), data.get('currency','KRW'),
                 data['payer'], json.dumps(data.get('participants',[])),
                 int(data.get('day_num',0)), data.get('note',''))
            )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/api/expenses/<int:eid>', methods=['DELETE'])
def api_delete_expense(eid):
    with get_db() as conn:
        conn.execute('DELETE FROM expenses WHERE id=?', (eid,))
    return jsonify({"ok": True})

@app.route('/api/config', methods=['GET'])
def api_get_config():
    with get_db() as conn:
        rows = conn.execute('SELECT key, value FROM config').fetchall()
    result = {}
    for r in rows:
        try:    result[r['key']] = json.loads(r['value'])
        except: result[r['key']] = r['value']
    return jsonify(result)

@app.route('/api/config', methods=['POST'])
def api_update_config():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False}), 400
    with get_db() as conn:
        for key, value in data.items():
            v = json.dumps(value) if isinstance(value, (list, dict)) else str(value)
            conn.execute('INSERT OR REPLACE INTO config VALUES (?,?)', (key, v))
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)

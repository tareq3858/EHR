import json
from datetime import date, datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = "meditech-secret-key-change-in-prod"

# Ensure DB + any new columns exist every time the app starts
init_db()


def compute_age(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return "—"


def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def doctor_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "doctor":
            flash("Access not allowed. Only doctors can view the patient portal.", "error")
            return redirect(url_for("appointments"))
        return fn(*args, **kwargs)
    return wrapper


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("appointments"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        db.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("appointments"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        full_name = request.form["full_name"].strip()
        address = request.form["address"].strip()
        phone = request.form["phone"].strip()
        role = request.form["role"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        pw_hash = generate_password_hash(password)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, full_name, address, phone, role, created_at) VALUES (?,?,?,?,?,?,?)",
                (username, pw_hash, full_name, address, phone, role, now)
            )
            db.commit()
        except Exception:
            db.close()
            flash("Username already exists.", "error")
            return render_template("signup.html")
        db.close()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Appointments ──────────────────────────────────────────────────────────────

@app.route("/appointments")
@login_required
def appointments():
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.appointment_date, a.appointment_time, a.status,
               p.id AS patient_id, p.full_name, p.date_of_birth, p.gender
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """).fetchall()
    db.close()

    data = []
    for r in rows:
        data.append({
            "id": r["id"],
            "patient_id": r["patient_id"],
            "full_name": r["full_name"],
            "date_of_birth": r["date_of_birth"],
            "age": compute_age(r["date_of_birth"]),
            "appointment_date": r["appointment_date"],
            "appointment_time": r["appointment_time"],
            "status": r["status"],
        })

    return render_template("appointments.html", appointments=data, role=session.get("role"), full_name=session.get("full_name"))


@app.route("/api/patients/search")
@login_required
def api_patients_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    term = f"%{q}%"
    db = get_db()
    rows = db.execute("""
        SELECT id, full_name, date_of_birth, gender, phone, address
        FROM patients
        WHERE full_name LIKE ? OR date_of_birth LIKE ?
        ORDER BY full_name
        LIMIT 10
    """, (term, term)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/add-appointment", methods=["GET", "POST"])
@login_required
def add_appointment():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        dob = request.form["date_of_birth"]
        gender = request.form["gender"]
        address = request.form["address"].strip()
        phone = request.form["phone"].strip()
        appt_date = request.form["appointment_date"]
        appt_time = request.form["appointment_time"]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = date.today().strftime("%Y-%m-%d")

        db = get_db()
        patient = db.execute(
            "SELECT * FROM patients WHERE full_name = ? AND date_of_birth = ?",
            (full_name, dob)
        ).fetchone()

        if patient:
            patient_id = patient["id"]
        else:
            cur = db.execute(
                "INSERT INTO patients (full_name, date_of_birth, gender, phone, address, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (full_name, dob, gender, phone, address, now, now)
            )
            patient_id = cur.lastrowid

        db.execute(
            "INSERT INTO appointments (patient_id, created_by_user_id, appointment_date, appointment_time, status, created_at) VALUES (?,?,?,?,?,?)",
            (patient_id, session["user_id"], appt_date, appt_time, "scheduled", now)
        )
        db.commit()
        db.close()
        flash("Appointment booked successfully.", "success")
        return redirect(url_for("appointments"))

    prefill_date = request.args.get("date", "")
    return render_template("add_appointment.html", prefill_date=prefill_date)


@app.route("/appointments/<int:appt_id>/status", methods=["POST"])
@login_required
def update_status(appt_id):
    new_status = request.form.get("status")
    if new_status not in ("scheduled", "completed", "cancelled"):
        return jsonify({"error": "Invalid status"}), 400
    db = get_db()
    db.execute("UPDATE appointments SET status = ? WHERE id = ?", (new_status, appt_id))
    db.commit()
    db.close()
    return redirect(url_for("appointments"))


@app.route("/appointments/<int:appt_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appt_id):
    db = get_db()
    db.execute("DELETE FROM appointments WHERE id = ?", (appt_id,))
    db.commit()
    db.close()
    flash("Appointment deleted.", "success")
    return redirect(url_for("appointments"))


# ── Patient Portal ────────────────────────────────────────────────────────────

@app.route("/patient-portal/<int:patient_id>", methods=["GET", "POST"])
@login_required
@doctor_required
def patient_portal(patient_id):
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not patient:
        db.close()
        flash("Patient not found.", "error")
        return redirect(url_for("appointments"))

    today_str = date.today().strftime("%Y-%m-%d")
    age = compute_age(patient["date_of_birth"])

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_visit":
            dx = request.form.get("dx", "")
            chief_complaint = request.form.get("chief_complaint", "")
            present_illness = request.form.get("present_illness", "")
            vitals = json.dumps({
                "bp": request.form.get("bp", ""),
                "pulse": request.form.get("pulse", ""),
                "temp": request.form.get("temp", ""),
                "rr": request.form.get("rr", ""),
                "spo2": request.form.get("spo2", ""),
            })
            labs_requested = request.form.get("labs_requested", "")
            lab_results = request.form.get("lab_results", "")
            special_notes = request.form.get("special_notes", "")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            existing = db.execute(
                "SELECT id FROM medical_records WHERE patient_id = ? AND visit_date = ?",
                (patient_id, today_str)
            ).fetchone()

            if existing:
                record_id = existing["id"]
                db.execute("""
                    UPDATE medical_records
                    SET user_id=?, dx=?, chief_complaint=?, present_illness=?, vitals=?,
                        labs_requested=?, lab_results=?, special_notes=?
                    WHERE id=?
                """, (session["user_id"], dx, chief_complaint, present_illness, vitals,
                      labs_requested, lab_results, special_notes, record_id))
            else:
                cur = db.execute("""
                    INSERT INTO medical_records (patient_id, user_id, visit_date, dx, chief_complaint, present_illness, vitals, labs_requested, lab_results, special_notes, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (patient_id, session["user_id"], today_str, dx, chief_complaint, present_illness,
                      vitals, labs_requested, lab_results, special_notes, now))
                record_id = cur.lastrowid

            # Insert prescriptions — continue_flag[] is a hidden field that always submits
            # "0" or "1" in row order, so indexes align with med_name[] etc.
            med_names = request.form.getlist("med_name[]")
            strengths = request.form.getlist("strength[]")
            dosages = request.form.getlist("dosage[]")
            durations = request.form.getlist("duration_days[]")
            continues = request.form.getlist("continue_flag[]")

            db.execute("DELETE FROM prescriptions WHERE medical_record_id = ?", (record_id,))
            for i in range(len(med_names)):
                if med_names[i].strip():
                    cont = 1 if i < len(continues) and continues[i] == "1" else 0
                    dur_raw = durations[i] if i < len(durations) else ""
                    dur = int(dur_raw) if dur_raw.isdigit() else 0
                    db.execute("""
                        INSERT INTO prescriptions (medical_record_id, med_name, strength, dosage, duration_days, continue_flag, prescribed_date)
                        VALUES (?,?,?,?,?,?,?)
                    """, (record_id, med_names[i],
                          strengths[i] if i < len(strengths) else "",
                          dosages[i] if i < len(dosages) else "",
                          dur, cont, today_str))

            # Add illness if dx non-empty and not duplicate
            if dx.strip():
                existing_ill = db.execute(
                    "SELECT id FROM patient_illnesses WHERE patient_id = ? AND illness = ?",
                    (patient_id, dx.strip())
                ).fetchone()
                if not existing_ill:
                    db.execute(
                        "INSERT INTO patient_illnesses (patient_id, illness, date_added) VALUES (?,?,?)",
                        (patient_id, dx.strip(), today_str)
                    )

            db.commit()
            flash("Visit saved successfully.", "success")
            session["last_saved_record"] = record_id

        elif action == "add_illness":
            illness = request.form.get("illness", "").strip()
            if illness:
                existing_ill = db.execute(
                    "SELECT id FROM patient_illnesses WHERE patient_id = ? AND illness = ?",
                    (patient_id, illness)
                ).fetchone()
                if not existing_ill:
                    db.execute(
                        "INSERT INTO patient_illnesses (patient_id, illness, date_added) VALUES (?,?,?)",
                        (patient_id, illness, today_str)
                    )
                    db.commit()
                    flash("Illness added.", "success")

        return redirect(url_for("patient_portal", patient_id=patient_id))

    # GET
    illnesses = db.execute(
        "SELECT * FROM patient_illnesses WHERE patient_id = ? ORDER BY date_added DESC",
        (patient_id,)
    ).fetchall()

    today = date.today()
    all_rx = db.execute("""
        SELECT p.id, p.med_name, p.strength, p.duration_days, p.prescribed_date, p.continue_flag
        FROM prescriptions p
        JOIN medical_records mr ON p.medical_record_id = mr.id
        WHERE mr.patient_id = ? AND p.continue_flag = 1
    """, (patient_id,)).fetchall()

    # Continue flag = 1 means perpetual, always show. No duration filter.
    active_rx = []
    for rx in all_rx:
        active_rx.append({
            "id": rx["id"],
            "med_name": rx["med_name"],
            "strength": rx["strength"],
            "label": "Continuing",
        })

    # Today's record
    record = db.execute(
        "SELECT * FROM medical_records WHERE patient_id = ? AND visit_date = ?",
        (patient_id, today_str)
    ).fetchone()

    vitals = {}
    existing_rx = []
    if record:
        try:
            vitals = json.loads(record["vitals"] or "{}")
        except Exception:
            vitals = {}
        existing_rx = db.execute(
            "SELECT * FROM prescriptions WHERE medical_record_id = ?",
            (record["id"],)
        ).fetchall()

    last_saved_record = session.pop("last_saved_record", None)
    db.close()

    return render_template("patient_portal.html",
                           patient=patient,
                           age=age,
                           illnesses=illnesses,
                           active_rx=active_rx,
                           record=record,
                           vitals=vitals,
                           existing_rx=existing_rx,
                           today=today_str,
                           full_name=session.get("full_name"),
                           role=session.get("role"),
                           last_saved_record=last_saved_record)


@app.route("/patient-portal/<int:patient_id>/delete-illness/<int:illness_id>", methods=["POST"])
@login_required
@doctor_required
def delete_illness(patient_id, illness_id):
    db = get_db()
    db.execute("DELETE FROM patient_illnesses WHERE id = ? AND patient_id = ?", (illness_id, patient_id))
    db.commit()
    db.close()
    return redirect(url_for("patient_portal", patient_id=patient_id))


@app.route("/patient-portal/<int:patient_id>/api/illnesses", methods=["POST"])
@login_required
@doctor_required
def api_add_illness(patient_id):
    data = request.get_json(silent=True) or {}
    illness = (data.get("illness") or "").strip()
    if not illness:
        return jsonify({"error": "empty"}), 400
    today_str = date.today().strftime("%Y-%m-%d")
    db = get_db()
    existing = db.execute(
        "SELECT id FROM patient_illnesses WHERE patient_id = ? AND illness = ?",
        (patient_id, illness)
    ).fetchone()
    if existing:
        db.close()
        return jsonify({"error": "duplicate"}), 409
    cur = db.execute(
        "INSERT INTO patient_illnesses (patient_id, illness, date_added) VALUES (?,?,?)",
        (patient_id, illness, today_str)
    )
    db.commit()
    new_id = cur.lastrowid
    db.close()
    return jsonify({"id": new_id, "illness": illness, "date_added": today_str})


@app.route("/patient-portal/<int:patient_id>/api/illnesses/<int:illness_id>", methods=["DELETE"])
@login_required
@doctor_required
def api_delete_illness(patient_id, illness_id):
    db = get_db()
    db.execute("DELETE FROM patient_illnesses WHERE id = ? AND patient_id = ?", (illness_id, patient_id))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/patient-portal/<int:patient_id>/api/prescriptions/<int:rx_id>", methods=["DELETE"])
@login_required
@doctor_required
def api_delete_rx(patient_id, rx_id):
    db = get_db()
    db.execute("DELETE FROM prescriptions WHERE id = ?", (rx_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/patient-portal/<int:patient_id>/delete-rx/<int:rx_id>", methods=["POST"])
@login_required
@doctor_required
def delete_rx(patient_id, rx_id):
    db = get_db()
    db.execute("DELETE FROM prescriptions WHERE id = ?", (rx_id,))
    db.commit()
    db.close()
    return redirect(url_for("patient_portal", patient_id=patient_id))


@app.route("/prescription/<int:record_id>/print")
@login_required
@doctor_required
def print_prescription(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM medical_records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        db.close()
        flash("Record not found.", "error")
        return redirect(url_for("appointments"))
    patient = db.execute("SELECT * FROM patients WHERE id = ?", (record["patient_id"],)).fetchone()
    prescriptions = db.execute(
        "SELECT * FROM prescriptions WHERE medical_record_id = ?", (record_id,)
    ).fetchall()
    db.close()

    age = compute_age(patient["date_of_birth"])
    try:
        vitals = json.loads(record["vitals"] or "{}")
    except Exception:
        vitals = {}

    return render_template("print_prescription.html",
                           record=record,
                           patient=patient,
                           prescriptions=prescriptions,
                           age=age,
                           vitals=vitals,
                           doctor_name=session.get("full_name"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import random
import string
from datetime import datetime, timedelta
import math

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- TEMP STORAGE ----------------
attendance_codes = []
attendance_records = []

# ---------------- CONFIG ----------------
ALLOWED_RADIUS = 100000  # 100 KM

# ---------------- HELPERS ----------------
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


def distance(lat1, lon1, lat2, lon2):
    R = 6371e3
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template("index.html")


# ---------------- TEACHER / STUDENT DASHBOARD ----------------
@app.route('/teacher')
def teacher():
    if not session.get('teacher'):
        return redirect(url_for('teacher_login'))
    return render_template("teacher.html")


@app.route('/student')
def student():
    if not session.get('student'):
        return redirect(url_for('student_login'))
    return render_template("student.html")


# ---------------- GENERATE CODE ----------------
@app.route('/generate')
def generate():
    custom_code = request.args.get("custom")
    code = custom_code.upper() if custom_code else generate_code()

    lat = float(request.args.get("lat"))
    lng = float(request.args.get("lng"))
    expiry_seconds = int(request.args.get("expiry", 3600))
    expiry = datetime.now() + timedelta(seconds=expiry_seconds)

    teacher_name = session.get("teacher_name", "Unknown Teacher")

    # Check duplicate
    for c in attendance_codes:
        if c["code"] == code and c["expires_at"] > datetime.now():
            return jsonify({"message": "Code already active"}), 400

    attendance_codes.append({
        "code": code,
        "lat": lat,
        "lng": lng,
        "expires_at": expiry,
        "teacher_name": teacher_name
    })

    return jsonify({"code": code, "expires_in": expiry_seconds})


# ---------------- SUBMIT ATTENDANCE ----------------
@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    name = data['name']
    code = data['code']
    lat = float(data['lat'])
    lng = float(data['lng'])

    # Find code
    active_code = None
    for c in reversed(attendance_codes):
        if c["code"] == code and c["expires_at"] > datetime.now():
            active_code = c
            break

    if not active_code:
        return jsonify({"message": "Invalid or expired code"})

    if distance(lat, lng, active_code["lat"], active_code["lng"]) > ALLOWED_RADIUS:
        return jsonify({"message": "Too far from teacher (100km limit)"})

    # Prevent duplicate
    for r in attendance_records:
        if r["name"] == name and r["code"] == code:
            return jsonify({"message": "Already marked"})

    attendance_records.append({
        "name": name,
        "code": code,
        "lat": lat,
        "lng": lng,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "teacher": active_code["teacher_name"]
    })

    return jsonify({"message": "Attendance marked successfully"})


# ---------------- DASHBOARDS ----------------
@app.route('/student-dashboard')
def student_dashboard():
    if not session.get('student'):
        return redirect(url_for('student_login'))

    records = [r for r in attendance_records if r["name"] == session.get("student_name")]
    return render_template("student_dashboard.html", records=records)


@app.route('/dashboard')
def dashboard():
    if not session.get('teacher'):
        return redirect(url_for('teacher_login'))

    teacher = session.get("teacher_name")
    records = [r for r in attendance_records if r["teacher"] == teacher]
    return render_template("dashboard.html", records=records)


# ---------------- LOGIN / LOGOUT ----------------
@app.route('/teacher-login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        session['teacher'] = True
        session['teacher_name'] = request.form['username']
        return redirect(url_for('teacher'))
    return render_template("login.html")


@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        session['student'] = True
        session['student_name'] = request.form['username']
        return redirect(url_for('student'))
    return render_template("student_login.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run()
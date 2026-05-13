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
users_students = {}
users_teachers = {}

# ---------------- CONFIG ----------------
ALLOWED_RADIUS = 100_000  # 100 km

# ---------------- HELPERS ----------------
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def distance(lat1, lon1, lat2, lon2):
    R = 6371e3  # meters
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

# ---------------- TEACHER DASHBOARD ----------------
@app.route('/teacher')
def teacher():
    if not session.get('teacher'):
        return redirect(url_for('teacher_login'))
    return render_template("teacher.html")

# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student')
def student():
    if not session.get('student'):
        return redirect(url_for('student_login'))
    return render_template("student.html")

# ---------------- GENERATE CODE ----------------
@app.route('/generate')
def generate_attendance():
    custom_code = request.args.get("custom")
    code = custom_code.upper() if custom_code and len(custom_code)>=4 else generate_code()
    lat = float(request.args.get("lat", 0))
    lng = float(request.args.get("lng", 0))
    expiry_seconds = int(request.args.get("expiry", 60))
    expiry = datetime.now() + timedelta(seconds=expiry_seconds)
    teacher_name = session.get("teacher_name", "Unknown Teacher")

    # prevent duplicate active code
    for c in attendance_codes:
        if c['code'] == code and c['expires_at'] > datetime.now():
            return jsonify({"message":"Code already active"}), 400

    attendance_codes.append({
        "code": code,
        "lat": lat,
        "lng": lng,
        "expires_at": expiry,
        "teacher": teacher_name
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

    # find code
    code_entry = next((c for c in attendance_codes if c['code']==code and c['expires_at']>datetime.now()), None)
    if not code_entry:
        return jsonify({"message":"Invalid or expired code"})

    dist = distance(lat, lng, code_entry['lat'], code_entry['lng'])
    if dist > ALLOWED_RADIUS:
        return jsonify({"message":"Too far from teacher"})

    # prevent double marking
    if any(r for r in attendance_records if r['student_name']==name and r['code']==code):
        return jsonify({"message":"Already marked"})

    attendance_records.append({
        "student_name": name,
        "code": code,
        "lat": lat,
        "lng": lng,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "teacher": code_entry['teacher']
    })

    return jsonify({"message":"Attendance marked successfully"})

# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student-dashboard')
def student_dashboard():
    if not session.get('student'):
        return redirect(url_for('student_login'))

    student_name = session.get('student_name')
    records = [r for r in attendance_records if r['student_name']==student_name]

    return render_template("student_dashboard.html", records=records)

# ---------------- TEACHER DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():
    if not session.get('teacher'):
        return redirect(url_for('teacher_login'))

    teacher_name = session.get('teacher_name')
    records = [r for r in attendance_records if r['teacher']==teacher_name]

    return render_template("dashboard.html", records=records)

# ---------------- AUTH ROUTES ----------------
@app.route('/student-login', methods=['GET','POST'])
def student_login():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        if users_students.get(username)==password:
            session['student'] = True
            session['student_name'] = username
            return redirect(url_for('student'))
        return "Invalid credentials"
    return render_template("student_login.html")

@app.route('/teacher-login', methods=['GET','POST'])
def teacher_login():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        if users_teachers.get(username)==password:
            session['teacher'] = True
            session['teacher_name'] = username
            return redirect(url_for('teacher'))
        return "Invalid credentials"
    return render_template("login.html")

# ---------------- SIGNUP ----------------
@app.route('/teacher-signup', methods=['GET','POST'])
def teacher_signup():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        users_teachers[username] = password
        return redirect(url_for('teacher_login'))
    return render_template("signup.html")

@app.route('/student-signup', methods=['GET','POST'])
def student_signup():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        users_students[username] = password
        return redirect(url_for('student-login'))
    return render_template("student_signup.html")

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/student-logout')
def student_logout():
    session.clear()
    return redirect(url_for('home'))

if __name__=="__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
import random
import string
from datetime import datetime, timedelta
import math

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- DB ----------------
import os
import mysql.connector

db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=os.getenv("DB_PORT", 3306)
)

cursor = db.cursor()

# ---------------- CONFIG ----------------
ALLOWED_RADIUS = 100  # meters

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
def generate():

    custom_code = request.args.get("custom")

    if custom_code and len(custom_code) >= 4:
        code = custom_code.upper()
    else:
        code = generate_code()

    lat = request.args.get("lat")
    lng = request.args.get("lng")

    expiry_seconds = int(request.args.get("expiry", 60))

    expiry = datetime.now() + timedelta(seconds=expiry_seconds)

    teacher_name = session.get("teacher_name", "Unknown Teacher")

    # prevent duplicate active code
    cursor.execute("""
        SELECT id FROM attendance_codes
        WHERE code=%s AND expires_at > NOW()
    """, (code,))

    existing = cursor.fetchone()

    if existing:
        return jsonify({
            "message": "Code already active"
        }), 400

    cursor.execute("""
        INSERT INTO attendance_codes
        (code, expires_at, lat, lng, teacher_name)
        VALUES (%s, %s, %s, %s, %s)
    """, (code, expiry, float(lat), float(lng), teacher_name))

    db.commit()

    return jsonify({
        "code": code,
        "expires_in": expiry_seconds
    })

# ---------------- SUBMIT ATTENDANCE ----------------
@app.route('/submit', methods=['POST'])
def submit():

    data = request.json

    name = data['name']
    code = data['code']
    lat = float(data['lat'])
    lng = float(data['lng'])

    cursor.execute("""
        SELECT lat, lng FROM attendance_codes
        WHERE code=%s AND expires_at > NOW()
        ORDER BY id DESC LIMIT 1
    """, (code,))

    row = cursor.fetchone()

    if not row:
        return jsonify({"message": "Invalid or expired code"})

    teacher_lat, teacher_lng = row

    dist = distance(lat, lng, teacher_lat, teacher_lng)

    if dist > ALLOWED_RADIUS:
        return jsonify({"message": "Too far from teacher"})

    cursor.execute("""
        SELECT id FROM attendance_records
        WHERE student_name=%s AND code=%s
    """, (name, code))

    if cursor.fetchone():
        return jsonify({"message": "Already marked"})

    cursor.execute("""
        INSERT INTO attendance_records (student_name, code, lat, lng)
        VALUES (%s, %s, %s, %s)
    """, (name, code, lat, lng))

    db.commit()

    return jsonify({"message": "Attendance marked successfully"})


# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student-dashboard')
def student_dashboard():

    if not session.get('student'):
        return redirect(url_for('student_login'))

    cur = db.cursor()

    cur.execute("""
        SELECT c.teacher_name, r.code, r.marked_at
        FROM attendance_records r
        JOIN attendance_codes c ON r.code = c.code
        WHERE r.student_name = %s
        ORDER BY r.id DESC
    """, (session.get('student_name'),))

    records = cur.fetchall()

    return render_template("student_dashboard.html", records=records)

#----------------TEACHER DASHBOARD-----------------------------------------
@app.route('/dashboard')
def dashboard():

    if not session.get('teacher'):
        return redirect(url_for('teacher_login'))

    teacher_name = session.get('teacher_name')

    cur = db.cursor()

    cur.execute("""
        SELECT r.id, r.student_name, r.code, r.lat, r.lng, r.marked_at
        FROM attendance_records r
        JOIN attendance_codes c ON r.code = c.code
        WHERE c.teacher_name = %s
        ORDER BY r.id DESC
    """, (teacher_name,))

    records = cur.fetchall()

    return render_template("dashboard.html", records=records)


# ---------------- LOGOUTS ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/student-logout')
def student_logout():
    session.clear()
    return redirect(url_for('home'))


# ---------------- LOGIN (MINIMAL FIX) ----------------
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute("""
            SELECT * FROM students
            WHERE username=%s AND password=%s
        """, (username, password))

        user = cursor.fetchone()

        if user:
            session['student'] = True
            session['student_name'] = username
            return redirect(url_for('student'))

        return "Invalid credentials"

    return render_template("student_login.html")


@app.route('/teacher-login', methods=['GET', 'POST'])
def teacher_login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute("""
            SELECT * FROM teachers
            WHERE username=%s AND password=%s
        """, (username, password))

        user = cursor.fetchone()

        if user:
            session['teacher'] = True
            session['teacher_name'] = username
            return redirect(url_for('teacher'))

        return "Invalid credentials"

    return render_template("login.html")

#---------------------------SIGNUP (teacher)---------------------------------
@app.route('/teacher-signup', methods=['GET', 'POST'])
def teacher_signup():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        cursor.execute("""
            INSERT INTO teachers (username, password)
            VALUES (%s, %s)
        """, (username, password))

        db.commit()

        return redirect(url_for('teacher_login'))

    return render_template("signup.html")

#--------------------------------SIGNUP (student)----------------------------
@app.route('/student-signup', methods=['GET', 'POST'])
def student_signup():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        try:
            cursor.execute("""
                INSERT INTO students (username, password)
                VALUES (%s, %s)
            """, (username, password))

            db.commit()

            return redirect(url_for('student_login'))

        except mysql.connector.IntegrityError:
            return "Username already exists"

    return render_template("student_signup.html")


if __name__ == '__main__':
    app.run()
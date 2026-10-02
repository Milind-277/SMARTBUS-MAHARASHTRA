# app.py  -  SmartBus Maharashtra  -  Main Flask Application
import os
import re
import random
import string
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db_connection

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")


def normalize_user_row(user):
    if not user:
        return user
    if "password_hash" not in user and "password" in user:
        user["password_hash"] = user["password"]
    if "role" in user and isinstance(user["role"], str):
        user["role"] = user["role"].strip().lower()
    if "status" in user and "is_active" not in user:
        user["is_active"] = 1 if str(user["status"]).strip().lower() == "active" else 0
    if "is_active" in user and isinstance(user["is_active"], str):
        user["is_active"] = 1 if user["is_active"].strip().lower() == "active" else 0
    return user


def verify_password(stored_hash, plain_password):
    if not stored_hash:
        return False
    try:
        return check_password_hash(stored_hash, plain_password)
    except ValueError:
        return stored_hash == plain_password

# ═══════════════════════════════════════════════════════════════
# MAHARASHTRA DISTRICT LIST  (for search datalist)
# ═══════════════════════════════════════════════════════════════
MH_DISTRICTS = [
    "Mumbai City","Mumbai Suburban","Thane","Palghar","Raigad",
    "Ratnagiri","Sindhudurg","Pune","Satara","Sangli","Kolhapur",
    "Solapur","Nashik","Dhule","Nandurbar","Jalgaon","Ahilyanagar",
    "Chhatrapati Sambhajinagar","Jalna","Beed","Dharashiv","Latur",
    "Nanded","Parbhani","Hingoli","Amravati","Akola","Buldhana",
    "Washim","Yavatmal","Nagpur","Wardha","Bhandara","Gondia",
    "Chandrapur","Gadchiroli","Shirdi",  # Shirdi kept as a key town
    "Mumbai","Pune"  # short aliases used in routes
]

# ═══════════════════════════════════════════════════════════════
# DECORATORS
# ═══════════════════════════════════════════════════════════════
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            return render_template("403.html"), 403
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def generate_booking_code():
    """Generate unique booking code like SB20261001001."""
    today = date.today().strftime("%Y%m%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bookings WHERE DATE(booking_date) = %s", (date.today(),))
    count = cursor.fetchone()[0]
    cursor.close(); conn.close()
    return f"SB{today}{str(count + 1).zfill(4)}"

def generate_ticket_number(booking_code):
    """Generate ticket number from booking code."""
    return "TKT-" + booking_code

def generate_transaction_id():
    """Generate a fake transaction ID for payment simulation."""
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    return f"TXN-SB-{date.today().strftime('%Y%m%d')}-{rand}"

def get_booked_seats(schedule_id):
    """Return list of confirmed-booked seat numbers for a schedule."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bs.seat_number
        FROM booking_seats bs
        JOIN bookings b ON bs.booking_id = b.booking_id
        WHERE b.schedule_id = %s AND b.booking_status = 'Confirmed'
    """, (schedule_id,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return [r[0] for r in rows]

def get_schedule_detail(schedule_id):
    """Fetch full schedule with bus and route info."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.schedule_id, s.travel_date, s.departure_time, s.arrival_time,
               b.bus_id, b.service_number, b.bus_number, b.bus_name, b.bus_type, b.total_seats,
               r.route_id, r.source, r.destination,
               r.distance_km AS distance, r.duration_hours AS duration, r.base_fare AS fare
        FROM schedules s
        JOIN buses  b ON s.bus_id   = b.bus_id
        JOIN routes r ON s.route_id = r.route_id
        WHERE s.schedule_id = %s AND b.status = 'Active'
    """, (schedule_id,))
    sch = cursor.fetchone()
    cursor.close(); conn.close()
    return sch

# ═══════════════════════════════════════════════════════════════
# ONE-TIME SETUP  (visit /setup once to create demo accounts)
# ═══════════════════════════════════════════════════════════════
@app.route("/setup")
def setup():
    conn = get_db_connection()
    if not conn:
        return "<h2>Database connection failed. Check database.py credentials.</h2>"
    cursor = conn.cursor()
    accounts = [
        ("SmartBus Admin",  "admin@smartbus.co.in",     "9000000001", "Admin@123",  "admin"),
        ("Rahul Sharma",    "passenger@smartbus.co.in",  "9000000002", "Pass@123",   "user"),
        ("Priya Deshmukh",  "priya@example.com",         "9000000003", "Test@123",   "user"),
        ("Amit Patil",      "amit@example.com",          "9000000004", "Test@123",   "user"),
    ]
    created = 0
    for name, email, mobile, pwd, role in accounts:
        cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        if not cursor.fetchone():
            role_name = "Admin" if role == "admin" else "Passenger"
            cursor.execute(
                "INSERT INTO users (name,email,mobile,password_hash,role,status) VALUES (%s,%s,%s,%s,%s,%s)",
                (name, email, mobile, generate_password_hash(pwd), role_name, "Active"))
            created += 1
    conn.commit(); cursor.close(); conn.close()
    return (f"<h2>Setup complete! Created {created} account(s).</h2>"
            "<p>Admin: admin@smartbus.co.in / Admin@123</p>"
            "<p>User:  passenger@smartbus.co.in / Pass@123</p>"
            "<p><a href='/'>Go to Homepage</a> | <a href='/admin/login'>Admin Login</a></p>")

# ═══════════════════════════════════════════════════════════════
# PUBLIC PAGES
# ═══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    conn = get_db_connection()
    stats = {"total_buses": 0, "total_routes": 0, "total_trips": 0}
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM buses WHERE status='Active'")
        stats["total_buses"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM routes")
        stats["total_routes"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE booking_status='Confirmed'")
        stats["total_trips"] = cursor.fetchone()[0]
        cursor.close(); conn.close()
    return render_template("index.html", stats=stats, districts=MH_DISTRICTS)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact", methods=["GET","POST"])
def contact():
    if request.method == "POST":
        name    = request.form.get("name","").strip()
        email   = request.form.get("email","").strip()
        message = request.form.get("message","").strip()
        if not name or not email or not message:
            flash("All fields are required.", "danger")
            return render_template("contact.html")
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO contact_messages (name,email,subject,message) VALUES (%s,%s,%s,%s)",
                           (name, email, "General Inquiry", message))
            conn.commit(); cursor.close(); conn.close()
        flash("Your message has been sent. We will get back to you soon.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

# ═══════════════════════════════════════════════════════════════
# AUTHENTICATION  (Public login — users only)
# ═══════════════════════════════════════════════════════════════
@app.route("/register", methods=["GET","POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name    = request.form.get("name","").strip()
        email   = request.form.get("email","").strip()
        mobile  = request.form.get("mobile","").strip()
        pwd     = request.form.get("password","")
        cpwd    = request.form.get("confirm_password","")
        errors  = []
        if not name:
            errors.append("Full name is required.")
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
            errors.append("Enter a valid email address.")
        if not re.match(r"^\d{10}$", mobile):
            errors.append("Mobile must be exactly 10 digits.")
        if len(pwd) < 6:
            errors.append("Password must be at least 6 characters.")
        if pwd != cpwd:
            errors.append("Passwords do not match.")
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("register.html", name=name, email=email, mobile=mobile)
        conn = get_db_connection()
        if not conn:
            flash("Service temporarily unavailable. Please try again.", "danger")
            return render_template("register.html")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("This email is already registered. Please log in.", "warning")
            cursor.close(); conn.close()
            return render_template("register.html", name=name, mobile=mobile)
        cursor.execute(
            "INSERT INTO users (name,email,mobile,password_hash,role,status) VALUES (%s,%s,%s,%s,'Passenger','Active')",
            (name, email, mobile, generate_password_hash(pwd)))
        conn.commit(); cursor.close(); conn.close()
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email","").strip()
        pwd   = request.form.get("password","")
        conn  = get_db_connection()
        if not conn:
            flash("Service error. Please try again.", "danger")
            return render_template("login.html")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT *, LOWER(role) AS role, CASE WHEN status='Active' THEN 1 ELSE 0 END AS is_active FROM users WHERE email=%s", (email,))
        user = normalize_user_row(cursor.fetchone())
        cursor.close(); conn.close()
        if user and verify_password(user.get("password_hash") or user.get("password"), pwd):
            if user["role"] == "admin":
                flash("Please use the admin login page.", "warning")
                return redirect(url_for("admin_login"))
            session["user_id"]   = user["user_id"]
            session["user_name"] = user["name"]
            session["role"]      = "user" if user["role"] == "passenger" else user["role"]
            session["email"]     = user["email"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

# ═══════════════════════════════════════════════════════════════
# USER DASHBOARD
# ═══════════════════════════════════════════════════════════════
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()
    recent = []; summary = {"upcoming":0,"total":0,"active":0,"cancelled":0}
    if conn:
        cursor = conn.cursor(dictionary=True)
        uid = session["user_id"]
        cursor.execute("""
            SELECT b.booking_code, b.total_amount, b.booking_status, b.payment_status,
                   s.travel_date, s.departure_time, r.source, r.destination, bu.bus_name
            FROM bookings b
            JOIN schedules s ON b.schedule_id=s.schedule_id
            JOIN routes r    ON s.route_id=r.route_id
            JOIN buses bu    ON s.bus_id=bu.bus_id
            WHERE b.user_id=%s ORDER BY b.booking_date DESC LIMIT 5
        """, (uid,))
        recent = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE user_id=%s", (uid,))
        summary["total"] = cursor.fetchone()["COUNT(*)"]
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE user_id=%s AND booking_status='Confirmed' AND schedule_id IN (SELECT schedule_id FROM schedules WHERE travel_date >= CURDATE())", (uid,))
        summary["upcoming"] = cursor.fetchone()["COUNT(*)"]
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE user_id=%s AND booking_status='Confirmed'", (uid,))
        summary["active"] = cursor.fetchone()["COUNT(*)"]
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE user_id=%s AND booking_status='Cancelled'", (uid,))
        summary["cancelled"] = cursor.fetchone()["COUNT(*)"]
        cursor.close(); conn.close()
    return render_template("dashboard.html", recent=recent, summary=summary)

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    conn = get_db_connection()
    if not conn:
        flash("Service error.", "danger"); return redirect(url_for("dashboard"))
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (session["user_id"],))
    user = cursor.fetchone()
    if request.method == "POST":
        name   = request.form.get("name","").strip()
        mobile = request.form.get("mobile","").strip()
        if not name or not re.match(r"^\d{10}$", mobile):
            flash("Please enter a valid name and 10-digit mobile number.", "danger")
        else:
            cursor.execute("UPDATE users SET name=%s, mobile=%s WHERE user_id=%s",
                           (name, mobile, session["user_id"]))
            conn.commit()
            session["user_name"] = name
            flash("Profile updated successfully.", "success")
            cursor.execute("SELECT * FROM users WHERE user_id=%s", (session["user_id"],))
            user = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template("profile.html", user=user)

# ═══════════════════════════════════════════════════════════════
# ALL BUS SERVICES
# ═══════════════════════════════════════════════════════════════
@app.route("/all-services")
def all_services():
    source_filter = request.args.get("source", "").strip()
    dest_filter = request.args.get("destination", "").strip()
    conn = get_db_connection()
    services = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT r.source, r.destination, s.departure_time, s.arrival_time,
                   r.base_fare AS fare, b.bus_name, b.service_number, b.bus_type, MIN(s.travel_date) as next_date
            FROM schedules s
            JOIN buses b ON s.bus_id = b.bus_id
            JOIN routes r ON s.route_id = r.route_id
            WHERE s.travel_date >= CURDATE()
        """
        params = []
        if source_filter:
            query += " AND r.source = %s"
            params.append(source_filter)
        if dest_filter:
            query += " AND r.destination = %s"
            params.append(dest_filter)
        query += " GROUP BY r.source, r.destination, s.departure_time, s.arrival_time, r.base_fare, b.bus_name, b.service_number, b.bus_type ORDER BY r.source, r.destination, s.departure_time"
        cursor.execute(query, tuple(params))
        services = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template("all_services.html", services=services, districts=MH_DISTRICTS)

# ═══════════════════════════════════════════════════════════════
# BUS SEARCH
# ═══════════════════════════════════════════════════════════════
@app.route("/search", methods=["GET","POST"])
def search():
    if request.method == "POST":
        source      = request.form.get("source","").strip()
        destination = request.form.get("destination","").strip()
        travel_date = request.form.get("travel_date","").strip()
        if not source or not destination or not travel_date:
            flash("Please fill all search fields.", "danger")
            return render_template("search.html", districts=MH_DISTRICTS)
        try:
            search_date = datetime.strptime(travel_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return render_template("search.html", districts=MH_DISTRICTS)
        if search_date < date.today():
            flash("Travel date cannot be in the past.", "warning")
            return render_template("search.html", districts=MH_DISTRICTS)
        conn = get_db_connection()
        if not conn:
            flash("Service error. Please try again.", "danger")
            return render_template("search.html", districts=MH_DISTRICTS)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT s.schedule_id, s.travel_date, s.departure_time, s.arrival_time,
                   b.service_number, b.bus_number, b.bus_name, b.bus_type, b.total_seats,
                   r.source, r.destination,
                   r.distance_km AS distance, r.duration_hours AS duration, r.base_fare AS fare
            FROM schedules s
            JOIN buses  b ON s.bus_id   = b.bus_id
            JOIN routes r ON s.route_id = r.route_id
            WHERE LOWER(r.source)      = LOWER(%s)
              AND LOWER(r.destination) = LOWER(%s)
              AND s.travel_date        = %s
              AND b.status             = 'Active'
            ORDER BY s.departure_time
        """, (source, destination, travel_date))
        schedules = cursor.fetchall()
        for sch in schedules:
            cursor.execute("""
                SELECT COUNT(*) FROM booking_seats bs
                JOIN bookings bk ON bs.booking_id=bk.booking_id
                WHERE bk.schedule_id=%s AND bk.booking_status='Confirmed'
            """, (sch["schedule_id"],))
            booked = cursor.fetchone()["COUNT(*)"]
            sch["available_seats"] = sch["total_seats"] - booked
        cursor.close(); conn.close()
        return render_template("results.html",
                               schedules=schedules, source=source,
                               destination=destination, travel_date=travel_date)
    return render_template("search.html", districts=MH_DISTRICTS)

# ═══════════════════════════════════════════════════════════════
# SEAT SELECTION
# ═══════════════════════════════════════════════════════════════
@app.route("/select-seats/<int:schedule_id>")
@login_required
def select_seats(schedule_id):
    sch = get_schedule_detail(schedule_id)
    if not sch:
        flash("Schedule not available.", "danger")
        return redirect(url_for("search"))
    booked_seats = get_booked_seats(schedule_id)
    all_seats    = [str(i).zfill(2) for i in range(1, sch["total_seats"] + 1)]
    return render_template("seat_selection.html",
                           schedule=sch, booked_seats=booked_seats, all_seats=all_seats)

# ═══════════════════════════════════════════════════════════════
# PASSENGER DETAILS
# ═══════════════════════════════════════════════════════════════
@app.route("/passenger-details", methods=["POST"])
@login_required
def passenger_details():
    schedule_id    = request.form.get("schedule_id","")
    selected_seats = request.form.getlist("selected_seats")
    if not selected_seats:
        flash("Please select at least one seat.", "warning")
        return redirect(url_for("select_seats", schedule_id=schedule_id))
    # Store in session temporarily
    session["sel_seats"]   = selected_seats
    session["sel_sched"]   = int(schedule_id)
    sch = get_schedule_detail(int(schedule_id))
    if not sch:
        flash("Schedule not found.", "danger"); return redirect(url_for("search"))
    total_amount = float(sch["fare"]) * len(selected_seats)
    return render_template("passenger_details.html",
                           schedule=sch, selected_seats=selected_seats,
                           total_amount=total_amount)

# ═══════════════════════════════════════════════════════════════
# BOOKING REVIEW
# ═══════════════════════════════════════════════════════════════
@app.route("/review-booking", methods=["POST"])
@login_required
def review_booking():
    schedule_id    = request.form.get("schedule_id","")
    selected_seats = session.get("sel_seats", [])
    if not selected_seats:
        flash("Session expired. Please start booking again.", "warning")
        return redirect(url_for("search"))
    sch = get_schedule_detail(int(schedule_id))
    if not sch:
        flash("Schedule not found.", "danger"); return redirect(url_for("search"))
    # Collect passenger data from form and store in session
    passengers = {}
    for seat in selected_seats:
        passengers[seat] = {
            "name":   request.form.get(f"p_name_{seat}","").strip(),
            "age":    request.form.get(f"p_age_{seat}","0"),
            "gender": request.form.get(f"p_gender_{seat}","Male"),
            "mobile": request.form.get(f"p_mobile_{seat}","").strip(),
        }
    session["passengers"] = passengers
    total_amount = float(sch["fare"]) * len(selected_seats)
    return render_template("booking_review.html",
                           schedule=sch, selected_seats=selected_seats,
                           passengers=passengers, total_amount=total_amount)

# ═══════════════════════════════════════════════════════════════
# PAYMENT PAGE
# ═══════════════════════════════════════════════════════════════
@app.route("/payment", methods=["POST"])
@login_required
def payment():
    schedule_id    = request.form.get("schedule_id","")
    selected_seats = session.get("sel_seats", [])
    if not selected_seats:
        flash("Session expired.", "warning"); return redirect(url_for("search"))
    sch = get_schedule_detail(int(schedule_id))
    if not sch:
        flash("Schedule not found.", "danger"); return redirect(url_for("search"))
    total_amount = float(sch["fare"]) * len(selected_seats)
    return render_template("payment.html",
                           schedule=sch, selected_seats=selected_seats,
                           total_amount=total_amount)

# ═══════════════════════════════════════════════════════════════
# PROCESS PAYMENT & CONFIRM BOOKING
# ═══════════════════════════════════════════════════════════════
@app.route("/process-payment", methods=["POST"])
@login_required
def process_payment():
    schedule_id    = request.form.get("schedule_id","")
    payment_method = request.form.get("payment_method","Cash")
    selected_seats = session.get("sel_seats", [])
    passengers     = session.get("passengers", {})

    if not selected_seats or not schedule_id:
        flash("Session expired. Please start booking again.", "warning")
        return redirect(url_for("search"))

    conn = get_db_connection()
    if not conn:
        flash("Service error. Please try again.", "danger")
        return redirect(url_for("search"))
    cursor = conn.cursor(dictionary=True)

    # Validate schedule still exists
    cursor.execute("""
        SELECT s.schedule_id, r.base_fare AS fare, s.travel_date
        FROM schedules s JOIN routes r ON s.route_id=r.route_id
        WHERE s.schedule_id=%s
    """, (schedule_id,))
    sch = cursor.fetchone()
    if not sch:
        flash("Schedule no longer available.", "danger")
        cursor.close(); conn.close()
        return redirect(url_for("search"))

    # Re-check seat availability (prevent double booking)
    booked = get_booked_seats(int(schedule_id))
    conflicts = [s for s in selected_seats if s in booked]
    if conflicts:
        flash(f"Seats {', '.join(conflicts)} were just booked by someone else. Please select again.", "danger")
        cursor.close(); conn.close()
        return redirect(url_for("select_seats", schedule_id=schedule_id))

    # Determine payment status
    if payment_method == "Cash":
        pay_status = "Pending"
    else:
        pay_status = "Paid"

    total_amount = float(sch["fare"]) * len(selected_seats)
    booking_code = generate_booking_code()

    # Insert booking
    cursor.execute("""
        INSERT INTO bookings (booking_code, user_id, schedule_id, total_amount,
                              payment_method, payment_status, booking_status)
        VALUES (%s,%s,%s,%s,%s,%s,'Confirmed')
    """, (booking_code, session["user_id"], schedule_id, total_amount,
          payment_method, pay_status))
    booking_id = cursor.lastrowid

    # Insert passenger/seat records
    for seat in selected_seats:
        p = passengers.get(seat, {})
        cursor.execute("""
            INSERT INTO booking_seats
                (booking_id, seat_number, passenger_name, passenger_age, passenger_gender, passenger_mobile)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (booking_id, seat,
              p.get("name",""),  p.get("age",0),
              p.get("gender","Male"), p.get("mobile","")))

    # Insert payment record
    txn_id = generate_transaction_id() if pay_status == "Paid" else f"CASH-{booking_code}"
    cursor.execute("""
        INSERT INTO payments (booking_id, transaction_id, payment_method, amount, payment_status)
        VALUES (%s,%s,%s,%s,%s)
    """, (booking_id, txn_id, payment_method, total_amount, pay_status))

    # Insert ticket record
    ticket_number = generate_ticket_number(booking_code)
    cursor.execute("""
        INSERT INTO tickets (ticket_number, booking_id)
        VALUES (%s,%s)
    """, (ticket_number, booking_id))

    conn.commit(); cursor.close(); conn.close()

    # Clear booking session data
    session.pop("sel_seats", None)
    session.pop("sel_sched", None)
    session.pop("passengers", None)

    flash(f"Booking confirmed! Your booking ID is {booking_code}.", "success")
    return redirect(url_for("booking_success", booking_code=booking_code))

# ═══════════════════════════════════════════════════════════════
# BOOKING SUCCESS / CONFIRMATION
# ═══════════════════════════════════════════════════════════════
@app.route("/booking-success/<booking_code>")
@login_required
def booking_success(booking_code):
    conn = get_db_connection()
    if not conn:
        flash("Error loading booking.", "danger"); return redirect(url_for("my_trips"))
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.*, s.travel_date, s.departure_time, s.arrival_time,
               bu.service_number, bu.bus_number, bu.bus_name, bu.bus_type,
               r.source, r.destination, r.base_fare AS fare,
               u.name AS user_name, u.email AS user_email,
               tk.ticket_number
        FROM bookings b
        JOIN schedules s ON b.schedule_id=s.schedule_id
        JOIN buses bu    ON s.bus_id=bu.bus_id
        JOIN routes r    ON s.route_id=r.route_id
        JOIN users u     ON b.user_id=u.user_id
        LEFT JOIN tickets tk ON tk.booking_id=b.booking_id
        WHERE b.booking_code=%s AND b.user_id=%s
    """, (booking_code, session["user_id"]))
    booking = cursor.fetchone()
    if not booking:
        flash("Booking not found.", "danger"); cursor.close(); conn.close()
        return redirect(url_for("my_trips"))
    cursor.execute("SELECT * FROM booking_seats WHERE booking_id=%s", (booking["booking_id"],))
    seats = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template("booking_success.html", booking=booking, seats=seats)

# ═══════════════════════════════════════════════════════════════
# MY TRIPS (booking history)
# ═══════════════════════════════════════════════════════════════
@app.route("/my-trips")
@login_required
def my_trips():
    conn = get_db_connection()
    bookings = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.booking_id, b.booking_code, b.booking_date, b.total_amount,
                   b.payment_method, b.payment_status, b.booking_status,
                   s.travel_date, s.departure_time,
                   bu.bus_name, bu.service_number,
                   r.source, r.destination,
                   tk.ticket_number
            FROM bookings b
            JOIN schedules s ON b.schedule_id=s.schedule_id
            JOIN buses bu    ON s.bus_id=bu.bus_id
            JOIN routes r    ON s.route_id=r.route_id
            LEFT JOIN tickets tk ON tk.booking_id=b.booking_id
            WHERE b.user_id=%s ORDER BY b.booking_date DESC
        """, (session["user_id"],))
        bookings = cursor.fetchall()
        for bk in bookings:
            cursor.execute("SELECT seat_number FROM booking_seats WHERE booking_id=%s",
                           (bk["booking_id"],))
            bk["seats"] = ", ".join(r["seat_number"] for r in cursor.fetchall())
        cursor.close(); conn.close()
    return render_template("my_trips.html", bookings=bookings)

# ═══════════════════════════════════════════════════════════════
# MY TICKETS
# ═══════════════════════════════════════════════════════════════
@app.route("/my-tickets")
@login_required
def my_tickets():
    conn = get_db_connection()
    tickets = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT tk.ticket_number, tk.generated_at, tk.ticket_status,
                   b.booking_code, b.booking_status, b.total_amount,
                   s.travel_date, r.source, r.destination,
                   bu.bus_name, bu.service_number
            FROM tickets tk
            JOIN bookings b  ON tk.booking_id=b.booking_id
            JOIN schedules s ON b.schedule_id=s.schedule_id
            JOIN routes r    ON s.route_id=r.route_id
            JOIN buses bu    ON s.bus_id=bu.bus_id
            WHERE b.user_id=%s ORDER BY tk.generated_at DESC
        """, (session["user_id"],))
        tickets = cursor.fetchall()
        cursor.close(); conn.close()
    return render_template("my_tickets.html", tickets=tickets, today=date.today())

# ═══════════════════════════════════════════════════════════════
# TICKET VIEW (persistent — works after re-login)
# ═══════════════════════════════════════════════════════════════
@app.route("/ticket/<booking_code>")
@login_required
def ticket(booking_code):
    conn = get_db_connection()
    if not conn:
        flash("Service error.", "danger"); return redirect(url_for("my_trips"))
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.*, s.travel_date, s.departure_time, s.arrival_time,
               bu.service_number, bu.bus_number, bu.bus_name, bu.bus_type,
               r.source, r.destination, r.base_fare AS fare,
               u.name AS user_name, u.email AS user_email, u.mobile AS user_mobile,
               tk.ticket_number, tk.generated_at
        FROM bookings b
        JOIN schedules s ON b.schedule_id=s.schedule_id
        JOIN buses bu    ON s.bus_id=bu.bus_id
        JOIN routes r    ON s.route_id=r.route_id
        JOIN users u     ON b.user_id=u.user_id
        LEFT JOIN tickets tk ON tk.booking_id=b.booking_id
        WHERE b.booking_code=%s AND b.user_id=%s
    """, (booking_code, session["user_id"]))
    booking = cursor.fetchone()
    if not booking:
        flash("Ticket not found.", "danger"); cursor.close(); conn.close()
        return redirect(url_for("my_trips"))
    cursor.execute("SELECT * FROM booking_seats WHERE booking_id=%s", (booking["booking_id"],))
    seats = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template("ticket.html", booking=booking, seats=seats)

# ═══════════════════════════════════════════════════════════════
# CANCEL BOOKING
# ═══════════════════════════════════════════════════════════════
@app.route("/cancel-booking/<int:booking_id>", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    conn = get_db_connection()
    if not conn:
        flash("Service error.", "danger"); return redirect(url_for("my_trips"))
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT booking_id, booking_status FROM bookings WHERE booking_id=%s AND user_id=%s",
                   (booking_id, session["user_id"]))
    bk = cursor.fetchone()
    if not bk:
        flash("Booking not found.", "danger")
    elif bk["booking_status"] == "Cancelled":
        flash("This booking is already cancelled.", "warning")
    else:
        cursor.execute("UPDATE bookings SET booking_status='Cancelled' WHERE booking_id=%s", (booking_id,))
        cursor.execute("UPDATE tickets SET ticket_status='Cancelled' WHERE booking_id=%s", (booking_id,))
        conn.commit()
        flash("Booking cancelled. Your seat(s) have been released.", "success")
    cursor.close(); conn.close()
    return redirect(url_for("my_trips"))

# ═══════════════════════════════════════════════════════════════
# ADMIN LOGIN  (separate from public login)
# ═══════════════════════════════════════════════════════════════
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    # If already logged in as admin, redirect to dashboard
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        email = request.form.get("email","").strip()
        pwd   = request.form.get("password","")
        conn  = get_db_connection()
        if not conn:
            flash("Service error. Try again.", "danger")
            return render_template("admin/login.html")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT *, LOWER(role) AS role, CASE WHEN status='Active' THEN 1 ELSE 0 END AS is_active FROM users WHERE email=%s AND LOWER(role)='admin'", (email,))
        admin = normalize_user_row(cursor.fetchone())
        cursor.close(); conn.close()
        if admin and verify_password(admin.get("password_hash") or admin.get("password"), pwd):
            session["user_id"]   = admin["user_id"]
            session["user_name"] = admin["name"]
            session["role"]      = "admin"
            session["email"]     = admin["email"]
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

# ═══════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ═══════════════════════════════════════════════════════════════
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    stats = {}; recent = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS c FROM users WHERE LOWER(role)='passenger'"); stats["users"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM buses");                   stats["buses"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM routes");                  stats["routes"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM schedules");               stats["schedules"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM bookings");                stats["bookings"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM bookings WHERE booking_status='Confirmed'"); stats["confirmed"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM bookings WHERE booking_status='Cancelled'"); stats["cancelled"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM payments WHERE payment_status='Pending'"); stats["pending_pay"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COALESCE(SUM(amount),0) AS rev FROM payments WHERE payment_status='Paid'")
        stats["revenue"] = cursor.fetchone()["rev"]
        cursor.execute("""
            SELECT b.booking_code, b.booking_date, b.booking_status, b.total_amount,
                   u.name AS user_name, r.source, r.destination, s.travel_date
            FROM bookings b
            JOIN users u     ON b.user_id=u.user_id
            JOIN schedules s ON b.schedule_id=s.schedule_id
            JOIN routes r    ON s.route_id=r.route_id
            ORDER BY b.booking_date DESC LIMIT 8
        """)
        recent = cursor.fetchall()
        cursor.close(); conn.close()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)

# ─── Admin: Users ───────────────────────────────────────────────
@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db_connection(); users = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id,name,email,mobile,LOWER(role) AS role, CASE WHEN status='Active' THEN 1 ELSE 0 END AS is_active, created_at FROM users ORDER BY created_at DESC")
        users = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("admin/users.html", users=users)

@app.route("/admin/users/toggle/<int:user_id>", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, LOWER(role) AS role FROM users WHERE user_id=%s", (user_id,))
        u = cursor.fetchone()
        if u and u["role"] != "admin":
            new_status = "Inactive" if str(u["status"]).strip() == "Active" else "Active"
            cursor.execute("UPDATE users SET status=%s WHERE user_id=%s", (new_status, user_id))
            conn.commit(); flash("User status updated.", "success")
        else:
            flash("Cannot modify admin accounts.", "warning")
        cursor.close(); conn.close()
    return redirect(url_for("admin_users"))

# ─── Admin: Buses ───────────────────────────────────────────────
@app.route("/admin/buses")
@admin_required
def admin_buses():
    conn = get_db_connection(); buses = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM buses ORDER BY service_number")
        buses = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("admin/buses.html", buses=buses)

@app.route("/admin/buses/add", methods=["POST"])
@admin_required
def admin_add_bus():
    svc   = request.form.get("service_number","").strip()
    bnum  = request.form.get("bus_number","").strip()
    bname = request.form.get("bus_name","").strip()
    btype = request.form.get("bus_type","Ordinary")
    seats = request.form.get("total_seats", 40)
    stat  = request.form.get("status","Active")
    if not svc or not bnum or not bname:
        flash("Service number, bus number and name are required.", "danger")
        return redirect(url_for("admin_buses"))
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO buses (service_number,bus_number,bus_name,bus_type,total_seats,status) VALUES (%s,%s,%s,%s,%s,%s)",
                           (svc, bnum, bname, btype, seats, stat))
            conn.commit(); flash("Bus added.", "success")
        except Exception:
            flash("Error: Service/bus number may already exist.", "danger")
        cursor.close(); conn.close()
    return redirect(url_for("admin_buses"))

@app.route("/admin/buses/edit/<int:bus_id>", methods=["GET","POST"])
@admin_required
def admin_edit_bus(bus_id):
    conn = get_db_connection()
    if not conn: flash("DB error.","danger"); return redirect(url_for("admin_buses"))
    cursor = conn.cursor(dictionary=True)
    if request.method == "POST":
        cursor.execute("""UPDATE buses SET service_number=%s,bus_number=%s,bus_name=%s,
                          bus_type=%s,total_seats=%s,status=%s WHERE bus_id=%s""",
                       (request.form.get("service_number",""),
                        request.form.get("bus_number",""),
                        request.form.get("bus_name",""),
                        request.form.get("bus_type","Ordinary"),
                        request.form.get("total_seats",40),
                        request.form.get("status","Active"), bus_id))
        conn.commit(); flash("Bus updated.", "success")
        cursor.close(); conn.close()
        return redirect(url_for("admin_buses"))
    cursor.execute("SELECT * FROM buses WHERE bus_id=%s", (bus_id,))
    bus = cursor.fetchone(); cursor.close(); conn.close()
    if not bus: flash("Bus not found.","danger"); return redirect(url_for("admin_buses"))
    return render_template("admin/edit_bus.html", bus=bus)

@app.route("/admin/buses/delete/<int:bus_id>", methods=["POST"])
@admin_required
def admin_delete_bus(bus_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM schedules WHERE bus_id=%s", (bus_id,))
        count = cursor.fetchone()[0]
        if count > 0:
            flash(f"Cannot delete: {count} schedule(s) exist for this bus.", "warning")
        else:
            cursor.execute("DELETE FROM buses WHERE bus_id=%s", (bus_id,))
            conn.commit(); flash("Bus deleted.", "success")
        cursor.close(); conn.close()
    return redirect(url_for("admin_buses"))

# ─── Admin: Routes ──────────────────────────────────────────────
@app.route("/admin/routes")
@admin_required
def admin_routes():
    conn = get_db_connection(); routes = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM routes ORDER BY source, destination")
        routes = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("admin/routes.html", routes=routes, districts=MH_DISTRICTS)

@app.route("/admin/routes/add", methods=["POST"])
@admin_required
def admin_add_route():
    src  = request.form.get("source","").strip()
    dst  = request.form.get("destination","").strip()
    dist = request.form.get("distance",0)
    dur  = request.form.get("duration","").strip()
    fare = request.form.get("fare",0)
    if not src or not dst or not dur:
        flash("All fields are required.","danger")
        return redirect(url_for("admin_routes"))
    if src.lower() == dst.lower():
        flash("Source and destination cannot be the same.","danger")
        return redirect(url_for("admin_routes"))
    try:
        fare = float(fare)
        if fare <= 0: raise ValueError()
    except ValueError:
        flash("Fare must be a positive number.","danger")
        return redirect(url_for("admin_routes"))
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO routes (source,destination,distance_km,duration_hours,base_fare,status) VALUES (%s,%s,%s,%s,%s,'Active')",
                       (src, dst, dist, dur, fare))
        conn.commit(); flash("Route added.","success")
        cursor.close(); conn.close()
    return redirect(url_for("admin_routes"))

@app.route("/admin/routes/edit/<int:route_id>", methods=["GET","POST"])
@admin_required
def admin_edit_route(route_id):
    conn = get_db_connection()
    if not conn: flash("DB error.","danger"); return redirect(url_for("admin_routes"))
    cursor = conn.cursor(dictionary=True)
    if request.method == "POST":
        src  = request.form.get("source","").strip()
        dst  = request.form.get("destination","").strip()
        if src.lower() == dst.lower():
            flash("Source and destination cannot be the same.","danger")
        else:
            cursor.execute("""UPDATE routes SET source=%s,destination=%s,
                              distance_km=%s,duration_hours=%s,base_fare=%s WHERE route_id=%s""",
                           (src, dst, request.form.get("distance",0),
                            request.form.get("duration",""),
                            request.form.get("fare",0), route_id))
            conn.commit(); flash("Route updated.","success")
        cursor.close(); conn.close()
        return redirect(url_for("admin_routes"))
    cursor.execute("SELECT route_id,source,destination,distance_km AS distance,duration_hours AS duration,base_fare AS fare,status FROM routes WHERE route_id=%s", (route_id,))
    route = cursor.fetchone(); cursor.close(); conn.close()
    if not route: flash("Route not found.","danger"); return redirect(url_for("admin_routes"))
    return render_template("admin/edit_route.html", route=route, districts=MH_DISTRICTS)

@app.route("/admin/routes/delete/<int:route_id>", methods=["POST"])
@admin_required
def admin_delete_route(route_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM schedules WHERE route_id=%s", (route_id,))
        count = cursor.fetchone()[0]
        if count > 0: flash(f"Cannot delete: {count} schedule(s) use this route.","warning")
        else:
            cursor.execute("DELETE FROM routes WHERE route_id=%s", (route_id,))
            conn.commit(); flash("Route deleted.","success")
        cursor.close(); conn.close()
    return redirect(url_for("admin_routes"))

# ─── Admin: Schedules ───────────────────────────────────────────
@app.route("/admin/schedules")
@admin_required
def admin_schedules():
    conn = get_db_connection()
    schedules = []; buses = []; routes = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT s.schedule_id, s.travel_date, s.departure_time, s.arrival_time,
                   b.service_number, b.bus_name,
                   r.source, r.destination, r.base_fare AS fare
            FROM schedules s
            JOIN buses  b ON s.bus_id=b.bus_id
            JOIN routes r ON s.route_id=r.route_id
            ORDER BY s.travel_date DESC, s.departure_time LIMIT 200
        """)
        schedules = cursor.fetchall()
        cursor.execute("SELECT bus_id,service_number,bus_name FROM buses WHERE status='Active' ORDER BY service_number")
        buses = cursor.fetchall()
        cursor.execute("SELECT route_id,source,destination,base_fare AS fare FROM routes ORDER BY source")
        routes = cursor.fetchall()
        cursor.close(); conn.close()
    return render_template("admin/schedules.html", schedules=schedules, buses=buses, routes=routes)

@app.route("/admin/schedules/add", methods=["POST"])
@admin_required
def admin_add_schedule():
    bus_id = request.form.get("bus_id"); route_id = request.form.get("route_id")
    tdate  = request.form.get("travel_date"); dep = request.form.get("departure_time")
    arr    = request.form.get("arrival_time")
    if not all([bus_id, route_id, tdate, dep, arr]):
        flash("All fields required.","danger"); return redirect(url_for("admin_schedules"))
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO schedules (bus_id,route_id,travel_date,departure_time,arrival_time) VALUES (%s,%s,%s,%s,%s)",
                       (bus_id, route_id, tdate, dep, arr))
        conn.commit(); flash("Schedule added.","success")
        cursor.close(); conn.close()
    return redirect(url_for("admin_schedules"))

@app.route("/admin/schedules/edit/<int:schedule_id>", methods=["GET","POST"])
@admin_required
def admin_edit_schedule(schedule_id):
    conn = get_db_connection()
    if not conn: flash("DB error.","danger"); return redirect(url_for("admin_schedules"))
    cursor = conn.cursor(dictionary=True)
    if request.method == "POST":
        cursor.execute("""UPDATE schedules SET bus_id=%s,route_id=%s,travel_date=%s,
                          departure_time=%s,arrival_time=%s WHERE schedule_id=%s""",
                       (request.form.get("bus_id"), request.form.get("route_id"),
                        request.form.get("travel_date"), request.form.get("departure_time"),
                        request.form.get("arrival_time"), schedule_id))
        conn.commit(); flash("Schedule updated.","success")
        cursor.close(); conn.close()
        return redirect(url_for("admin_schedules"))
    cursor.execute("SELECT * FROM schedules WHERE schedule_id=%s", (schedule_id,))
    sch = cursor.fetchone()
    cursor.execute("SELECT bus_id,service_number,bus_name FROM buses WHERE status='Active' ORDER BY service_number")
    buses = cursor.fetchall()
    cursor.execute("SELECT route_id,source,destination,fare FROM routes ORDER BY source")
    routes = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template("admin/edit_schedule.html", schedule=sch, buses=buses, routes=routes)

@app.route("/admin/schedules/delete/<int:schedule_id>", methods=["POST"])
@admin_required
def admin_delete_schedule(schedule_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE schedule_id=%s AND booking_status='Confirmed'", (schedule_id,))
        count = cursor.fetchone()[0]
        if count > 0: flash(f"Cannot delete: {count} confirmed booking(s).","warning")
        else:
            cursor.execute("DELETE FROM schedules WHERE schedule_id=%s", (schedule_id,))
            conn.commit(); flash("Schedule deleted.","success")
        cursor.close(); conn.close()
    return redirect(url_for("admin_schedules"))

# ─── Admin: Bookings ────────────────────────────────────────────
@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    status_filter = request.args.get("status","All")
    conn = get_db_connection(); bookings = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT b.booking_id, b.booking_code, b.booking_date, b.total_amount,
                   b.payment_method, b.payment_status, b.booking_status,
                   u.name AS user_name, u.email AS user_email,
                   bu.service_number, bu.bus_name,
                   r.source, r.destination, s.travel_date,
                   tk.ticket_number
            FROM bookings b
            JOIN users u     ON b.user_id=u.user_id
            JOIN schedules s ON b.schedule_id=s.schedule_id
            JOIN buses bu    ON s.bus_id=bu.bus_id
            JOIN routes r    ON s.route_id=r.route_id
            LEFT JOIN tickets tk ON tk.booking_id=b.booking_id
        """
        if status_filter in ("Confirmed","Cancelled"):
            cursor.execute(sql + " WHERE b.booking_status=%s ORDER BY b.booking_date DESC", (status_filter,))
        else:
            cursor.execute(sql + " ORDER BY b.booking_date DESC")
        bookings = cursor.fetchall()
        for bk in bookings:
            cursor.execute("SELECT seat_number FROM booking_seats WHERE booking_id=%s", (bk["booking_id"],))
            bk["seats"] = ", ".join(r["seat_number"] for r in cursor.fetchall())
        cursor.close(); conn.close()
    return render_template("admin/bookings.html", bookings=bookings, status_filter=status_filter)

# ─── Admin: Payments ────────────────────────────────────────────
@app.route("/admin/payments")
@admin_required
def admin_payments():
    conn = get_db_connection(); payments = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.payment_id, p.transaction_id, p.payment_method, p.amount,
                   p.payment_status, p.paid_at,
                   b.booking_code,
                   u.name AS user_name, u.email AS user_email
            FROM payments p
            JOIN bookings b ON p.booking_id=b.booking_id
            JOIN users u    ON b.user_id=u.user_id
            ORDER BY p.paid_at DESC
        """)
        payments = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("admin/payments.html", payments=payments)

# ─── Admin: Reports ─────────────────────────────────────────────
@app.route("/admin/reports")
@admin_required
def admin_reports():
    conn = get_db_connection()
    report = {}; route_stats = []; bus_stats = []; pay_stats = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS c FROM bookings"); report["total"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM bookings WHERE booking_status='Confirmed'"); report["confirmed"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM bookings WHERE booking_status='Cancelled'"); report["cancelled"] = cursor.fetchone()["c"]
        cursor.execute("SELECT COALESCE(SUM(amount),0) AS rev FROM payments WHERE payment_status='Paid'"); report["revenue"] = cursor.fetchone()["rev"]
        cursor.execute("SELECT COUNT(*) AS c FROM payments WHERE payment_status='Pending'"); report["pending"] = cursor.fetchone()["c"]
        cursor.execute("""
            SELECT r.source, r.destination,
                   COUNT(b.booking_id) AS bookings,
                   COALESCE(SUM(b.total_amount),0) AS revenue
            FROM routes r
            LEFT JOIN schedules s ON r.route_id=s.route_id
            LEFT JOIN bookings b  ON s.schedule_id=b.schedule_id AND b.booking_status='Confirmed'
            GROUP BY r.route_id, r.source, r.destination
            ORDER BY bookings DESC LIMIT 20
        """)
        route_stats = cursor.fetchall()
        cursor.execute("""
            SELECT bu.service_number, bu.bus_name, bu.bus_type,
                   COUNT(b.booking_id) AS bookings,
                   COALESCE(SUM(b.total_amount),0) AS revenue
            FROM buses bu
            LEFT JOIN schedules s ON bu.bus_id=s.bus_id
            LEFT JOIN bookings b  ON s.schedule_id=b.schedule_id AND b.booking_status='Confirmed'
            GROUP BY bu.bus_id, bu.service_number, bu.bus_name, bu.bus_type
            ORDER BY bookings DESC LIMIT 20
        """)
        bus_stats = cursor.fetchall()
        cursor.execute("""
            SELECT payment_method,
                   COUNT(*) AS count,
                   COALESCE(SUM(amount),0) AS total
            FROM payments GROUP BY payment_method
        """)
        pay_stats = cursor.fetchall()
        cursor.close(); conn.close()
    return render_template("admin/reports.html",
                           report=report, route_stats=route_stats,
                           bus_stats=bus_stats, pay_stats=pay_stats)

# ─── Admin: Messages ────────────────────────────────────────────
@app.route("/admin/messages")
@admin_required
def admin_messages():
    conn = get_db_connection(); messages = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT message_id,name,email,message,submitted_at AS created_at FROM contact_messages ORDER BY submitted_at DESC")
        messages = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("admin/messages.html", messages=messages)

# ═══════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403

@app.errorhandler(500)
def server_error(e):
    return render_template("404.html"), 500

if __name__ == "__main__":
    app.run(debug=True)

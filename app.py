
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "digital_grievance_secret_key")


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():
    from urllib.parse import urlparse

    database_url = os.getenv("MYSQL_URL")

    if not database_url:
        raise Exception("MYSQL_URL is not configured")

    url = urlparse(database_url)

    return mysql.connector.connect(
        host=url.hostname,
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        database=url.path.lstrip("/"),
        connection_timeout=10
    )


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def create_tables():
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                phone VARCHAR(20),
                password VARCHAR(255) NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                category VARCHAR(100),
                location VARCHAR(255),
                status VARCHAR(50) DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL
            )
        """)

        connection.commit()

    finally:
        cursor.close()
        connection.close()


try:
    create_tables()
except Exception as error:
    print("Database table creation error:", error)


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# USER REGISTRATION
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            return "Please fill in all required fields."

        if password != confirm_password:
            return "Passwords do not match."

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (name, email, phone, password)
                VALUES (%s, %s, %s, %s)
            """, (name, email, phone, hashed_password))

            connection.commit()

        except mysql.connector.Error as error:
            connection.rollback()

            if error.errno == 1062:
                return "Email already registered. Please log in or use another email."

            return f"Database error: {error}"

        finally:
            cursor.close()
            connection.close()

        return "Registration successful! <a href='/login'>Login here</a>"

    return render_template("register.html")


# =========================================================
# USER LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()

        except mysql.connector.Error as error:
            return f"Database error: {error}"

        finally:
            cursor.close()
            connection.close()

        if user:
            stored_password = user["password"]

            try:
                password_matches = check_password_hash(
                    stored_password,
                    password
                )
            except (ValueError, TypeError):
                password_matches = False

            # Also support accounts that were originally saved
            # with a plain-text password. New registrations always
            # store a secure password hash.
            if not password_matches and stored_password == password:
                password_matches = True

                # Convert the old plain-text password to a hash.
                connection = get_db_connection()
                cursor = connection.cursor()

                try:
                    cursor.execute(
                        "UPDATE users SET password = %s WHERE id = %s",
                        (generate_password_hash(password), user["id"])
                    )
                    connection.commit()
                except mysql.connector.Error as error:
                    connection.rollback()
                    return f"Could not update password securely: {error}"
                finally:
                    cursor.close()
                    connection.close()

            if password_matches:
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                session["user_email"] = user["email"]

                return redirect("/dashboard")

        return "Invalid email or password. Please check your details."

    return render_template("login.html")


# =========================================================
# USER DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        email=session["user_email"]
    )


# =========================================================
# SUBMIT COMPLAINT
# =========================================================

@app.route("/complaint", methods=["GET", "POST"])
def complaint():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()

        if not title:
            return "Complaint title is required."

        if not category:
            return "Complaint category is required."

        if not description:
            return "Complaint description is required."

        if not location:
            return "Complaint location is required."

        if len(title) > 255:
            return "Complaint title must be 255 characters or less."

        if len(category) > 100:
            return "Complaint category must be 100 characters or less."

        if len(location) > 255:
            return "Complaint location must be 255 characters or less."

        if len(description) > 5000:
            return "Complaint description must be 5000 characters or less."

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO complaints
                (user_id, title, description, category, location, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (
                session["user_id"],
                title,
                description,
                category,
                location,
                "Pending"
            ))

            connection.commit()
            complaint_id = cursor.lastrowid

        except mysql.connector.Error as error:
            connection.rollback()
            return f"Database error: {error}"

        finally:
            cursor.close()
            connection.close()

        return render_template(
            "complaint_success.html",
            complaint_id=complaint_id
        )

    return render_template("complaint.html")


# =========================================================
# MY COMPLAINTS
# =========================================================

@app.route("/my-complaints")
def my_complaints():
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM complaints
            WHERE user_id = %s
            ORDER BY id DESC
        """, (session["user_id"],))

        complaints = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "my_complaints.html",
        complaints=complaints
    )


# =========================================================
# USER COMPLAINT DETAILS
# =========================================================

@app.route("/complaint/<int:complaint_id>")
def user_complaint_details(complaint_id):
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM complaints
            WHERE id = %s AND user_id = %s
        """, (complaint_id, session["user_id"]))

        complaint_record = cursor.fetchone()

    except mysql.connector.Error as error:
        return f"Database error: {error}"

    finally:
        cursor.close()
        connection.close()

    if complaint_record is None:
        return render_template(
            "complaint_details.html",
            complaint=None
        )

    return render_template(
        "complaint_details.html",
        complaint=complaint_record
    )


# =========================================================
# COMPLAINT STATUS
# =========================================================

@app.route("/complaint-status")
def complaint_status():
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM complaints
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (session["user_id"],))

        complaints = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "complaint_status.html",
        complaints=complaints
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM admins WHERE email = %s",
                (email,)
            )
            admin = cursor.fetchone()

        except mysql.connector.Error as error:
            return f"Database error: {error}"

        finally:
            cursor.close()
            connection.close()

        if admin and check_password_hash(admin["password"], password):
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["name"]
            session["admin_email"] = admin["email"]

            return redirect("/admin-dashboard")

        return "Invalid admin email or password."

    return render_template("admin_login.html")


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin-dashboard")
def admin_dashboard():
    if "admin_id" not in session:
        return redirect("/admin-login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) AS total FROM complaints")
        total_complaints = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM complaints WHERE status = %s",
            ("Pending",)
        )
        pending_complaints = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM complaints WHERE status = %s",
            ("In Progress",)
        )
        in_progress_complaints = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM complaints WHERE status = %s",
            ("Resolved",)
        )
        resolved_complaints = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT category, COUNT(*) AS total
            FROM complaints
            GROUP BY category
            ORDER BY total DESC
        """)
        category_complaints = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_dashboard.html",
        admin_name=session["admin_name"],
        admin_email=session["admin_email"],
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        in_progress_complaints=in_progress_complaints,
        resolved_complaints=resolved_complaints,
        category_complaints=category_complaints
    )


# =========================================================
# ADMIN COMPLAINT MANAGEMENT
# =========================================================

@app.route("/admin/complaints")
def admin_complaints():
    if "admin_id" not in session:
        return redirect("/admin-login")

    search = request.args.get("search", "").strip()
    selected_status = request.args.get("status", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    sql = """
        SELECT
            complaints.id AS complaint_id,
            complaints.title,
            complaints.category,
            complaints.description,
            complaints.location,
            complaints.status,
            complaints.created_at,
            users.name AS user_name,
            users.email AS user_email
        FROM complaints
        INNER JOIN users ON complaints.user_id = users.id
        WHERE 1 = 1
    """

    values = []

    if search:
        sql += """
            AND (
                complaints.title LIKE %s
                OR complaints.category LIKE %s
                OR complaints.description LIKE %s
                OR complaints.location LIKE %s
                OR users.name LIKE %s
                OR users.email LIKE %s
            )
        """

        search_value = "%" + search + "%"
        values.extend([search_value] * 6)

    if selected_status:
        sql += " AND complaints.status = %s"
        values.append(selected_status)

    sql += " ORDER BY complaints.created_at DESC"

    try:
        cursor.execute(sql, values)
        complaints = cursor.fetchall()

    except mysql.connector.Error as error:
        return f"Database error: {error}"

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_complaints.html",
        complaints=complaints,
        selected_status=selected_status,
        search=search
    )


# =========================================================
# ADMIN COMPLAINT DETAILS
# =========================================================

@app.route("/admin/complaint/<int:complaint_id>")
def admin_complaint_details(complaint_id):
    if "admin_id" not in session:
        return redirect("/admin-login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                complaints.id AS complaint_id,
                complaints.title,
                complaints.category,
                complaints.description,
                complaints.location,
                complaints.status,
                complaints.created_at,
                users.name AS user_name,
                users.email AS user_email,
                users.phone AS user_phone
            FROM complaints
            INNER JOIN users ON complaints.user_id = users.id
            WHERE complaints.id = %s
        """, (complaint_id,))

        complaint_record = cursor.fetchone()

    except mysql.connector.Error as error:
        return f"Database error: {error}"

    finally:
        cursor.close()
        connection.close()

    if complaint_record is None:
        return "Complaint not found."

    return render_template(
        "admin_complaint_details.html",
        complaint=complaint_record
    )


# =========================================================
# DELETE COMPLAINT
# =========================================================

@app.route(
    "/admin/delete-complaint/<int:complaint_id>",
    methods=["POST"]
)
def admin_delete_complaint(complaint_id):
    if "admin_id" not in session:
        return redirect("/admin-login")

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM complaints WHERE id = %s",
            (complaint_id,)
        )
        connection.commit()

    except mysql.connector.Error as error:
        connection.rollback()
        return f"Database error: {error}"

    finally:
        cursor.close()
        connection.close()

    return redirect("/admin/complaints")


# =========================================================
# UPDATE COMPLAINT STATUS
# =========================================================

@app.route(
    "/admin/update-complaint/<int:complaint_id>",
    methods=["POST"]
)
def update_complaint(complaint_id):
    if "admin_id" not in session:
        return redirect("/admin-login")

    status = request.form.get("status")

    allowed_statuses = [
        "Pending",
        "In Progress",
        "Resolved",
        "Rejected"
    ]

    if status not in allowed_statuses:
        return "Invalid complaint status."

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE complaints
            SET status = %s
            WHERE id = %s
        """, (status, complaint_id))

        connection.commit()

    except mysql.connector.Error as error:
        connection.rollback()
        return f"Database error: {error}"

    finally:
        cursor.close()
        connection.close()

    return redirect("/admin/complaints")


# =========================================================
# USER LOGOUT
# =========================================================

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)

    return redirect("/login")


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_name", None)
    session.pop("admin_email", None)

    return redirect("/admin-login")


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )

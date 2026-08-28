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

    return mysql.connector.connect(
        host=os.getenv("MYSQLHOST", "localhost"),
        port=int(os.getenv("MYSQLPORT", "3306")),
        user=os.getenv("MYSQLUSER", "root"),
        password=os.getenv("MYSQLPASSWORD", ""),
        database=os.getenv("MYSQLDATABASE", "digital_grievance")
    )


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

        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Check password confirmation
        if password != confirm_password:

            return "Passwords do not match"

        # Hash password
        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            sql = """
            INSERT INTO users
            (name, email, phone, password)
            VALUES (%s, %s, %s, %s)
            """

            values = (
                name,
                email,
                phone,
                hashed_password
            )

            cursor.execute(sql, values)

            connection.commit()

        except mysql.connector.Error as error:

            connection.rollback()

            if error.errno == 1062:

                return "Email already registered. Please use another email."

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

        email = request.form["email"]
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
        SELECT *
        FROM users
        WHERE email = %s
        """

        cursor.execute(sql, (email,))

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect("/dashboard")

        return "Invalid email or password"

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

    # Check user login
    if "user_id" not in session:

        return redirect("/login")

    if request.method == "POST":

        # Get form values
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()


        # =====================================================
        # VALIDATION
        # =====================================================

        if not title:

            return "Complaint title is required."

        if not category:

            return "Complaint category is required."

        if not description:

            return "Complaint description is required."

        if not location:

            return "Complaint location is required."


        # =====================================================
        # LENGTH VALIDATION
        # =====================================================

        if len(title) > 255:

            return "Complaint title must be 255 characters or less."

        if len(category) > 100:

            return "Complaint category must be 100 characters or less."

        if len(location) > 255:

            return "Complaint location must be 255 characters or less."

        if len(description) > 5000:

            return "Complaint description must be 5000 characters or less."


        # =====================================================
        # DATABASE CONNECTION
        # =====================================================

        connection = get_db_connection()
        cursor = connection.cursor()


        # =====================================================
        # INSERT COMPLAINT
        # =====================================================

        sql = """
        INSERT INTO complaints
        (user_id, title, category, description, location)
        VALUES (%s, %s, %s, %s, %s)
        """


        values = (
            session["user_id"],
            title,
            category,
            description,
            location
        )


        try:

            cursor.execute(sql, values)

            connection.commit()

            # =================================================
            # GET NEW COMPLAINT ID
            # =================================================

            complaint_id = cursor.lastrowid


        except mysql.connector.Error as error:

            connection.rollback()

            return f"Database error: {error}"


        finally:

            cursor.close()

            connection.close()


        # =====================================================
        # STEP 25.3
        # SHOW COMPLAINT SUCCESS PAGE
        # =====================================================

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

    sql = """
    SELECT *
    FROM complaints
    WHERE user_id = %s
    ORDER BY created_at DESC
    """

    cursor.execute(
        sql,
        (session["user_id"],)
    )

    complaints = cursor.fetchall()

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

    # Check user login
    if "user_id" not in session:

        return redirect("/login")


    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)


    # Get only this user's complaint
    sql = """
        SELECT *
        FROM complaints
        WHERE id = %s
        AND user_id = %s
    """


    try:

        cursor.execute(
            sql,
            (
                complaint_id,
                session["user_id"]
            )
        )

        complaint = cursor.fetchone()


    except mysql.connector.Error as error:

        cursor.close()
        connection.close()

        return f"Database error: {error}"


    cursor.close()
    connection.close()


    # Complaint not found
    if complaint is None:

        return render_template(
            "complaint_details.html",
            complaint=None
        )


    return render_template(
        "complaint_details.html",
        complaint=complaint
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

    sql = """
    SELECT *
    FROM complaints
    WHERE user_id = %s
    ORDER BY created_at DESC
    """

    cursor.execute(
        sql,
        (session["user_id"],)
    )

    complaints = cursor.fetchall()

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

        email = request.form["email"]
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
        SELECT *
        FROM admins
        WHERE email = %s
        """

        cursor.execute(
            sql,
            (email,)
        )

        admin = cursor.fetchone()

        cursor.close()
        connection.close()

        if admin and check_password_hash(
            admin["password"],
            password
        ):

            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["name"]
            session["admin_email"] = admin["email"]

            return redirect("/admin-dashboard")

        return "Invalid admin email or password"

    return render_template("admin_login.html")


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin-dashboard")
def admin_dashboard():

    if "admin_id" not in session:

        return redirect("/admin-login")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)


    # =====================================================
    # TOTAL COMPLAINTS
    # =====================================================

    cursor.execute(
        "SELECT COUNT(*) AS total FROM complaints"
    )

    total_complaints = cursor.fetchone()["total"]


    # =====================================================
    # PENDING COMPLAINTS
    # =====================================================

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM complaints
        WHERE status = %s
        """,
        ("Pending",)
    )

    pending_complaints = cursor.fetchone()["total"]


    # =====================================================
    # IN PROGRESS COMPLAINTS
    # =====================================================

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM complaints
        WHERE status = %s
        """,
        ("In Progress",)
    )

    in_progress_complaints = cursor.fetchone()["total"]


    # =====================================================
    # RESOLVED COMPLAINTS
    # =====================================================

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM complaints
        WHERE status = %s
        """,
        ("Resolved",)
    )

    resolved_complaints = cursor.fetchone()["total"]


    # =====================================================
    # CATEGORY-WISE COMPLAINTS
    # =====================================================

    cursor.execute(
        """
        SELECT
            category,
            COUNT(*) AS total
        FROM complaints
        GROUP BY category
        ORDER BY total DESC
        """
    )

    category_complaints = cursor.fetchall()


    # =====================================================
    # CLOSE DATABASE
    # =====================================================

    cursor.close()
    db.close()


    # =====================================================
    # SEND DATA TO HTML
    # =====================================================

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

    # Check admin login
    if "admin_id" not in session:

        return redirect("/admin-login")


    # =====================================================
    # GET SEARCH TEXT
    # =====================================================

    search = request.args.get(
        "search",
        ""
    ).strip()


    # =====================================================
    # GET STATUS FILTER
    # =====================================================

    selected_status = request.args.get(
        "status",
        ""
    ).strip()


    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)


    # =====================================================
    # BASE SQL
    # =====================================================

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

        INNER JOIN users
            ON complaints.user_id = users.id

        WHERE 1 = 1
    """


    values = []


    # =====================================================
    # SEARCH
    # =====================================================

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

        values.extend([
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value
        ])


    # =====================================================
    # STATUS FILTER
    # =====================================================

    if selected_status:

        sql += """
            AND complaints.status = %s
        """

        values.append(selected_status)


    # =====================================================
    # ORDER BY
    # =====================================================

    sql += """
        ORDER BY complaints.created_at DESC
    """


    # =====================================================
    # EXECUTE QUERY
    # =====================================================

    try:

        cursor.execute(
            sql,
            values
        )

        complaints = cursor.fetchall()

    except mysql.connector.Error as error:

        cursor.close()
        connection.close()

        return f"Database error: {error}"


    # =====================================================
    # CLOSE DATABASE
    # =====================================================

    cursor.close()
    connection.close()


    # =====================================================
    # SEND DATA TO HTML
    # =====================================================

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

    # Check admin login
    if "admin_id" not in session:

        return redirect("/admin-login")


    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)


    # =====================================================
    # GET COMPLAINT DETAILS
    # =====================================================

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

            users.email AS user_email,

            users.phone AS user_phone

        FROM complaints

        INNER JOIN users
            ON complaints.user_id = users.id

        WHERE complaints.id = %s
    """


    try:

        cursor.execute(
            sql,
            (complaint_id,)
        )

        complaint = cursor.fetchone()


    except mysql.connector.Error as error:

        cursor.close()
        connection.close()

        return f"Database error: {error}"


    cursor.close()
    connection.close()


    # =====================================================
    # COMPLAINT NOT FOUND
    # =====================================================

    if complaint is None:

        return "Complaint not found"


    return render_template(
        "admin_complaint_details.html",
        complaint=complaint
    )


# =========================================================
# DELETE COMPLAINT
# =========================================================

@app.route(
    "/admin/delete-complaint/<int:complaint_id>",
    methods=["POST"]
)
def admin_delete_complaint(complaint_id):

    # Check admin login
    if "admin_id" not in session:

        return redirect("/admin-login")


    connection = get_db_connection()
    cursor = connection.cursor()


    try:

        # Delete complaint
        cursor.execute(
            """
            DELETE FROM complaints
            WHERE id = %s
            """,
            (complaint_id,)
        )

        connection.commit()


    except mysql.connector.Error as error:

        connection.rollback()

        cursor.close()
        connection.close()

        return f"Database error: {error}"


    cursor.close()
    connection.close()


    # Return to complaint management
    return redirect("/admin/complaints")


# =========================================================
# UPDATE COMPLAINT STATUS
# =========================================================

@app.route(
    "/admin/update-complaint/<int:complaint_id>",
    methods=["POST"]
)
def update_complaint(complaint_id):

    # Check admin login
    if "admin_id" not in session:

        return redirect("/admin-login")


    status = request.form.get("status")


    # =====================================================
    # ALLOWED STATUS VALUES
    # =====================================================

    allowed_statuses = [
        "Pending",
        "In Progress",
        "Resolved",
        "Rejected"
    ]


    if status not in allowed_statuses:

        return "Invalid complaint status"


    connection = get_db_connection()
    cursor = connection.cursor()


    sql = """
    UPDATE complaints

    SET status = %s

    WHERE id = %s
    """


    try:

        cursor.execute(
            sql,
            (status, complaint_id)
        )

        connection.commit()


    except mysql.connector.Error as error:

        connection.rollback()

        cursor.close()
        connection.close()

        return f"Database error: {error}"


    cursor.close()
    connection.close()


    return redirect("/admin/complaints")


# =========================================================
# USER LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    # Clear user session
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)

    return redirect("/login")


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin-logout")
def admin_logout():

    # Clear admin session
    session.pop("admin_id", None)
    session.pop("admin_name", None)
    session.pop("admin_email", None)

    return redirect("/admin-login")


# =========================================================
# RUN APPLICATION
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
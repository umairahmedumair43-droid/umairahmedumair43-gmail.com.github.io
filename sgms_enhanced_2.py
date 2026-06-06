import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import hashlib
import re
import logging
import json
import os
from datetime import datetime
from pathlib import Path

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
CONFIG_FILE = "sgms_config.json"
DB_PATH = "sgms_database.db"
LOG_FILE = "sgms.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    "db_path": DB_PATH,
    "window_size": "1100x680",
    "max_semester": 8,
    "min_password_length": 6,
    "hash_algorithm": "sha256"
}

COLORS = {
    "bg_dark":       "#0F1117",
    "sidebar_bg":    "#161B27",
    "sidebar_hover": "#1E2535",
    "accent":        "#4F8EF7",
    "accent_hover":  "#3A78E0",
    "success":       "#22C55E",
    "danger":        "#EF4444",
    "warning":       "#F59E0B",
    "card_bg":       "#1C2333",
    "card_border":   "#2A3347",
    "text_primary":  "#E8ECF4",
    "text_secondary":"#8A95A8",
    "input_bg":      "#111827",
    "input_border":  "#2A3347",
    "row_even":      "#161B27",
    "row_odd":       "#1C2333",
    "heading_bg":    "#0D1120",
}

LETTER_GRADES = {
    (90, 100): ("A+", COLORS["success"]),
    (85,  90): ("A",  COLORS["success"]),
    (80,  85): ("A-", "#4ADE80"),
    (75,  80): ("B+", "#34D399"),
    (70,  75): ("B",  COLORS["accent"]),
    (65,  70): ("B-", "#60A5FA"),
    (60,  65): ("C+", COLORS["warning"]),
    (55,  60): ("C",  "#FBBF24"),
    (50,  55): ("C-", "#F97316"),
    ( 0,  50): ("F",  COLORS["danger"]),
}

def load_config():
    """Load configuration from file or use defaults."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

CONFIG = load_config()

def save_config(config):
    """Save configuration to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info("Configuration saved")
    except Exception as e:
        logger.error(f"Error saving config: {e}")

def get_letter_grade(marks):
    """Get letter grade and color for given marks."""
    try:
        marks = float(marks)
        for (lo, hi), (grade, color) in LETTER_GRADES.items():
            if lo <= marks <= hi:
                return grade, color
    except (ValueError, TypeError):
        pass
    return "F", COLORS["danger"]

def hash_password(pw):
    """Hash password using SHA-256."""
    try:
        return hashlib.sha256(pw.encode()).hexdigest()
    except Exception as e:
        logger.error(f"Error hashing password: {e}")
        return None

def validate_email(email):
    """Validate email format."""
    if not email:
        return True  # Email is optional
    pattern = r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Validate phone number format."""
    if not phone:
        return True  # Phone is optional
    # Remove common separators and spaces
    clean_phone = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    return bool(re.match(r"^\d{10,15}$", clean_phone))

def validate_semester(sem_str):
    """Validate semester input."""
    try:
        sem = int(sem_str) if sem_str else 1
        max_sem = CONFIG.get("max_semester", 8)
        return 1 <= sem <= max_sem
    except ValueError:
        return False

# ==========================================
# DATABASE LAYER
# ==========================================
class Database:
    """Database manager with error handling and logging."""
    
    def __init__(self, db_path=None):
        self.path = db_path or CONFIG.get("db_path", DB_PATH)
        self.connection = None
        logger.info(f"Database initialized at {self.path}")

    def connect(self):
        """Create database connection with foreign key support."""
        try:
            conn = sqlite3.connect(self.path)
            conn.execute("PRAGMA foreign_keys = ON")
            logger.debug("Database connection established")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise

    def setup(self):
        """Initialize database schema and seed default data."""
        try:
            with self.connect() as conn:
                c = conn.cursor()
                c.executescript('''
                    CREATE TABLE IF NOT EXISTS users (
                        id       INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT    UNIQUE NOT NULL,
                        password TEXT    NOT NULL,
                        role     TEXT    NOT NULL CHECK(role IN ('Admin','Teacher','Student')),
                        created_at TEXT DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS students (
                        studentID INTEGER PRIMARY KEY AUTOINCREMENT,
                        name      TEXT    NOT NULL,
                        regNo     TEXT    UNIQUE NOT NULL,
                        email     TEXT,
                        phone     TEXT,
                        program   TEXT,
                        semester  INTEGER DEFAULT 1,
                        created   TEXT    DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS courses (
                        courseID    INTEGER PRIMARY KEY AUTOINCREMENT,
                        courseCode  TEXT    UNIQUE NOT NULL,
                        courseName  TEXT    NOT NULL,
                        creditHours INTEGER NOT NULL DEFAULT 3,
                        teacherName TEXT,
                        description TEXT,
                        created_at  TEXT    DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS grades (
                        gradeID     INTEGER PRIMARY KEY AUTOINCREMENT,
                        studentID   INTEGER NOT NULL,
                        courseID    INTEGER NOT NULL,
                        marks       REAL    NOT NULL CHECK(marks BETWEEN 0 AND 100),
                        letterGrade TEXT,
                        gradePoints REAL,
                        updatedAt   TEXT    DEFAULT (datetime('now')),
                        FOREIGN KEY(studentID) REFERENCES students(studentID) ON DELETE CASCADE,
                        FOREIGN KEY(courseID)  REFERENCES courses(courseID)   ON DELETE CASCADE,
                        UNIQUE(studentID, courseID)
                    );
                ''')
                self._migrate_schema(c)
                self._seed_users(c)
                conn.commit()
                logger.info("Database setup completed successfully")
        except sqlite3.Error as e:
            logger.error(f"Database setup error: {e}")
            raise

    def _migrate_schema(self, c):
        """Add missing columns to existing database schema."""
        migrations = [
            ("students", "phone",    "TEXT"),
            ("students", "program",  "TEXT"),
            ("students", "semester", "INTEGER DEFAULT 1"),
            ("students", "created",  "TEXT DEFAULT (datetime('now'))"),
            ("courses",  "courseCode",  "TEXT"),
            ("courses",  "description", "TEXT"),
            ("courses",  "created_at",  "TEXT DEFAULT (datetime('now'))"),
            ("grades",   "gradePoints", "REAL"),
            ("grades",   "updatedAt",   "TEXT DEFAULT (datetime('now'))"),
        ]
        
        for table, column, col_type in migrations:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"Added column {column} to {table}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Ensure courseCode has unique values
        try:
            c.execute("UPDATE courses SET courseCode = 'C-' || courseID WHERE courseCode IS NULL OR courseCode = ''")
        except sqlite3.OperationalError:
            pass

    def _seed_users(self, c):
        """Seed default user accounts with hashed passwords."""
        defaults = [
            ("admin",   "admin123",   "Admin"),
            ("teacher", "teacher123", "Teacher"),
            ("student", "student123", "Student"),
        ]
        
        for username, password, role in defaults:
            hashed = hash_password(password)
            try:
                row = c.execute("SELECT id, password FROM users WHERE username=?",
                                (username,)).fetchone()
                if row is None:
                    c.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                              (username, hashed, role))
                    logger.info(f"Created default user: {username}")
                else:
                    uid, stored_pw = row
                    if stored_pw != hashed:
                        c.execute("UPDATE users SET password=?, role=? WHERE id=?",
                                  (hashed, role, uid))
                        logger.info(f"Updated default user: {username}")
            except sqlite3.Error as e:
                logger.error(f"Error seeding user {username}: {e}")

    # ---- Authentication ----
    def authenticate(self, username, password):
        """Authenticate user with username and password."""
        try:
            pw_hash = hash_password(password)
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT role FROM users WHERE username=? AND password=?",
                    (username, pw_hash)
                ).fetchone()
            result = row[0] if row else None
            if result:
                logger.info(f"Successful login: {username}")
            else:
                logger.warning(f"Failed login attempt: {username}")
            return result
        except sqlite3.Error as e:
            logger.error(f"Authentication error: {e}")
            return None

    # ---- User Management ----
    def get_all_users(self):
        """Get all users ordered by role and username."""
        try:
            with self.connect() as conn:
                return conn.execute(
                    "SELECT id, username, role FROM users ORDER BY role, username"
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching users: {e}")
            return []

    def add_user(self, username, password, role):
        """Add new user account."""
        try:
            pw_hash = hash_password(password)
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO users (username, password, role) VALUES (?,?,?)",
                    (username, pw_hash, role)
                )
            logger.info(f"User created: {username} ({role})")
        except sqlite3.IntegrityError:
            logger.warning(f"User already exists: {username}")
            raise ValueError(f"Username '{username}' already exists")
        except sqlite3.Error as e:
            logger.error(f"Error adding user: {e}")
            raise

    def delete_user(self, uid):
        """Delete user by ID."""
        try:
            with self.connect() as conn:
                conn.execute("DELETE FROM users WHERE id=?", (uid,))
            logger.info(f"User deleted: ID {uid}")
        except sqlite3.Error as e:
            logger.error(f"Error deleting user: {e}")
            raise

    # ---- Student Management ----
    def get_students(self, search=""):
        """Get students with optional search filter."""
        try:
            with self.connect() as conn:
                if search:
                    q = f"%{search}%"
                    return conn.execute(
                        "SELECT studentID, name, regNo, email, program, semester FROM students "
                        "WHERE name LIKE ? OR regNo LIKE ? OR email LIKE ? ORDER BY name",
                        (q, q, q)
                    ).fetchall()
                return conn.execute(
                    "SELECT studentID, name, regNo, email, program, semester FROM students ORDER BY name"
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching students: {e}")
            return []

    def add_student(self, name, reg_no, email, phone, program, semester):
        """Add new student record."""
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO students (name, regNo, email, phone, program, semester) VALUES (?,?,?,?,?,?)",
                    (name, reg_no, email, phone, program, semester)
                )
            logger.info(f"Student added: {name} ({reg_no})")
        except sqlite3.IntegrityError:
            logger.warning(f"Registration number already exists: {reg_no}")
            raise ValueError(f"Registration number '{reg_no}' already exists")
        except sqlite3.Error as e:
            logger.error(f"Error adding student: {e}")
            raise

    def update_student(self, sid, name, reg_no, email, phone, program, semester):
        """Update existing student record."""
        try:
            with self.connect() as conn:
                conn.execute(
                    "UPDATE students SET name=?, regNo=?, email=?, phone=?, program=?, semester=? WHERE studentID=?",
                    (name, reg_no, email, phone, program, semester, sid)
                )
            logger.info(f"Student updated: {name} (ID: {sid})")
        except sqlite3.Error as e:
            logger.error(f"Error updating student: {e}")
            raise

    def delete_student(self, sid):
        """Delete student by ID (cascades to grades)."""
        try:
            with self.connect() as conn:
                conn.execute("DELETE FROM students WHERE studentID=?", (sid,))
            logger.info(f"Student deleted: ID {sid}")
        except sqlite3.Error as e:
            logger.error(f"Error deleting student: {e}")
            raise

    def count_students(self):
        """Get total student count."""
        try:
            with self.connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Error counting students: {e}")
            return 0

    # ---- Course Management ----
    def get_courses(self, search=""):
        """Get courses with optional search filter."""
        try:
            with self.connect() as conn:
                if search:
                    q = f"%{search}%"
                    return conn.execute(
                        "SELECT courseID, courseCode, courseName, creditHours, teacherName FROM courses "
                        "WHERE courseName LIKE ? OR courseCode LIKE ? OR teacherName LIKE ? ORDER BY courseName",
                        (q, q, q)
                    ).fetchall()
                return conn.execute(
                    "SELECT courseID, courseCode, courseName, creditHours, teacherName FROM courses ORDER BY courseName"
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching courses: {e}")
            return []

    def add_course(self, code, name, credits, teacher, desc):
        """Add new course."""
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO courses (courseCode, courseName, creditHours, teacherName, description) VALUES (?,?,?,?,?)",
                    (code, name, credits, teacher, desc)
                )
            logger.info(f"Course added: {code} - {name}")
        except sqlite3.IntegrityError:
            logger.warning(f"Course code already exists: {code}")
            raise ValueError(f"Course code '{code}' already exists")
        except sqlite3.Error as e:
            logger.error(f"Error adding course: {e}")
            raise

    def update_course(self, cid, code, name, credits, teacher, desc):
        """Update existing course."""
        try:
            with self.connect() as conn:
                conn.execute(
                    "UPDATE courses SET courseCode=?, courseName=?, creditHours=?, teacherName=?, description=? WHERE courseID=?",
                    (code, name, credits, teacher, desc, cid)
                )
            logger.info(f"Course updated: {code} (ID: {cid})")
        except sqlite3.Error as e:
            logger.error(f"Error updating course: {e}")
            raise

    def delete_course(self, cid):
        """Delete course by ID (cascades to grades)."""
        try:
            with self.connect() as conn:
                conn.execute("DELETE FROM courses WHERE courseID=?", (cid,))
            logger.info(f"Course deleted: ID {cid}")
        except sqlite3.Error as e:
            logger.error(f"Error deleting course: {e}")
            raise

    def count_courses(self):
        """Get total course count."""
        try:
            with self.connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Error counting courses: {e}")
            return 0

    def get_course_names(self):
        """Get list of courses for dropdown."""
        try:
            with self.connect() as conn:
                return conn.execute("SELECT courseID, courseName, courseCode FROM courses ORDER BY courseName").fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching course names: {e}")
            return []

    def get_student_names(self):
        """Get list of students for dropdown."""
        try:
            with self.connect() as conn:
                return conn.execute("SELECT studentID, name, regNo FROM students ORDER BY name").fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching student names: {e}")
            return []

    # ---- Grade Management ----
    def get_grades(self, search=""):
        """Get grades with optional search filter."""
        try:
            with self.connect() as conn:
                if search:
                    q = f"%{search}%"
                    return conn.execute(
                        "SELECT g.gradeID, s.name, s.regNo, c.courseName, g.marks, g.letterGrade "
                        "FROM grades g JOIN students s ON g.studentID=s.studentID "
                        "JOIN courses c ON g.courseID=c.courseID "
                        "WHERE s.name LIKE ? OR s.regNo LIKE ? OR c.courseName LIKE ? "
                        "ORDER BY s.name",
                        (q, q, q)
                    ).fetchall()
                return conn.execute(
                    "SELECT g.gradeID, s.name, s.regNo, c.courseName, g.marks, g.letterGrade "
                    "FROM grades g JOIN students s ON g.studentID=s.studentID "
                    "JOIN courses c ON g.courseID=c.courseID ORDER BY s.name"
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching grades: {e}")
            return []

    def save_grade(self, student_id, course_id, marks):
        """Save or update grade for student-course pair."""
        try:
            letter, _ = get_letter_grade(marks)
            gp = self._grade_points(letter)
            with self.connect() as conn:
                # Check if grade exists
                existing = conn.execute(
                    "SELECT gradeID FROM grades WHERE studentID=? AND courseID=?",
                    (student_id, course_id)
                ).fetchone()
                
                if existing:
                    # Update existing grade
                    conn.execute(
                        "UPDATE grades SET marks=?, letterGrade=?, gradePoints=?, updatedAt=datetime('now') "
                        "WHERE studentID=? AND courseID=?",
                        (marks, letter, gp, student_id, course_id)
                    )
                else:
                    # Insert new grade
                    conn.execute(
                        "INSERT INTO grades (studentID, courseID, marks, letterGrade, gradePoints, updatedAt) "
                        "VALUES (?,?,?,?,?,datetime('now'))",
                        (student_id, course_id, marks, letter, gp)
                    )
            logger.info(f"Grade saved: Student {student_id}, Course {course_id}, Marks {marks}")
        except sqlite3.Error as e:
            logger.error(f"Error saving grade: {e}")
            raise

    def _grade_points(self, letter):
        """Convert letter grade to GPA points."""
        mapping = {
            "A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0,
            "B-": 2.7, "C+": 2.3, "C": 2.0, "C-": 1.7, "D": 1.0, "F": 0.0
        }
        return mapping.get(letter, 0.0)

    def delete_grade(self, gid):
        """Delete grade record."""
        try:
            with self.connect() as conn:
                conn.execute("DELETE FROM grades WHERE gradeID=?", (gid,))
            logger.info(f"Grade deleted: ID {gid}")
        except sqlite3.Error as e:
            logger.error(f"Error deleting grade: {e}")
            raise

    def count_grades(self):
        """Get total grade count."""
        try:
            with self.connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Error counting grades: {e}")
            return 0

    def get_report(self):
        """Get student performance report."""
        try:
            with self.connect() as conn:
                return conn.execute(
                    "SELECT s.name, s.regNo, s.program, "
                    "ROUND(AVG(g.marks),2) as avg_marks, "
                    "ROUND(AVG(g.gradePoints),2) as cgpa, "
                    "COUNT(g.gradeID) as total_courses "
                    "FROM students s LEFT JOIN grades g ON s.studentID=g.studentID "
                    "GROUP BY s.studentID ORDER BY avg_marks DESC"
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error generating report: {e}")
            return []

    def get_course_stats(self):
        """Get course statistics report."""
        try:
            with self.connect() as conn:
                return conn.execute(
                    "SELECT c.courseName, COUNT(g.gradeID) as enrolled, "
                    "ROUND(AVG(g.marks),2) as avg, MAX(g.marks) as highest, MIN(g.marks) as lowest "
                    "FROM courses c LEFT JOIN grades g ON c.courseID=g.courseID "
                    "GROUP BY c.courseID ORDER BY c.courseName"
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error generating course stats: {e}")
            return []

    def get_top_students(self, limit=5):
        """Get top performing students."""
        try:
            with self.connect() as conn:
                return conn.execute(
                    "SELECT s.name, s.regNo, ROUND(AVG(g.marks),1) as avg "
                    "FROM students s JOIN grades g ON s.studentID=g.studentID "
                    "GROUP BY s.studentID ORDER BY avg DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching top students: {e}")
            return []


# ==========================================
# STYLED WIDGET HELPERS
# ==========================================
C = COLORS

def styled_label(parent, text, size=11, weight="normal", color=None, **kw):
    """Create styled label."""
    color = color or C["text_primary"]
    return tk.Label(parent, text=text, font=("Segoe UI", size, weight),
                    bg=parent["bg"], fg=color, **kw)

def styled_entry(parent, width=30, show=None):
    """Create styled entry widget."""
    e = tk.Entry(parent, font=("Segoe UI", 11), bg=C["input_bg"],
                 fg=C["text_primary"], insertbackground=C["text_primary"],
                 relief="flat", bd=0, width=width,
                 highlightthickness=1, highlightbackground=C["input_border"],
                 highlightcolor=C["accent"])
    if show:
        e.config(show=show)
    return e

def styled_button(parent, text, command, color=None, hover_color=None,
                  font_size=10, width=None):
    """Create styled button with hover effect."""
    bg = color or C["accent"]
    hov = hover_color or C["accent_hover"]
    kw = dict(font=("Segoe UI", font_size, "bold"), bg=bg, fg="white",
              relief="flat", bd=0, cursor="hand2", command=command,
              activebackground=hov, activeforeground="white")
    if width:
        kw["width"] = width
    btn = tk.Button(parent, text=text, **kw)
    btn.bind("<Enter>", lambda e: btn.config(bg=hov))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn

def separator(parent, color=None):
    """Create separator line."""
    return tk.Frame(parent, bg=color or C["card_border"], height=1)

def card(parent, padx=16, pady=12, **kw):
    """Create card frame."""
    return tk.Frame(parent, bg=C["card_bg"],
                    highlightthickness=1,
                    highlightbackground=C["card_border"],
                    padx=padx, pady=pady, **kw)


# ==========================================
# MAIN APPLICATION
# ==========================================
class SGMSApp:
    """Main application class."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SGMS — Student Grade Management System")
        
        # Load window size from config
        window_size = CONFIG.get("window_size", "1100x680")
        self.root.geometry(window_size)
        self.root.configure(bg=C["bg_dark"])
        self.root.resizable(True, True)
        
        self.db = Database()
        try:
            self.db.setup()
        except Exception as e:
            logger.error(f"Failed to setup database: {e}")
            messagebox.showerror("Database Error", "Failed to initialize database")
            self.root.quit()
            return
        
        self._current_role = None
        self._nav_buttons = {}
        self._setup_styles()
        self.show_login()
        logger.info("Application started")

    def _setup_styles(self):
        """Configure ttk styles."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                        background=C["card_bg"], foreground=C["text_primary"],
                        fieldbackground=C["card_bg"], rowheight=34,
                        font=("Segoe UI", 10))
        style.configure("Dark.Treeview.Heading",
                        background=C["heading_bg"], foreground=C["text_secondary"],
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Dark.Treeview",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "white")])
        style.configure("Dark.Vertical.TScrollbar",
                        troughcolor=C["bg_dark"], background=C["card_border"])
        
        # Configure Combobox styling
        style.configure("Dark.TCombobox",
                        fieldbackground=C["input_bg"],
                        background=C["input_bg"],
                        foreground=C["text_primary"])

    def clear(self):
        """Clear all widgets from root."""
        for w in self.root.winfo_children():
            w.destroy()

    # ==========================
    # LOGIN SCREEN
    # ==========================
    def show_login(self):
        """Display login screen."""
        self.clear()
        self._current_role = None

        outer = tk.Frame(self.root, bg=C["bg_dark"])
        outer.place(relx=0.5, rely=0.5, anchor="center")

        # Brand header
        brand = tk.Frame(outer, bg=C["bg_dark"])
        brand.pack(pady=(0, 30))
        tk.Label(brand, text="SGMS", font=("Segoe UI", 36, "bold"),
                 bg=C["bg_dark"], fg=C["accent"]).pack()
        tk.Label(brand, text="Student Grade Management System",
                 font=("Segoe UI", 11), bg=C["bg_dark"],
                 fg=C["text_secondary"]).pack()

        # Login card
        login_card = tk.Frame(outer, bg=C["card_bg"],
                              highlightthickness=1,
                              highlightbackground=C["card_border"],
                              padx=40, pady=32)
        login_card.pack()

        styled_label(login_card, "Welcome back", size=16, weight="bold").pack(pady=(0, 4))
        styled_label(login_card, "Sign in to continue", size=10,
                     color=C["text_secondary"]).pack(pady=(0, 20))

        # Username
        styled_label(login_card, "USERNAME", size=9,
                     color=C["text_secondary"]).pack(anchor="w")
        self.e_user = styled_entry(login_card, width=32)
        self.e_user.pack(ipady=7, pady=(3, 12))
        self.e_user.focus()

        # Password
        styled_label(login_card, "PASSWORD", size=9,
                     color=C["text_secondary"]).pack(anchor="w")
        self.e_pass = styled_entry(login_card, width=32, show="●")
        self.e_pass.pack(ipady=7, pady=(3, 20))
        self.e_pass.bind("<Return>", lambda e: self._do_login())

        styled_button(login_card, "  Sign In  →  ", self._do_login,
                      font_size=11).pack(fill="x", ipady=8)

        # Demo credentials panel
        cred_frame = tk.Frame(login_card, bg=C["input_bg"],
                              highlightthickness=1,
                              highlightbackground=C["card_border"])
        cred_frame.pack(fill="x", pady=(14, 0))
        styled_label(cred_frame, "  Quick Login", size=8,
                     color=C["text_secondary"]).pack(anchor="w", padx=10, pady=(8, 4))
        demo_accounts = [
            ("Admin",   "admin",   "admin123",   C["danger"]),
            ("Teacher", "teacher", "teacher123", C["warning"]),
            ("Student", "student", "student123", C["success"]),
        ]
        for role_label, uname, pwd, dot_color in demo_accounts:
            row = tk.Frame(cred_frame, bg=C["input_bg"])
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text="●", font=("Segoe UI", 8), bg=C["input_bg"], fg=dot_color).pack(side="left")
            tk.Label(row, text=f" {role_label}", font=("Segoe UI", 9, "bold"),
                     bg=C["input_bg"], fg=C["text_primary"], width=9, anchor="w").pack(side="left")
            tk.Label(row, text=f"{uname} / {pwd}", font=("Courier New", 9),
                     bg=C["input_bg"], fg=C["text_secondary"]).pack(side="left")
            def _fill(u=uname, p=pwd):
                self.e_user.delete(0, "end")
                self.e_user.insert(0, u)
                self.e_pass.delete(0, "end")
                self.e_pass.insert(0, p)
            tk.Button(row, text="Use", font=("Segoe UI", 8), bg=C["input_bg"],
                      fg=C["accent"], relief="flat", cursor="hand2",
                      activebackground=C["input_bg"], activeforeground=C["accent_hover"],
                      command=_fill).pack(side="right")
        tk.Frame(cred_frame, bg=C["input_bg"], height=8).pack()

    def _do_login(self):
        """Handle login authentication."""
        u = self.e_user.get().strip()
        p = self.e_pass.get()
        if not u or not p:
            messagebox.showwarning("Input Required", "Please enter username and password.")
            return
        
        role = self.db.authenticate(u, p)
        if role:
            self._current_role = role
            self.show_dashboard(role)
        else:
            messagebox.showerror("Login Failed", "Invalid username or password.")
            self.e_pass.delete(0, "end")

    # ==========================
    # DASHBOARD SHELL
    # ==========================
    def show_dashboard(self, role):
        """Display main dashboard with sidebar navigation."""
        self.clear()

        # ---- Sidebar ----
        sidebar = tk.Frame(self.root, bg=C["sidebar_bg"], width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Brand
        tk.Frame(sidebar, bg=C["accent"], height=3).pack(fill="x")
        tk.Label(sidebar, text="SGMS", font=("Segoe UI", 20, "bold"),
                 bg=C["sidebar_bg"], fg=C["accent"]).pack(pady=(18, 2))
        tk.Label(sidebar, text=f"Logged in as  {role}",
                 font=("Segoe UI", 8), bg=C["sidebar_bg"],
                 fg=C["text_secondary"]).pack(pady=(0, 20))
        separator(sidebar).pack(fill="x", padx=12, pady=(0, 12))

        # Nav items — role-based access
        if role == "Admin":
            nav_items = [
                ("dashboard", "🏠  Dashboard",    self._go_dashboard),
                ("students",  "👨‍🎓  Students",     self._go_students),
                ("courses",   "📚  Courses",       self._go_courses),
                ("grades",    "📝  Grades",        self._go_grades),
                ("reports",   "📊  Reports",       self._go_reports),
                ("users",     "👤  User Accounts", self._go_users),
            ]
        elif role == "Teacher":
            nav_items = [
                ("dashboard", "🏠  Dashboard",    self._go_dashboard),
                ("students",  "👨‍🎓  Students",     self._go_students),
                ("courses",   "📚  Courses",       self._go_courses),
                ("grades",    "📝  Enter Grades",  self._go_grades),
                ("reports",   "📊  Reports",       self._go_reports),
            ]
        else:  # Student
            nav_items = [
                ("dashboard", "🏠  Dashboard",    self._go_dashboard),
                ("grades",    "📝  My Grades",     self._go_student_grades),
                ("courses",   "📚  Course List",   self._go_courses_readonly),
            ]

        self._nav_buttons = {}
        self._active_nav = "dashboard"
        
        for key, label, cmd in nav_items:
            btn = tk.Button(sidebar, text=label,
                            font=("Segoe UI", 10), bg=C["sidebar_bg"],
                            fg=C["text_primary"], relief="flat",
                            anchor="w", padx=20, cursor="hand2",
                            activebackground=C["sidebar_hover"],
                            activeforeground=C["text_primary"],
                            command=lambda c=cmd, k=key: (c(), self._highlight_nav(k)))
            btn.pack(fill="x", ipady=9)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=C["sidebar_hover"]))
            btn.bind("<Leave>", lambda e, b=btn, k=key:
                     b.config(bg=C["accent"] if self._active_nav == k else C["sidebar_bg"]))
            self._nav_buttons[key] = btn

        # Logout at bottom
        separator(sidebar).pack(fill="x", padx=12, pady=8)
        logout_btn = tk.Button(sidebar, text="⬅  Log Out",
                               font=("Segoe UI", 10), bg=C["sidebar_bg"],
                               fg=C["danger"], relief="flat", anchor="w",
                               padx=20, cursor="hand2",
                               command=self.show_login)
        logout_btn.pack(fill="x", ipady=9, side="bottom", pady=(0, 10))
        logout_btn.bind("<Enter>", lambda e: logout_btn.config(bg="#2A1A1A"))
        logout_btn.bind("<Leave>", lambda e: logout_btn.config(bg=C["sidebar_bg"]))

        # ---- Content area ----
        self.content = tk.Frame(self.root, bg=C["bg_dark"])
        self.content.pack(side="right", fill="both", expand=True)

        self._highlight_nav("dashboard")
        self._go_dashboard()

    def _highlight_nav(self, key):
        """Highlight active navigation button."""
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.config(bg=C["accent"], fg="white")
            else:
                btn.config(bg=C["sidebar_bg"], fg=C["text_primary"])
        self._active_nav = key

    def _clear_content(self):
        """Clear content area."""
        for w in self.content.winfo_children():
            w.destroy()

    def _page_header(self, title, subtitle=""):
        """Create page header."""
        hdr = tk.Frame(self.content, bg=C["bg_dark"])
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        tk.Label(hdr, text=title, font=("Segoe UI", 18, "bold"),
                 bg=C["bg_dark"], fg=C["text_primary"]).pack(side="left")
        if subtitle:
            tk.Label(hdr, text=subtitle, font=("Segoe UI", 10),
                     bg=C["bg_dark"], fg=C["text_secondary"]).pack(side="left", padx=(10, 0), pady=(6, 0))
        return hdr

    def _search_bar(self, parent, callback, placeholder="Search…"):
        """Create search bar widget."""
        f = tk.Frame(parent, bg=C["bg_dark"])
        e = styled_entry(f, width=28)
        e.pack(side="left", ipady=6)
        e.insert(0, placeholder)
        e.config(fg=C["text_secondary"])

        def on_focus_in(ev):
            if e.get() == placeholder:
                e.delete(0, "end")
                e.config(fg=C["text_primary"])

        def on_focus_out(ev):
            if not e.get():
                e.insert(0, placeholder)
                e.config(fg=C["text_secondary"])

        e.bind("<FocusIn>", on_focus_in)
        e.bind("<FocusOut>", on_focus_out)
        e.bind("<KeyRelease>", lambda ev: callback(
            "" if e.get() == placeholder else e.get()))

        styled_label(f, "🔍", size=12, color=C["text_secondary"]).pack(side="left", padx=(6, 0))
        return f, e

    def _build_tree(self, parent, columns, col_widths=None, col_anchors=None):
        """Create styled treeview."""
        frame = tk.Frame(parent, bg=C["bg_dark"])
        tree = ttk.Treeview(frame, columns=columns, show="headings",
                            style="Dark.Treeview")
        for i, col in enumerate(columns):
            tree.heading(col, text=col, anchor="w")
            w = (col_widths or {}).get(col, 140)
            a = (col_anchors or {}).get(col, "w")
            tree.column(col, width=w, anchor=a, stretch=True)
        tree.tag_configure("even", background=C["row_even"])
        tree.tag_configure("odd",  background=C["row_odd"])

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview,
                            style="Dark.Vertical.TScrollbar")
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return frame, tree

    def _insert_rows(self, tree, rows):
        """Insert rows into treeview."""
        tree.delete(*tree.get_children())
        for i, row in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            tree.insert("", "end", values=row, tags=(tag,))

    # ==========================
    # DASHBOARD HOME
    # ==========================
    def _go_dashboard(self):
        """Display dashboard home."""
        self._clear_content()
        self._page_header("Dashboard", "Overview")
        separator(self.content, C["card_border"]).pack(fill="x", padx=28, pady=(8, 16))

        # Stat cards
        stats_row = tk.Frame(self.content, bg=C["bg_dark"])
        stats_row.pack(fill="x", padx=28, pady=(0, 16))

        stats = [
            ("Students", self.db.count_students(), C["accent"],    "👨‍🎓"),
            ("Courses",  self.db.count_courses(),  C["success"],   "📚"),
            ("Grades",   self.db.count_grades(),   C["warning"],   "📝"),
        ]
        for label, value, color, icon in stats:
            c = tk.Frame(stats_row, bg=C["card_bg"],
                         highlightthickness=1,
                         highlightbackground=C["card_border"],
                         padx=20, pady=14)
            c.pack(side="left", expand=True, fill="x", padx=(0, 12))
            tk.Label(c, text=icon, font=("Segoe UI", 22), bg=C["card_bg"]).pack(anchor="w")
            tk.Label(c, text=str(value), font=("Segoe UI", 28, "bold"),
                     bg=C["card_bg"], fg=color).pack(anchor="w")
            tk.Label(c, text=label, font=("Segoe UI", 10),
                     bg=C["card_bg"], fg=C["text_secondary"]).pack(anchor="w")

        # Top students
        top_label_frame = tk.Frame(self.content, bg=C["bg_dark"])
        top_label_frame.pack(fill="x", padx=28, pady=(8, 4))
        styled_label(top_label_frame, "Top Performing Students",
                     size=12, weight="bold").pack(side="left")

        cols = ("Name", "Reg No", "Avg Marks")
        tf, tree = self._build_tree(self.content, cols,
                                    col_widths={"Name": 220, "Reg No": 140, "Avg Marks": 100},
                                    col_anchors={"Avg Marks": "center"})
        tf.pack(fill="x", padx=28, pady=(0, 12))
        top = self.db.get_top_students(8)
        self._insert_rows(tree, top)

    # ==========================
    # STUDENT MANAGEMENT
    # ==========================
    def _go_students(self):
        """Display student management page."""
        self._clear_content()
        hdr = self._page_header("Students", f"Total: {self.db.count_students()}")

        # Action bar
        actions = tk.Frame(self.content, bg=C["bg_dark"])
        actions.pack(fill="x", padx=28, pady=(10, 6))

        sb, _ = self._search_bar(actions, lambda q: self._load_students(q))
        sb.pack(side="left")
        styled_button(actions, " ＋ Add Student ", self._open_add_student,
                      font_size=10).pack(side="right")
        styled_button(actions, " ✏ Edit ", self._open_edit_student,
                      color="#334155", font_size=10).pack(side="right", padx=(0, 6))
        styled_button(actions, " 🗑 Delete ", self._delete_student,
                      color=C["danger"], hover_color="#B91C1C",
                      font_size=10).pack(side="right", padx=(0, 6))

        separator(self.content).pack(fill="x", padx=28, pady=(4, 6))

        cols = ("ID", "Name", "Reg No", "Email", "Program", "Semester")
        tf, self._student_tree = self._build_tree(
            self.content, cols,
            col_widths={"ID": 50, "Name": 200, "Reg No": 120,
                        "Email": 200, "Program": 140, "Semester": 80},
            col_anchors={"ID": "center", "Semester": "center"}
        )
        tf.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._load_students()

    def _load_students(self, search=""):
        """Load and display students."""
        rows = self.db.get_students(search)
        self._insert_rows(self._student_tree, rows)

    def _open_add_student(self):
        """Open add student dialog."""
        self._student_form("Add Student")

    def _open_edit_student(self):
        """Open edit student dialog."""
        sel = self._student_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a student to edit.")
            return
        vals = self._student_tree.item(sel[0])["values"]
        self._student_form("Edit Student", vals)

    def _student_form(self, title, data=None):
        """Display student form dialog."""
        win = self._popup(title, "560x540")
        fields = ["Full Name", "Registration No.", "Email Address",
                  "Phone Number", "Program / Department", "Semester (1-8)"]
        entries = {}
        col_frame = tk.Frame(win, bg=C["card_bg"])
        col_frame.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        for i, f in enumerate(fields):
            styled_label(col_frame, f.upper(), size=8,
                         color=C["text_secondary"]).pack(anchor="w", pady=(8, 0))
            e = styled_entry(col_frame, width=44)
            e.pack(fill="x", ipady=6, pady=(2, 0))
            entries[f] = e

        if data:
            # data: (id, name, regNo, email, program, semester)
            mapping = {
                "Full Name":            str(data[1]),
                "Registration No.":     str(data[2]),
                "Email Address":        str(data[3] or ""),
                "Phone Number":         str(data[4] or "") if len(data) > 4 else "",
                "Program / Department": str(data[4] or "") if len(data) > 4 else "",
                "Semester (1-8)":       str(data[5] or "1") if len(data) > 5 else "1",
            }
            for field, val in mapping.items():
                if field in entries:
                    entries[field].insert(0, val)

        def save():
            name    = entries["Full Name"].get().strip()
            reg     = entries["Registration No."].get().strip()
            email   = entries["Email Address"].get().strip()
            phone   = entries["Phone Number"].get().strip()
            program = entries["Program / Department"].get().strip()
            sem_str = entries["Semester (1-8)"].get().strip()

            if not name or not reg:
                messagebox.showwarning("Required", "Name and Registration No. are required.", parent=win)
                return
            
            if email and not validate_email(email):
                messagebox.showwarning("Invalid Email", "Please enter a valid email address.", parent=win)
                return
            
            if phone and not validate_phone(phone):
                messagebox.showwarning("Invalid Phone", "Please enter a valid phone number.", parent=win)
                return
            
            if not validate_semester(sem_str):
                max_sem = CONFIG.get("max_semester", 8)
                messagebox.showwarning("Invalid", f"Semester must be a number 1–{max_sem}.", parent=win)
                return
            
            sem = int(sem_str) if sem_str else 1
            try:
                if data:
                    self.db.update_student(data[0], name, reg, email, phone, program, sem)
                else:
                    self.db.add_student(name, reg, email, phone, program, sem)
                win.destroy()
                self._load_students()
                messagebox.showinfo("Success", "Student saved successfully!")
            except ValueError as ve:
                messagebox.showerror("Duplicate", str(ve), parent=win)
            except Exception as ex:
                messagebox.showerror("Error", f"Error saving student: {str(ex)}", parent=win)
                logger.error(f"Error in _student_form: {ex}")

        styled_button(win, "  Save Student  ", save,
                      font_size=11).pack(fill="x", padx=24, pady=16, ipady=8)

    def _delete_student(self):
        """Delete selected student."""
        sel = self._student_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a student to delete.")
            return
        vals = self._student_tree.item(sel[0])["values"]
        if messagebox.askyesno("Confirm Delete",
                               f"Delete student '{vals[1]}'?\nThis will also remove their grades.",
                               icon="warning"):
            try:
                self.db.delete_student(vals[0])
                self._load_students()
                messagebox.showinfo("Success", "Student deleted successfully!")
            except Exception as ex:
                messagebox.showerror("Error", f"Error deleting student: {str(ex)}")
                logger.error(f"Error in _delete_student: {ex}")

    # ==========================
    # COURSE MANAGEMENT
    # ==========================
    def _go_courses(self):
        """Display course management page."""
        self._clear_content()
        self._page_header("Courses", f"Total: {self.db.count_courses()}")

        actions = tk.Frame(self.content, bg=C["bg_dark"])
        actions.pack(fill="x", padx=28, pady=(10, 6))
        sb, _ = self._search_bar(actions, lambda q: self._load_courses(q))
        sb.pack(side="left")
        styled_button(actions, " ＋ Add Course ", self._open_add_course).pack(side="right")
        styled_button(actions, " ✏ Edit ", self._open_edit_course,
                      color="#334155").pack(side="right", padx=(0, 6))
        styled_button(actions, " 🗑 Delete ", self._delete_course,
                      color=C["danger"], hover_color="#B91C1C").pack(side="right", padx=(0, 6))

        separator(self.content).pack(fill="x", padx=28, pady=(4, 6))

        cols = ("ID", "Code", "Course Name", "Credits", "Teacher")
        tf, self._course_tree = self._build_tree(
            self.content, cols,
            col_widths={"ID": 50, "Code": 100, "Course Name": 240,
                        "Credits": 70, "Teacher": 180},
            col_anchors={"ID": "center", "Credits": "center"}
        )
        tf.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._load_courses()

    def _load_courses(self, search=""):
        """Load and display courses."""
        rows = self.db.get_courses(search)
        self._insert_rows(self._course_tree, rows)

    def _open_add_course(self):
        """Open add course dialog."""
        self._course_form("Add Course")

    def _open_edit_course(self):
        """Open edit course dialog."""
        sel = self._course_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a course to edit.")
            return
        vals = self._course_tree.item(sel[0])["values"]
        self._course_form("Edit Course", vals)

    def _course_form(self, title, data=None):
        """Display course form dialog."""
        win = self._popup(title, "520x480")
        fields = ["Course Code (e.g. CS-301)", "Course Name",
                  "Credit Hours (1-4)", "Teacher Name", "Description"]
        entries = {}
        col_frame = tk.Frame(win, bg=C["card_bg"])
        col_frame.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        for f in fields:
            styled_label(col_frame, f.upper(), size=8,
                         color=C["text_secondary"]).pack(anchor="w", pady=(8, 0))
            e = styled_entry(col_frame, width=44)
            e.pack(fill="x", ipady=6, pady=(2, 0))
            entries[f] = e

        if data:
            vals_map = {
                "Course Code (e.g. CS-301)": str(data[1]),
                "Course Name":               str(data[2]),
                "Credit Hours (1-4)":        str(data[3]),
                "Teacher Name":              str(data[4] or ""),
            }
            for field, val in vals_map.items():
                entries[field].insert(0, val)

        def save():
            code    = entries["Course Code (e.g. CS-301)"].get().strip()
            name    = entries["Course Name"].get().strip()
            credits = entries["Credit Hours (1-4)"].get().strip()
            teacher = entries["Teacher Name"].get().strip()
            desc    = entries["Description"].get().strip()

            if not code or not name:
                messagebox.showwarning("Required", "Course Code and Name are required.", parent=win)
                return
            
            try:
                cr = int(credits)
                if not 1 <= cr <= 4:
                    raise ValueError("Credits must be between 1 and 4")
            except ValueError:
                messagebox.showwarning("Invalid", "Credit hours must be 1–4.", parent=win)
                return
            
            try:
                if data:
                    self.db.update_course(data[0], code, name, cr, teacher, desc)
                else:
                    self.db.add_course(code, name, cr, teacher, desc)
                win.destroy()
                self._load_courses()
                messagebox.showinfo("Success", "Course saved successfully!")
            except ValueError as ve:
                messagebox.showerror("Duplicate", str(ve), parent=win)
            except Exception as ex:
                messagebox.showerror("Error", f"Error saving course: {str(ex)}", parent=win)
                logger.error(f"Error in _course_form: {ex}")

        styled_button(win, "  Save Course  ", save,
                      font_size=11).pack(fill="x", padx=24, pady=16, ipady=8)

    def _delete_course(self):
        """Delete selected course."""
        sel = self._course_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a course to delete.")
            return
        vals = self._course_tree.item(sel[0])["values"]
        if messagebox.askyesno("Confirm Delete",
                               f"Delete course '{vals[2]}'?\nThis will remove all associated grades.",
                               icon="warning"):
            try:
                self.db.delete_course(vals[0])
                self._load_courses()
                messagebox.showinfo("Success", "Course deleted successfully!")
            except Exception as ex:
                messagebox.showerror("Error", f"Error deleting course: {str(ex)}")
                logger.error(f"Error in _delete_course: {ex}")

    # ==========================
    # GRADE MANAGEMENT
    # ==========================
    def _go_grades(self):
        """Display grade management page."""
        self._clear_content()
        self._page_header("Grades", f"Total records: {self.db.count_grades()}")

        actions = tk.Frame(self.content, bg=C["bg_dark"])
        actions.pack(fill="x", padx=28, pady=(10, 6))
        sb, _ = self._search_bar(actions, lambda q: self._load_grades(q))
        sb.pack(side="left")
        styled_button(actions, " ＋ Enter / Update Grade ",
                      self._open_grade_form).pack(side="right")
        styled_button(actions, " 🗑 Delete ", self._delete_grade,
                      color=C["danger"], hover_color="#B91C1C").pack(side="right", padx=(0, 6))

        separator(self.content).pack(fill="x", padx=28, pady=(4, 6))

        cols = ("ID", "Student Name", "Reg No", "Course", "Marks", "Grade")
        tf, self._grade_tree = self._build_tree(
            self.content, cols,
            col_widths={"ID": 50, "Student Name": 180, "Reg No": 110,
                        "Course": 200, "Marks": 80, "Grade": 70},
            col_anchors={"ID": "center", "Marks": "center", "Grade": "center"}
        )
        tf.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._load_grades()

    def _load_grades(self, search=""):
        """Load and display grades."""
        rows = self.db.get_grades(search)
        self._insert_rows(self._grade_tree, rows)

    def _open_grade_form(self):
        """Open grade entry dialog."""
        win = self._popup("Enter / Update Grade", "460x380")
        col_frame = tk.Frame(win, bg=C["card_bg"])
        col_frame.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        students = self.db.get_student_names()
        courses  = self.db.get_course_names()

        if not students:
            messagebox.showinfo("No Students", "Please add students first.", parent=win)
            win.destroy()
            return
        if not courses:
            messagebox.showinfo("No Courses", "Please add courses first.", parent=win)
            win.destroy()
            return

        # Student dropdown
        styled_label(col_frame, "STUDENT", size=8,
                     color=C["text_secondary"]).pack(anchor="w", pady=(8, 0))
        student_var = tk.StringVar()
        student_map = {f"{s[1]} ({s[2]})": s[0] for s in students}
        s_combo = ttk.Combobox(col_frame, textvariable=student_var,
                               values=list(student_map.keys()), state="readonly", width=40,
                               style="Dark.TCombobox")
        s_combo.pack(fill="x", ipady=5, pady=(2, 0))
        s_combo.current(0)

        # Course dropdown
        styled_label(col_frame, "COURSE", size=8,
                     color=C["text_secondary"]).pack(anchor="w", pady=(12, 0))
        course_var = tk.StringVar()
        course_map = {f"{c[1]} ({c[2]})": c[0] for c in courses}
        c_combo = ttk.Combobox(col_frame, textvariable=course_var,
                               values=list(course_map.keys()), state="readonly", width=40,
                               style="Dark.TCombobox")
        c_combo.pack(fill="x", ipady=5, pady=(2, 0))
        c_combo.current(0)

        # Marks
        styled_label(col_frame, "MARKS (0–100)", size=8,
                     color=C["text_secondary"]).pack(anchor="w", pady=(12, 0))
        marks_e = styled_entry(col_frame, width=44)
        marks_e.pack(fill="x", ipady=6, pady=(2, 0))

        # Live grade preview
        preview = tk.Label(col_frame, text="Grade: —", font=("Segoe UI", 11, "bold"),
                           bg=C["card_bg"], fg=C["text_secondary"])
        preview.pack(anchor="w", pady=(8, 0))

        def update_preview(*_):
            try:
                m = float(marks_e.get())
                if 0 <= m <= 100:
                    letter, color = get_letter_grade(m)
                    preview.config(text=f"Grade: {letter}", fg=color)
                else:
                    preview.config(text="Grade: out of range", fg=C["danger"])
            except ValueError:
                preview.config(text="Grade: —", fg=C["text_secondary"])

        marks_e.bind("<KeyRelease>", update_preview)

        def save():
            student_display = student_var.get()
            course_display = course_var.get()
            
            # Validate selections
            sid = student_map.get(student_display)
            cid = course_map.get(course_display)
            
            if sid is None or cid is None:
                messagebox.showwarning("Invalid Selection", "Please select both a student and a course.", parent=win)
                return
            
            try:
                marks = float(marks_e.get())
                if not 0 <= marks <= 100:
                    raise ValueError("Marks must be between 0 and 100")
            except ValueError as ve:
                messagebox.showwarning("Invalid", "Marks must be a number between 0 and 100.", parent=win)
                return
            
            try:
                self.db.save_grade(sid, cid, marks)
                win.destroy()
                self._load_grades()
                messagebox.showinfo("Success", "Grade saved/updated successfully!")
            except Exception as ex:
                messagebox.showerror("Error", f"Error saving grade: {str(ex)}", parent=win)
                logger.error(f"Error in save_grade: {ex}")

        styled_button(win, "  Save Grade  ", save,
                      font_size=11).pack(fill="x", padx=24, pady=16, ipady=8)

    def _delete_grade(self):
        """Delete selected grade."""
        sel = self._grade_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a grade record to delete.")
            return
        vals = self._grade_tree.item(sel[0])["values"]
        if messagebox.askyesno("Confirm Delete",
                               f"Delete grade for '{vals[1]}' in '{vals[3]}'?",
                               icon="warning"):
            try:
                self.db.delete_grade(vals[0])
                self._load_grades()
                messagebox.showinfo("Success", "Grade deleted successfully!")
            except Exception as ex:
                messagebox.showerror("Error", f"Error deleting grade: {str(ex)}")
                logger.error(f"Error in _delete_grade: {ex}")

    # ==========================
    # REPORTS
    # ==========================
    def _go_reports(self):
        """Display reports page."""
        self._clear_content()
        self._page_header("Reports", "Academic Performance Overview")
        separator(self.content).pack(fill="x", padx=28, pady=(8, 6))

        tabs = ttk.Notebook(self.content)
        tabs.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # ---- Student Performance tab ----
        sp_frame = tk.Frame(tabs, bg=C["bg_dark"])
        tabs.add(sp_frame, text="  Student Performance  ")

        cols = ("Student Name", "Reg No", "Program", "Avg Marks", "CGPA", "Courses")
        tf, tree = self._build_tree(sp_frame, cols,
            col_widths={"Student Name": 180, "Reg No": 110, "Program": 140,
                        "Avg Marks": 90, "CGPA": 70, "Courses": 70},
            col_anchors={"Avg Marks": "center", "CGPA": "center", "Courses": "center"})
        tf.pack(fill="both", expand=True, pady=10)
        rows = self.db.get_report()
        self._insert_rows(tree, rows)

        # ---- Course Stats tab ----
        cs_frame = tk.Frame(tabs, bg=C["bg_dark"])
        tabs.add(cs_frame, text="  Course Statistics  ")

        cols2 = ("Course Name", "Enrolled", "Avg Marks", "Highest", "Lowest")
        tf2, tree2 = self._build_tree(cs_frame, cols2,
            col_widths={"Course Name": 240, "Enrolled": 80,
                        "Avg Marks": 90, "Highest": 80, "Lowest": 80},
            col_anchors={"Enrolled": "center", "Avg Marks": "center",
                         "Highest": "center", "Lowest": "center"})
        tf2.pack(fill="both", expand=True, pady=10)
        rows2 = self.db.get_course_stats()
        self._insert_rows(tree2, rows2)

    # ==========================
    # USER MANAGEMENT (Admin)
    # ==========================
    def _go_users(self):
        """Display user management page (Admin only)."""
        self._clear_content()
        self._page_header("User Accounts", "System access management")

        actions = tk.Frame(self.content, bg=C["bg_dark"])
        actions.pack(fill="x", padx=28, pady=(10, 6))
        styled_button(actions, " ＋ Add User ", self._open_add_user).pack(side="right")
        styled_button(actions, " 🗑 Delete ", self._delete_user,
                      color=C["danger"], hover_color="#B91C1C").pack(side="right", padx=(0, 6))

        separator(self.content).pack(fill="x", padx=28, pady=(4, 6))

        cols = ("ID", "Username", "Role")
        tf, self._user_tree = self._build_tree(
            self.content, cols,
            col_widths={"ID": 60, "Username": 200, "Role": 120},
            col_anchors={"ID": "center", "Role": "center"}
        )
        tf.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._load_users()

    def _load_users(self):
        """Load and display users."""
        self._insert_rows(self._user_tree, self.db.get_all_users())

    def _open_add_user(self):
        """Open add user dialog."""
        win = self._popup("Add User Account", "420x360")
        col_frame = tk.Frame(win, bg=C["card_bg"])
        col_frame.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        styled_label(col_frame, "USERNAME", size=8, color=C["text_secondary"]).pack(anchor="w", pady=(8, 0))
        e_user = styled_entry(col_frame, width=40)
        e_user.pack(fill="x", ipady=6, pady=(2, 0))

        styled_label(col_frame, "PASSWORD", size=8, color=C["text_secondary"]).pack(anchor="w", pady=(10, 0))
        e_pass = styled_entry(col_frame, width=40, show="●")
        e_pass.pack(fill="x", ipady=6, pady=(2, 0))

        styled_label(col_frame, "ROLE", size=8, color=C["text_secondary"]).pack(anchor="w", pady=(10, 0))
        role_var = tk.StringVar(value="Teacher")
        role_combo = ttk.Combobox(col_frame, textvariable=role_var,
                                  values=["Admin", "Teacher", "Student"],
                                  state="readonly", width=38, style="Dark.TCombobox")
        role_combo.pack(fill="x", ipady=5, pady=(2, 0))

        def save():
            u = e_user.get().strip()
            p = e_pass.get()
            r = role_var.get()
            if not u or not p:
                messagebox.showwarning("Required", "Username and password are required.", parent=win)
                return
            min_len = CONFIG.get("min_password_length", 6)
            if len(p) < min_len:
                messagebox.showwarning("Weak Password", f"Password must be at least {min_len} characters.", parent=win)
                return
            try:
                self.db.add_user(u, p, r)
                win.destroy()
                self._load_users()
                messagebox.showinfo("Success", "User created successfully!")
            except ValueError as ve:
                messagebox.showerror("Error", str(ve), parent=win)
            except Exception as ex:
                messagebox.showerror("Error", f"Error creating user: {str(ex)}", parent=win)
                logger.error(f"Error in _open_add_user: {ex}")

        styled_button(win, "  Create User  ", save,
                      font_size=11).pack(fill="x", padx=24, pady=16, ipady=8)

    def _delete_user(self):
        """Delete selected user."""
        sel = self._user_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a user to delete.")
            return
        vals = self._user_tree.item(sel[0])["values"]
        if vals[1] == "admin":
            messagebox.showerror("Protected", "The default admin account cannot be deleted.")
            return
        if messagebox.askyesno("Confirm Delete", f"Delete user '{vals[1]}'?", icon="warning"):
            try:
                self.db.delete_user(vals[0])
                self._load_users()
                messagebox.showinfo("Success", "User deleted successfully!")
            except Exception as ex:
                messagebox.showerror("Error", f"Error deleting user: {str(ex)}")
                logger.error(f"Error in _delete_user: {ex}")

    # ==========================
    # STUDENT ROLE VIEWS (read-only)
    # ==========================
    def _go_student_grades(self):
        """Student view: see all grade records (read-only)."""
        self._clear_content()
        self._page_header("My Grades", "Your academic record")
        separator(self.content).pack(fill="x", padx=28, pady=(8, 6))
        actions = tk.Frame(self.content, bg=C["bg_dark"])
        actions.pack(fill="x", padx=28, pady=(4, 6))
        sb, _ = self._search_bar(actions, lambda q: self._load_student_grades_view(q))
        sb.pack(side="left")
        cols = ("Student Name", "Reg No", "Course", "Marks", "Grade")
        tf, self._sgrade_tree = self._build_tree(
            self.content, cols,
            col_widths={"Student Name": 200, "Reg No": 120,
                        "Course": 220, "Marks": 80, "Grade": 70},
            col_anchors={"Marks": "center", "Grade": "center"})
        tf.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._load_student_grades_view()

    def _load_student_grades_view(self, search=""):
        """Load student grades for student view."""
        rows = self.db.get_grades(search)
        display = [r[1:] for r in rows]
        self._insert_rows(self._sgrade_tree, display)

    def _go_courses_readonly(self):
        """Read-only course list for Student/Teacher."""
        self._clear_content()
        self._page_header("Course List", "Available courses")
        separator(self.content).pack(fill="x", padx=28, pady=(8, 6))
        actions = tk.Frame(self.content, bg=C["bg_dark"])
        actions.pack(fill="x", padx=28, pady=(4, 6))
        sb, _ = self._search_bar(actions, lambda q: self._load_courses_ro(q))
        sb.pack(side="left")
        cols = ("Code", "Course Name", "Credits", "Teacher")
        tf, self._ro_course_tree = self._build_tree(
            self.content, cols,
            col_widths={"Code": 110, "Course Name": 260, "Credits": 80, "Teacher": 200},
            col_anchors={"Credits": "center"})
        tf.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._load_courses_ro()

    def _load_courses_ro(self, search=""):
        """Load courses for read-only view."""
        rows = self.db.get_courses(search)
        display = [(r[1], r[2], r[3], r[4] or "N/A") for r in rows]
        self._insert_rows(self._ro_course_tree, display)

    # ==========================
    # POPUP HELPER
    # ==========================
    def _popup(self, title, geometry="480x420"):
        """Create popup dialog window."""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(geometry)
        win.configure(bg=C["card_bg"])
        win.grab_set()
        win.resizable(False, False)
        # Title bar inside popup
        tk.Label(win, text=title, font=("Segoe UI", 13, "bold"),
                 bg=C["card_bg"], fg=C["text_primary"],
                 padx=24, pady=10).pack(fill="x", anchor="w")
        separator(win).pack(fill="x", padx=0)
        return win


# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = SGMSApp(root)
        root.mainloop()
    except Exception as e:
        logger.critical(f"Application crashed: {e}", exc_info=True)
        raise

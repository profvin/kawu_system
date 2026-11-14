import os
import sqlite3
import io
from datetime import datetime
from flask import Flask, request, jsonify, g, render_template, session, send_file
import qrcode
import openpyxl
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kawu_secret_key_2026')

# --- Render Persistent Disk Path Adjustment ---
DB_DIR = '/var/data' if os.path.exists('/var/data') else os.path.dirname(__file__)
DATABASE = os.path.join(DB_DIR, 'kawu.db')
QR_FOLDER = os.path.join(DB_DIR, 'static', 'qr_codes')

os.makedirs(QR_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Default Admin Password
ADMIN_PASSWORD = "kawu2026admin"

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON;")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS employers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reg_number TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                id_number TEXT UNIQUE NOT NULL,
                staff_number TEXT UNIQUE NOT NULL,
                gender TEXT CHECK(gender IN ('Male', 'Female', 'Other')) NOT NULL,
                employer_id INTEGER NOT NULL,
                reg_date DATE NOT NULL,
                status TEXT CHECK(status IN ('Active', 'Suspended', 'Exited')) DEFAULT 'Active',
                qr_code_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employer_id) REFERENCES employers (id)
            );
        """)
        db.commit()

        # Seed Official 9 KAWU Employer Categories
        employers_list = [
            'Kenya Airways',
            'Kenya Airports Authority (KAA)',
            'Jambojet',
            'Swissport Kenya',
            'KCAA (Kenya Civil Aviation Authority)',
            'Kenya Aerotek',
            'Tradewinds Aviation',
            'Eurocraft',
            'Bolloré Transport & Logistics'
        ]
        
        cursor = db.cursor()
        for emp in employers_list:
            cursor.execute("INSERT OR IGNORE INTO employers (name) VALUES (?)", (emp,))
        db.commit()

def generate_reg_number():
    db = get_db()
    current_year = datetime.now().year
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM members WHERE reg_number LIKE ?", (f'KAWU-{current_year}-%',))
    count = cursor.fetchone()[0] + 1
    return f"KAWU-{current_year}-{count:05d}"

def generate_qr_code(reg_number, full_name, id_number, staff_number):
    payload = f"KAWU:{reg_number}|ID:{id_number}|STAFF:{staff_number}|NAME:{full_name}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0a192f", back_color="white")
    
    file_name = f"{reg_number}.png"
    file_path = os.path.join(QR_FOLDER, file_name)
    img.save(file_path)
    return f"/static/qr_codes/{file_name}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    if data.get('password') == ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify({"status": "success", "message": "Admin authenticated successfully"})
    return jsonify({"error": "Invalid admin password"}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify({"status": "success", "message": "Logged out successfully"})

@app.route('/api/admin/reset-password', methods=['POST'])
def reset_admin_password():
    """Strictly require an active admin session to change the password"""
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized. You must be logged into the admin panel to change the password."}), 401

    data = request.get_json() or {}
    new_password = data.get('new_password', '').strip()
    
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters long."}), 400

    global ADMIN_PASSWORD
    ADMIN_PASSWORD = new_password
    return jsonify({"status": "success", "message": "Admin password updated successfully!"})

@app.route('/api/employers', methods=['GET', 'POST'])
def manage_employers():
    db = get_db()
    cursor = db.cursor()
    if request.method == 'GET':
        cursor.execute("SELECT id, name FROM employers ORDER BY name ASC")
        return jsonify({"status": "success", "employers": [dict(row) for row in cursor.fetchall()]})
    
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "Employer name is required"}), 400
    try:
        cursor.execute("INSERT INTO employers (name) VALUES (?)", (name,))
        db.commit()
        return jsonify({"status": "success", "message": f"Employer '{name}' added", "id": cursor.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Employer already exists"}), 409

@app.route('/api/admin/employers-list', methods=['GET'])
def admin_employers_list():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name FROM employers ORDER BY name ASC")
    return jsonify({"status": "success", "employers": [dict(row) for row in cursor.fetchall()]})

@app.route('/api/members/register', methods=['POST'])
def register_member():
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    id_number = data.get('id_number', '').strip()
    staff_number = data.get('staff_number', '').strip()
    gender = data.get('gender', '').strip()
    employer_id = data.get('employer_id')
    reg_date = data.get('reg_date') or datetime.now().strftime('%Y-%m-%d')

    if not all([full_name, id_number, staff_number, gender, employer_id]):
        return jsonify({"error": "All fields are required"}), 400

    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM members WHERE id_number = ? OR staff_number = ?", (id_number, staff_number))
    if cursor.fetchone():
        return jsonify({"error": "A member with this ID Number or Staff Number is already registered"}), 409

    reg_number = generate_reg_number()
    qr_path = generate_qr_code(reg_number, full_name, id_number, staff_number)

    cursor.execute("""
        INSERT INTO members (reg_number, full_name, id_number, staff_number, gender, employer_id, reg_date, qr_code_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (reg_number, full_name, id_number, staff_number, gender, employer_id, reg_date, qr_path))
    db.commit()

    return jsonify({
        "status": "success",
        "member": {
            "reg_number": reg_number,
            "full_name": full_name,
            "id_number": id_number,
            "staff_number": staff_number,
            "gender": gender,
            "reg_date": reg_date,
            "qr_code_url": qr_path,
            "status": "Active"
        }
    }), 201

@app.route('/api/members/query', methods=['GET'])
def query_member():
    search = request.args.get('search', '').strip()
    if not search:
        return jsonify({"error": "Search query required"}), 400
    
    clean_term = search.split('|')[0].replace("KAWU:", "").replace("ID:", "").replace("STAFF:", "").strip()
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT m.reg_number, m.full_name, m.id_number, m.staff_number, m.gender, m.reg_date, m.status, m.qr_code_path, e.name as employer
        FROM members m
        JOIN employers e ON m.employer_id = e.id
        WHERE m.reg_number = ? OR m.id_number = ? OR m.staff_number = ?
    """, (clean_term, clean_term, clean_term))
    
    member = cursor.fetchone()
    if not member:
        return jsonify({"found": False, "message": "Member record not found"}), 404
    return jsonify({"found": True, "member": dict(member)})

@app.route('/api/admin/members', methods=['GET'])
def admin_list_members():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT m.id, m.reg_number, m.full_name, m.id_number, m.staff_number, m.gender, m.reg_date, m.status, m.qr_code_path, e.name as employer
        FROM members m
        JOIN employers e ON m.employer_id = e.id
        ORDER BY m.created_at DESC
    """)
    return jsonify({"status": "success", "members": [dict(row) for row in cursor.fetchall()]})

@app.route('/api/admin/members/<int:member_id>/status', methods=['PUT'])
def update_member_status(member_id):
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ['Active', 'Suspended', 'Exited']:
        return jsonify({"error": "Invalid status value"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, full_name FROM members WHERE id = ?", (member_id,))
    member = cursor.fetchone()
    if not member:
        return jsonify({"error": "Member not found"}), 404
    cursor.execute("UPDATE members SET status = ? WHERE id = ?", (new_status, member_id))
    db.commit()
    return jsonify({"status": "success", "message": f"Member {member['full_name']} status updated to {new_status}"})

@app.route('/api/admin/export-excel', methods=['GET'])
def export_members_excel():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT m.reg_number, m.full_name, m.id_number, m.staff_number, m.gender, e.name as employer, m.reg_date, m.status
        FROM members m
        JOIN employers e ON m.employer_id = e.id
        ORDER BY m.created_at DESC
    """)
    members = cursor.fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "KAWU Members"

    headers = ['Registration Number', 'Full Name', 'ID Number', 'Staff Number', 'Gender', 'Employer Category', 'Registration Date', 'Status']
    ws.append(headers)

    for m in members:
        ws.append([m['reg_number'], m['full_name'], m['id_number'], m['staff_number'], m['gender'], m['employer'], m['reg_date'], m['status']])

    excel_io = io.BytesIO()
    wb.save(excel_io)
    excel_io.seek(0)

    filename = f"kawu_members_directory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(excel_io, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=filename)

@app.route('/api/admin/export-pdf', methods=['GET'])
def export_members_pdf():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT m.reg_number, m.full_name, m.id_number, m.staff_number, m.gender, e.name as employer, m.reg_date, m.status
        FROM members m
        JOIN employers e ON m.employer_id = e.id
        ORDER BY m.created_at DESC
    """)
    members = cursor.fetchall()

    pdf_io = io.BytesIO()
    doc = SimpleDocTemplate(pdf_io, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#0a192f'), fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=10, leading=14, alignment=1, textColor=colors.HexColor('#475569'), fontName='Helvetica')
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor('#1e293b'), fontName='Helvetica')
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.white, fontName='Helvetica-Bold')

    story.append(Paragraph("KENYA AVIATION WORKERS UNION (KAWU)", title_style))
    story.append(Paragraph(f"Registered Members Directory — Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))
    story.append(Spacer(1, 15))

    table_data = [[
        Paragraph('Reg No', header_style),
        Paragraph('Full Name', header_style),
        Paragraph('ID Number', header_style),
        Paragraph('Staff No', header_style),
        Paragraph('Gender', header_style),
        Paragraph('Employer', header_style),
        Paragraph('Reg Date', header_style),
        Paragraph('Status', header_style)
    ]]

    for m in members:
        table_data.append([
            Paragraph(m['reg_number'], cell_style),
            Paragraph(m['full_name'], cell_style),
            Paragraph(m['id_number'], cell_style),
            Paragraph(m['staff_number'], cell_style),
            Paragraph(m['gender'], cell_style),
            Paragraph(m['employer'], cell_style),
            Paragraph(m['reg_date'], cell_style),
            Paragraph(m['status'], cell_style)
        ])

    col_widths = [95, 130, 85, 75, 55, 130, 85, 65]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0a192f')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1'))
    ]))

    story.append(t)
    doc.build(story)
    pdf_io.seek(0)

    filename = f"kawu_members_directory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_io, mimetype="application/pdf", as_attachment=True, download_name=filename)

@app.route('/api/admin/backup', methods=['GET'])
def backup_database():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    if not os.path.exists(DATABASE):
        return jsonify({"error": "Database file not found"}), 404
    backup_filename = f"kawu_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    return send_file(DATABASE, as_attachment=True, download_name=backup_filename)

@app.route('/api/admin/restore', methods=['POST'])
def restore_database():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    file = request.files.get('database_file')
    if not file or not file.filename.endswith('.db'):
        return jsonify({"error": "A valid SQLite .db backup file is required"}), 400
    try:
        file.save(DATABASE)
        return jsonify({"status": "success", "message": "Database restored successfully! Please refresh."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    print("KAWU System running on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
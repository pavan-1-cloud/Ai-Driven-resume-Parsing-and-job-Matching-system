from flask import Flask, request, render_template, jsonify, send_file, redirect, flash, session, url_for
import mysql.connector
import os
import pdfplumber
import pandas as pd
from werkzeug.utils import secure_filename
import re
from pdfminer.pdfparser import PDFSyntaxError
import io
import logging
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from mysql.connector import Error
from flask import jsonify
# Suppress pdfplumber warnings
logging.getLogger('pdfminer').setLevel(logging.ERROR)

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}
MAX_UPLOADS = 15
app.secret_key = 'dev_key_12345'

# Make sure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="resume"
)
cursor = db.cursor()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check user in database
        try:
            cursor.execute("SELECT id, name, password FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

            if user:
                user_id, user_name, hashed_password = user

                if check_password_hash(hashed_password, password):
                    session['user_id'] = user_id
                    session['user_name'] = user_name
                    print("[DEBUG] Session set: user_id =", session['user_id'])
                    flash("Login successful!", "success")
                    return redirect('/client-uploads')  # Or wherever you want to go
                else:
                    flash("Invalid password.", "error")
            else:
                flash("Email not found.", "error")

        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")

        return redirect('/login')

    return render_template('login.html')

@app.route('/')
def home():
    return redirect('/login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        retype_password = request.form['retype_password']

        if password != retype_password:
            flash("Passwords do not match!", "error")
            return redirect('/signup')

        # You can also validate email and password here using regex

        hashed_password = generate_password_hash(password)

        try:
            cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                           (name, email, hashed_password))
            db.commit()
            flash("Signup successful!", "success")
            return redirect('/login')  # Assuming you have a login page
        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect('/signup')

    return render_template('signup.html')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            cursor.execute("SELECT id, name, password FROM users WHERE email = %s AND type = 'admin'", (email,))
            admin = cursor.fetchone()

            if admin:
                admin_id, admin_name, hashed_password = admin
                if check_password_hash(hashed_password, password):
                    session['admin_id'] = admin_id
                    session['admin_name'] = admin_name
                    # flash("Admin login successful!", "success")
                    return redirect('/index')  # You'll create this route later
                else:
                    flash("Invalid password.", "error")
            else:
                flash("Admin account not found.", "error")

        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")

        return redirect('/admin-login')

    return render_template('admin-login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect('/login')

@app.route('/admin-logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    flash("You have been logged out.", "success")
    return redirect('/admin-login')

@app.route('/sample')
def sample():
    return render_template('sample.html')




@app.route('/admin/users')
def admin_users():
    if 'admin_id' not in session:
        return redirect('/admin-login')

    try:
        cursor.execute("SELECT id, name, last_name, email, phone, type FROM users")
        users = cursor.fetchall()
        return render_template('admin_users.html', users=users)
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect('/index')

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if 'admin_id' not in session:
        return redirect('/admin-login')

    if request.method == 'POST':
        name = request.form['name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone = request.form['phone']
        user_type = request.form['type']

        try:
            cursor.execute("""
                UPDATE users
                SET name=%s, last_name=%s, email=%s, phone=%s, type=%s
                WHERE id=%s
            """, (name, last_name, email, phone, user_type, user_id))
            db.commit()
            flash("User updated successfully!", "success")
            return redirect('/admin/users')
        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")
            return redirect('/admin/users')

    # For GET method
    cursor.execute("SELECT id, name, last_name, email, phone, type FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        flash("User not found.", "error")
        return redirect('/admin/users')

    return render_template('edit_user.html', user=user)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'admin_id' not in session:
        return redirect('/admin-login')

    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()
        flash("User deleted successfully!", "success")
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")

    return redirect('/admin/users')



@app.route('/client-uploads', methods=['GET', 'POST'])
def client_uploads():
    if 'user_id' not in session:
        flash("Please log in to access this page.", "warning")
        return redirect('/login')

    user_id = session['user_id']
    print("[DEBUG] Session when accessing /client-uploads:", session)

    # Fetch current user data for pre-filling the form
    cursor.execute("SELECT name, last_name, email, phone, resume_file FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    user_name, user_last_name, user_email, user_phone, user_resume = user if user else ("", "", "", "", "")

    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone = request.form.get('phone')
        resume = request.files.get('resume')

        print("[DEBUG] Received form data:")
        print("First Name:", first_name)
        print("Last Name:", last_name)
        print("Email:", email)
        print("Phone:", phone)

        filename = user_resume  # default to current resume
        if resume and resume.filename != '':
            filename = secure_filename(resume.filename)
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            resume.save(resume_path)
            print("[DEBUG] Resume uploaded:", filename)
        else:
            print("[DEBUG] No new resume uploaded.")

        try:
            cursor.execute("""
                UPDATE users
                SET name = %s, last_name = %s, email = %s, phone = %s, resume_file = %s
                WHERE id = %s
            """, (first_name, last_name, email, phone, filename, user_id))
            db.commit()
            flash("Submission successful!", "success")
            print("[DEBUG] User record updated successfully.")
        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            print("[ERROR] Database error:", err)

        return redirect('/client-uploads')

    return render_template(
        'client-uploads.html',
        user_name=session.get('user_name'),
        user_first_name=user_name,
        user_last_name=user_last_name,
        user_email=user_email,
        user_phone=user_phone
    )

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Skill categorization
def categorize_skills(skills):
    categories = {
        'Programming': [
            'python', 'java', 'javascript', 'sql', 'c++', 'c#', 'go', 'ruby',
            'typescript', 'bash', 'perl', 'rust', 'kotlin', 'swift'
        ],
        'Web Development': [
            'html', 'css', 'react', 'node.js', 'angular', 'vue.js', 'bootstrap',
            'next.js', 'express.js', 'svelte', 'tailwind css'
        ],
        'Data Analysis': [
            'data analysis', 'machine learning', 'pandas', 'numpy', 'matplotlib',
            'seaborn', 'scikit-learn', 'deep learning', 'tensorflow', 'pytorch',
            'data visualization', 'statistics', 'power bi', 'tableau'
        ],
        'DevOps & Cloud': [
            'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'jenkins',
            'terraform', 'ansible', 'ci/cd', 'linux', 'cloud computing'
        ],
        'Databases': [
            'mysql', 'postgresql', 'mongodb', 'oracle', 'redis', 'sqlite',
            'nosql', 'elasticsearch'
        ],
        'Cybersecurity': [
            'network security', 'penetration testing', 'firewalls',
            'ethical hacking', 'encryption', 'incident response',
            'security auditing'
        ],
        'Mobile Development': [
            'android', 'ios', 'flutter', 'react native', 'swift', 'kotlin'
        ],
        'Project & Agile Tools': [
            'jira', 'confluence', 'scrum', 'kanban', 'agile methodology'
        ],
        'Soft Skills': [
            'communication', 'problem solving', 'teamwork', 'adaptability',
            'time management'
        ]
    }
    categorized = {cat: [s for s in skills if s in skills_list] for cat, skills_list in categories.items()}
    return {k: v for k, v in categorized.items() if v}

# Job recommendation based on skills
def recommend_jobs(skills):
    job_map = {
        'python': ['Python Developer', 'Data Scientist', 'Machine Learning Engineer'],
        'java': ['Java Developer', 'Backend Engineer', 'Android Developer'],
        'javascript': ['Frontend Developer', 'Full Stack Developer', 'Web Developer'],
        'sql': ['Database Administrator', 'Data Analyst', 'BI Developer'],
        'html': ['Web Developer', 'Frontend Developer'],
        'css': ['Web Developer', 'UI Developer'],
        'react': ['React Developer', 'Frontend Developer', 'Full Stack Developer'],
        'node.js': ['Backend Developer', 'Full Stack Developer'],
        'data analysis': ['Data Analyst', 'Business Analyst', 'BI Analyst'],
        'machine learning': ['Machine Learning Engineer', 'AI Engineer', 'Data Scientist'],
        'c++': ['Software Engineer', 'Game Developer', 'Embedded Systems Engineer'],
        'c#': ['.NET Developer', 'Software Engineer', 'Game Developer'],
        'typescript': ['Frontend Developer', 'Full Stack Developer'],
        'go': ['Go Developer', 'Backend Engineer'],
        'ruby': ['Ruby on Rails Developer', 'Web Developer'],
        'pandas': ['Data Analyst', 'Data Scientist'],
        'numpy': ['Data Scientist', 'Machine Learning Engineer'],
        'tensorflow': ['Machine Learning Engineer', 'AI Engineer'],
        'pytorch': ['AI Engineer', 'Deep Learning Engineer'],
        'aws': ['Cloud Engineer', 'DevOps Engineer', 'Solutions Architect'],
        'azure': ['Cloud Engineer', 'DevOps Engineer', 'Azure Administrator'],
        'gcp': ['Cloud Engineer', 'GCP Architect'],
        'docker': ['DevOps Engineer', 'Cloud Engineer', 'Site Reliability Engineer'],
        'kubernetes': ['DevOps Engineer', 'Cloud Engineer'],
        'linux': ['System Administrator', 'DevOps Engineer'],
        'git': ['Software Engineer', 'DevOps Engineer'],
        'flutter': ['Mobile Developer', 'Flutter Developer'],
        'swift': ['iOS Developer', 'Mobile Developer'],
        'kotlin': ['Android Developer', 'Mobile Developer'],
        'jira': ['Project Manager', 'Scrum Master'],
        'scrum': ['Scrum Master', 'Agile Coach'],
        'tableau': ['BI Developer', 'Data Analyst'],
        'power bi': ['BI Analyst', 'Data Analyst'],
        'mongodb': ['NoSQL Developer', 'Full Stack Developer'],
        'mysql': ['Database Administrator', 'Backend Developer'],
        'postgresql': ['Database Administrator', 'Data Engineer']
    }
    jobs = set()
    for skill in skills:
        if skill in job_map:
            jobs.update(job_map[skill])
    return list(jobs) if jobs else ['General Software Engineer']

# Career path suggestion
def suggest_career_path(jobs):
    if not jobs:
        return ['General Software Engineer (Entry-Level)', 'Mid-Level Software Engineer (2-5 Years)', 'Senior Software Engineer (5+ Years)']
    first_job = jobs[0].replace('Junior ', '').strip()
    return [
        f'Junior {first_job} (Entry-Level)',
        f'Mid-Level {first_job} (2-5 Years)',
        f'Senior {first_job} (5+ Years)'
    ]

@app.route('/get_resumes', methods=['GET'])
def get_resumes():
    if 'admin_id' not in session:
        return jsonify({'error': 'Unauthorized access.'}), 401

    try:
        print("[DEBUG] Fetching resumes from database...")
        cursor.execute("SELECT name, resume_file FROM users WHERE resume_file IS NOT NULL")
        resumes = cursor.fetchall()
        print("[DEBUG] Fetched resumes:", resumes)
        # Convert the result to a list of dictionaries
        resumes_list = [{'name': row[0], 'resume_file': row[1]} for row in resumes]
        print("[DEBUG] Formatted resumes list:", resumes_list)
        return jsonify({'resumes': resumes_list})
    except Error as e:
        print(f"[ERROR] Error fetching resumes: {str(e)}")
        return jsonify({'error': f'Error fetching resumes: {str(e)}'}), 500

@app.route('/index')
def index():
    if 'admin_id' not in session:
        flash("Please log in as admin to access the dashboard.", "warning")
        return redirect('/admin-login')

    admin_name = session.get('admin_name')
    return render_template('index.html', admin_name=admin_name)

@app.route('/upload', methods=['POST'])
def upload_files():
    # Check if admin is logged in
    if 'admin_id' not in session:
        print("[DEBUG] Unauthorized access to /upload - admin_id not in session")
        flash("Please log in as admin to access this feature.", "warning")
        return redirect('/admin-login')

    print("[DEBUG] Admin session verified for /upload, admin_id:", session['admin_id'])
    print("[DEBUG] Received /upload request")
    resume_files = request.form.getlist('resume_files')  # Database resume filenames
    uploaded_files = request.files.getlist('resumes')    # Newly uploaded files

    print("[DEBUG] Resume files from database:", resume_files)
    print("[DEBUG] Uploaded files:", [f.filename for f in uploaded_files if f])

    total_files = len(resume_files) + len(uploaded_files)
    print("[DEBUG] Total files to process:", total_files)
    if total_files == 0 or total_files > MAX_UPLOADS:
        print("[DEBUG] Invalid file count, returning 400")
        return jsonify({'error': f'Upload 1 to {MAX_UPLOADS} files.'}), 400

    data = []
    invalid_files = []

    # Process database resumes
    for filename in resume_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        print("[DEBUG] Processing database file:", filename, "Path:", file_path)
        if not os.path.exists(file_path):
            print("[DEBUG] File not found:", filename)
            invalid_files.append(filename)
            continue

        try:
            with pdfplumber.open(file_path) as pdf:
                text = ''
                for page in pdf.pages:
                    text += page.extract_text() or ''
                print("[DEBUG] Extracted text from", filename, ":", text[:100] + "..." if text else "No text")
                
                raw_skills = ['python', 'java', 'javascript', 'sql', 'html', 'css', 'react', 'node.js', 'data analysis', 'machine learning']
                found_skills = [skill for skill in raw_skills if re.search(r'\b' + re.escape(skill) + r'\b', text, re.IGNORECASE)]
                categorized_skills = categorize_skills(found_skills)
                skills_str = ', '.join(found_skills)
                jobs = recommend_jobs(found_skills)
                career_path = suggest_career_path(jobs)
                name = text.split('\n')[0].strip() if text else 'Unknown'

                data.append({
                    'name': name,
                    'filename': filename,
                    'skills': skills_str,
                    'categorized_skills': categorized_skills,
                    'jobs': ', '.join(jobs),
                    'career_path': career_path
                })
                print("[DEBUG] Processed data for", filename, ":", data[-1])
        except pdfplumber.PDFSyntaxError:
            print("[DEBUG] PDFSyntaxError for", filename)
            invalid_files.append(filename)
            continue
        except Exception as e:
            print(f"[ERROR] Unexpected error processing {filename}: {str(e)}")
            invalid_files.append(filename)
            continue

    # Process uploaded files
    for file in uploaded_files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            print("[DEBUG] Processing uploaded file:", filename, "Path:", file_path)
            try:
                file.save(file_path)
                with pdfplumber.open(file_path) as pdf:
                    text = ''
                    for page in pdf.pages:
                        text += page.extract_text() or ''
                    print("[DEBUG] Extracted text from", filename, ":", text[:100] + "..." if text else "No text")
                    
                    raw_skills = ['python', 'java', 'javascript', 'sql', 'html', 'css', 'react', 'node.js', 'data analysis', 'machine learning']
                    found_skills = [skill for skill in raw_skills if re.search(r'\b' + re.escape(skill) + r'\b', text, re.IGNORECASE)]
                    categorized_skills = categorize_skills(found_skills)
                    skills_str = ', '.join(found_skills)
                    jobs = recommend_jobs(found_skills)
                    career_path = suggest_career_path(jobs)
                    name = text.split('\n')[0].strip() if text else 'Unknown'

                    data.append({
                        'name': name,
                        'filename': filename,
                        'skills': skills_str,
                        'categorized_skills': categorized_skills,
                        'jobs': ', '.join(jobs),
                        'career_path': career_path
                    })
                    print("[DEBUG] Processed data for", filename, ":", data[-1])
            except pdfplumber.PDFSyntaxError:
                print("[DEBUG] PDFSyntaxError for", filename)
                invalid_files.append(filename)
                continue
            except Exception as e:
                print(f"[ERROR] Unexpected error processing uploaded file {filename}: {str(e)}")
                invalid_files.append(filename)
                continue

    if not data and invalid_files:
        print("[DEBUG] No valid data, all files invalid")
        return jsonify({'error': 'All uploaded files are invalid PDFs. Please upload valid text-based PDFs.'}), 400

    df = pd.DataFrame(data)
    print("[DEBUG] DataFrame created:", df.to_dict('records'))
    error_message = f'Invalid PDFs skipped: {", ".join(invalid_files)}' if invalid_files else None
    print("[DEBUG] Rendering results.html with error_message:", error_message)
    return render_template('results.html', table_data=df.to_dict('records'), error_message=error_message), 200



@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    try:
        # Get table data from form
        table_data = request.form['table_data']
        # Parse JSON string back to list of dicts
        import json
        table_data = json.loads(table_data)

        # Remove duplicates based on name
        unique_data = [dict(t) for t in {tuple(d.items()) for d in table_data}]

        # Create PDF
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        elements = []

        # Prepare table data with Paragraphs for wrapping
        styles = getSampleStyleSheet()
        styleN = styles['Normal']
        styleN.wordWrap = 'CJK'
        data = [[Paragraph('Name', styleN), Paragraph('Skills', styleN), Paragraph('Recommended Jobs', styleN)]]
        for row in unique_data:
            data.append([
                Paragraph(row['name'], styleN),
                Paragraph(row['skills'], styleN),
                Paragraph(row['jobs'], styleN)
            ])

        # Calculate dynamic column widths
        total_width = 7.5 * 72
        col_widths = [total_width * 0.3, total_width * 0.3, total_width * 0.4]
        from reportlab.pdfbase.pdfmetrics import stringWidth
        max_widths = [0, 0, 0]
        for row in data:
            for i, cell in enumerate(row):
                if isinstance(cell, Paragraph):
                    width = stringWidth(cell.text, styleN.fontName, styleN.fontSize)
                    max_widths[i] = max(max_widths[i], width)
        total_max = sum(max_widths)
        if total_max > 0:
            col_widths = [max(w / total_max * total_width, 50) for w in max_widths]

        # Create table with dynamic widths
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.green),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        elements.append(table)
        doc.build(elements)

        pdf_buffer.seek(0)
        return send_file(pdf_buffer, download_name='resumes.pdf', as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
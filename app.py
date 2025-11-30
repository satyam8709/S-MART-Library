import streamlit as st
import sqlite3
import pandas as pd
import os
import random
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART V6", page_icon="🏢", layout="wide")

if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v6.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. ADMINS
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    
    # 2. SEATS
    c.execute('''CREATE TABLE IF NOT EXISTS seats (
        seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available'
    )''')
    
    # 3. STUDENTS
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        email TEXT, father_name TEXT, guardian_phone TEXT, address TEXT,
        photo_path TEXT, govt_id_path TEXT,
        joining_date DATE, due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        mercy_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending'
    )''')
    
    # 4. EXTRAS
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount INTEGER, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')
    
    # 5. NEW: IN-APP NOTIFICATIONS (Targeted)
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        message TEXT,
        date DATE,
        is_read INTEGER DEFAULT 0
    )''')

    # Generate Seats
    c.execute('SELECT count(*) FROM seats')
    if c.fetchone()[0] == 0:
        seats = [(f"A-{i}", 1 if i%5==0 else 0, 'Available') for i in range(1, 101)]
        c.executemany('INSERT INTO seats (seat_label, has_locker, status) VALUES (?,?,?)', seats)
        
    conn.commit()
    conn.close()

if not os.path.exists(DB_NAME): init_db()

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def save_uploaded_file(uploaded_file, prefix):
    if uploaded_file is not None:
        file_path = f"student_documents/{prefix}_{uploaded_file.name}"
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_in_app_notification(student_id, message):
    conn = get_db()
    conn.execute("INSERT INTO notifications (student_id, message, date) VALUES (?,?,?)", (student_id, message, date.today()))
    conn.commit()
    conn.close()

def check_lockout(student_id):
    conn = get_db()
    try:
        df = pd.read_sql(f"SELECT * FROM students WHERE student_id={student_id}", conn)
        conn.close()
        if df.empty: return False, "Error"
        s = df.iloc[0]
        mercy = s['mercy_days'] if s['mercy_days'] else 0
        
        if s['status'] == 'Active':
            today = date.today()
            try: due = datetime.strptime(str(s['due_date']), '%Y-%m-%d').date()
            except: due = today
            limit = due + timedelta(days=5 + int(mercy))
            
            if today > limit:
                conn = get_db()
                conn.execute("UPDATE students SET status='Locked' WHERE student_id=?", (student_id,))
                conn.commit()
                return True, "⛔ ACCOUNT LOCKED"
            elif today > due:
                return False, f"⚠️ WARNING: Fees Overdue"
        elif s['status'] == 'Locked': return True, "⛔ ACCOUNT LOCKED"
        return False, "Welcome"
    except: return False, "System Error"

# ==========================================
# 3. REGISTRATION
# ==========================================
def show_registration_page():
    st.header("📝 S-MART Admission Form")
    if 'reg_verified' not in st.session_state: st.session_state['reg_verified'] = False
    
    if not st.session_state['reg_verified']:
        st.info("Step 1: Verify Mobile Number")
        phone_input = st.text_input("Enter Mobile Number (10 Digits)")
        if st.button("Send OTP"):
            if len(phone_input) == 10:
                otp = random.randint(1000, 9999)
                st.session_state['generated_otp'] = str(otp)
                st.session_state['reg_phone'] = phone_input
                st.success(f"OTP Sent! (Simulation Code: {otp})")
            else: st.error("Invalid Number")
        if 'generated_otp' in st.session_state:
            if st.button("Verify OTP"):
                # Simulation: Accepts any OTP in V6 for ease, or correct one
                st.session_state['reg_verified'] = True
                st.rerun()
    else:
        st.success(f"✅ Verified: {st.session_state['reg_phone']}")
        with st.form("kyc"):
            st.subheader("Details")
            c1, c2 = st.columns(2)
            name = c1.text_input("Name")
            father = c2.text_input("Father Name")
            c3, c4 = st.columns(2)
            exam = c3.selectbox("Exam", ["UPSC", "NEET", "Other"])
            pw = c4.text_input("Password", type="password")
            
            st.subheader("Uploads")
            c5, c6 = st.columns(2)
            photo = c5.file_uploader("Photo")
            gid = c6.file_uploader("ID Proof")
            
            if st.form_submit_button("Submit"):
                if photo and gid:
                    p_path = save_uploaded_file(photo, st.session_state['reg_phone'])
                    id_path = save_uploaded_file(gid, st.session_state['reg_phone'])
                    conn = get_db()
                    try:
                        conn.execute("""INSERT INTO students (name, phone, password, exam, father_name, photo_path, govt_id_path, joining_date, status) VALUES (?,?,?,?,?,?,?,?,?)""", 
                                     (name, st.session_state['reg_phone'], pw, exam, father, p_path, id_path, date.today(), 'Pending'))
                        conn.commit()
                        st.success("Registered!")
                    except: st.error("Phone used")
                    conn.close()

# ==========================================
# 4. ADMIN DASHBOARD
# ==========================================
def show_admin_dashboard():
    st.sidebar.header("👮 Admin")
    tab1, tab2, tab3 = st.tabs(["👥 Directory", "🗺️ Map", "🚦 Approvals"])
    
    conn = get_db()
    
    # --- TAB 1: DIRECTORY & REMINDERS ---
    with tab1:
        st.subheader("Student Operations")
        students = pd.read_sql("SELECT student_id, name, phone FROM students WHERE status != 'Pending'", conn)
        
        if not students.empty:
            choice = st.selectbox("Search Student", [f"{r['name']} ({r['phone']})" for _, r in students.iterrows()])
            phone = choice.split('(')[1].replace(')', '')
            profile = pd.read_sql(f"SELECT * FROM students WHERE phone='{phone}'", conn).iloc[0]
            
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if profile['photo_path']: st.image(profile['photo_path'], width=150)
            with c2:
                st.write(f"**Name:** {profile['name']}")
                st.write(f"**Father:** {profile['father_name']}")
                st.write(f"**Joined:** {profile['joining_date']}")
                st.write(f"**Valid Till:** {profile['due_date']}")
            with c3:
                st.write("#### 🔔 Actions")
                # DUAL CHANNEL REMINDERS
                if st.button("📲 In-App Reminder"):
                    send_in_app_notification(profile['student_id'], "🔔 Reminder: Your fees are due. Please pay to avoid lockout.")
                    st.success("Sent to App!")
                
                msg = f"Dear {profile['name']}, Fees Due."
                st.link_button("🟢 WhatsApp Reminder", f"https://wa.me/91{profile['phone']}?text={msg}")
    
    # --- TAB 2: MAP ---
    with tab2:
        st.subheader("Live Map")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    btn = "primary" if s['status'] != 'Available' else "secondary"
                    cols[i].button(s['seat_label'], type=btn)

    # --- TAB 3: APPROVALS ---
    with tab3:
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            c1, c2 = st.columns([3,1])
            c1.write(f"New: **{p['name']}**")
            if c2.button("Approve", key=p['student_id']):
                # Set Due Date 30 days from now
                due = date.today() + timedelta(days=30)
                conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", (due, p['student_id']))
                conn.commit()
                st.rerun()
    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD (UPDATED)
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked:
        st.error(msg)
        st.stop()

    st.title(f"🎓 Dashboard")
    
    # --- NEW: IN-APP NOTIFICATIONS ---
    conn = get_db()
    notifs = pd.read_sql(f"SELECT * FROM notifications WHERE student_id={user[0]} ORDER BY id DESC LIMIT 3", conn)
    conn.close()
    
    if not notifs.empty:
        st.warning(f"🔔 You have {len(notifs)} new message(s):")
        for _, n in notifs.iterrows():
            st.info(f"📅 {n['date']}: {n['message']}")

    c1, c2 = st.columns([1, 2])
    with c1:
        if user[9]: st.image(user[9], width=150)
        st.write(f"**Name:** {user[1]}")
        st.write(f"**Seat:** A-{user[15]}")
        
    with c2:
        # --- NEW: MEMBERSHIP DATES ---
        st.markdown(f"""
        <div style="background-color:#e8f4f8;padding:15px;border-radius:10px;">
            <h3>📅 Membership Status</h3>
            <p><b>Joined On:</b> {user[11]}</p>
            <p><b>Valid Till:</b> <span style="color:red;font-weight:bold">{user[12]}</span></p>
            <p><b>Status:</b> Active</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.link_button("💬 Chat with Admin", f"https://wa.me/919999999999?text=Hi Admin")

# ==========================================
# 6. ROUTER
# ==========================================
def main():
    if 'user' not in st.session_state: st.session_state['user'] = None
    
    if st.session_state['user']:
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()
        if st.session_state['role'] == 'Super': show_admin_dashboard()
        else: show_student_dashboard(st.session_state['user'])
    else:
        menu = st.sidebar.radio("Menu", ["🏠 Home", "📝 Join", "🔐 Login"])
        if menu == "🏠 Home": st.title("S-MART Library")
        elif menu == "📝 Join": show_registration_page()
        elif menu == "🔐 Login":
            st.header("Login")
            role = st.selectbox("Role", ["Student", "Admin"])
            u = st.text_input("User/Phone")
            p = st.text_input("Password", type="password")
            if st.button("Enter"):
                conn = get_db()
                if role == 'Admin':
                    user = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (u,p)).fetchone()
                    if user:
                        st.session_state['user'] = user
                        st.session_state['role'] = 'Super'
                        st.rerun()
                    else: st.error("Bad Admin Pass")
                else:
                    user = conn.execute("SELECT * FROM students WHERE phone=? AND password=?", (u,p)).fetchone()
                    if user:
                        if user[13] == 0: st.warning("Pending Approval")
                        else:
                            st.session_state['user'] = user
                            st.session_state['role'] = 'Student'
                            st.rerun()
                    else: st.error("User not found")
                conn.close()

if __name__ == "__main__":
    main()

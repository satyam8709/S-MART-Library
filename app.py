import streamlit as st
import sqlite3
import pandas as pd
import os
import random
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART OMNI V7", page_icon="🏢", layout="wide")

if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v7.db'

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
    
    # 3. STUDENTS (Full KYC Profile)
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
    
    # 4. OPERATIONS
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount INTEGER, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')
    
    # 5. NOTIFICATIONS (The V6 Feature)
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        message TEXT,
        date DATE,
        is_read INTEGER DEFAULT 0
    )''')

    # Generate 100 Seats
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
# 3. REGISTRATION (FULL KYC)
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
                st.session_state['reg_verified'] = True
                st.rerun()
    else:
        st.success(f"✅ Verified: {st.session_state['reg_phone']}")
        with st.form("kyc"):
            st.subheader("Personal Details")
            c1, c2 = st.columns(2)
            name = c1.text_input("Full Name")
            father = c2.text_input("Father Name")
            
            c3, c4 = st.columns(2)
            g_phone = c3.text_input("Guardian Phone")
            email = c4.text_input("Email")
            
            address = st.text_area("Permanent Address")
            exam = st.selectbox("Exam", ["UPSC", "BPSC", "JEE", "NEET", "Other"])
            pw = st.text_input("Create Password", type="password")
            
            st.subheader("Upload Documents")
            c5, c6 = st.columns(2)
            photo = c5.file_uploader("Photo")
            gid = c6.file_uploader("Govt ID")
            
            if st.form_submit_button("Submit Application"):
                if photo and gid:
                    p_path = save_uploaded_file(photo, st.session_state['reg_phone'])
                    id_path = save_uploaded_file(gid, st.session_state['reg_phone'])
                    conn = get_db()
                    try:
                        conn.execute("""INSERT INTO students (name, phone, password, exam, email, father_name, guardian_phone, address, photo_path, govt_id_path, joining_date, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                     (name, st.session_state['reg_phone'], pw, exam, email, father, g_phone, address, p_path, id_path, date.today(), 'Pending'))
                        conn.commit()
                        st.balloons()
                        st.success("Registered! Wait for Admin Approval.")
                    except: st.error("Phone already registered.")
                    conn.close()
                else: st.warning("Please upload Photo and ID")

# ==========================================
# 4. ADMIN DASHBOARD (RESTORED COMMANDER MODE)
# ==========================================
def show_admin_dashboard():
    # SIDEBAR X-RAY LOGIC (RESTORED)
    if 'selected_student_id' not in st.session_state: st.session_state['selected_student_id'] = None

    st.sidebar.markdown("---")
    st.sidebar.header("👮 Admin Panel")
    
    if st.session_state['selected_student_id']:
        conn = get_db()
        stu = pd.read_sql(f"SELECT * FROM students WHERE student_id={st.session_state['selected_student_id']}", conn).iloc[0]
        conn.close()
        with st.sidebar:
            st.info("👤 Student Profile")
            if stu['photo_path']: st.image(stu['photo_path'], width=150)
            st.write(f"**Name:** {stu['name']}")
            st.write(f"**Father:** {stu['father_name']}")
            st.write(f"**Guardian:** {stu['guardian_phone']}")
            st.write(f"**Address:** {stu['address']}")
            
            st.divider()
            if stu['govt_id_path']:
                with open(stu['govt_id_path'], "rb") as f:
                    st.download_button("Download ID", f, file_name="id_proof.png")
            
            if st.button("Close Details"):
                st.session_state['selected_student_id'] = None
                st.rerun()

    # TABS
    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ X-Ray Map", "👥 Directory", "🚦 Approvals", "⚙️ Ops"])
    
    conn = get_db()
    
    # --- TAB 1: MAP WITH CLICKABLE SEATS ---
    with tab1:
        st.subheader("Live Floor Plan (Click Seat to view Sidebar Details)")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        active_s = pd.read_sql("SELECT assigned_seat_id, student_id FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        s_map = {row['assigned_seat_id']: row['student_id'] for _, row in active_s.iterrows()}
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    sid = s['seat_id']
                    btn_type = "primary" if s['status'] != 'Available' else "secondary"
                    
                    if cols[i].button(s['seat_label'], key=f"map_{sid}", type=btn_type):
                        if sid in s_map:
                            st.session_state['selected_student_id'] = s_map[sid]
                            st.rerun()
                        else: st.toast("Seat Empty")

    # --- TAB 2: DIRECTORY & ACTIONS ---
    with tab2:
        st.subheader("Master Directory")
        students = pd.read_sql("SELECT student_id, name, phone FROM students WHERE status != 'Pending'", conn)
        if not students.empty:
            choice = st.selectbox("Search", [f"{r['name']} ({r['phone']})" for _, r in students.iterrows()])
            phone = choice.split('(')[1].replace(')', '')
            p = pd.read_sql(f"SELECT * FROM students WHERE phone='{phone}'", conn).iloc[0]
            
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if p['photo_path']: st.image(p['photo_path'], width=120)
            with c2:
                st.write(f"**{p['name']}**")
                st.write(f"**Valid Till:** {p['due_date']}")
                st.write(f"**Guardian:** {p['guardian_phone']}")
            with c3:
                if st.button("🔔 App Notify"):
                    send_in_app_notification(p['student_id'], "Fees Due. Pay immediately.")
                    st.success("Sent")
                
                msg = f"Dear {p['name']}, Fees Due."
                st.link_button("🟢 WhatsApp", f"https://wa.me/91{p['phone']}?text={msg}")
                
                if p['guardian_phone']:
                    g_msg = f"Dear Parent, Fees for {p['name']} is due."
                    st.link_button("👨 Parent Chat", f"https://wa.me/91{p['guardian_phone']}?text={g_msg}")

    # --- TAB 3: APPROVALS ---
    with tab3:
        st.subheader("Pending Approvals")
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, r in pending.iterrows():
            with st.expander(f"{r['name']} ({r['phone']})"):
                c1, c2 = st.columns(2)
                c1.write(f"**Father:** {r['father_name']}")
                c1.write(f"**Address:** {r['address']}")
                if r['photo_path']: c2.image(r['photo_path'], width=100)
                
                if st.button("✅ Approve Profile", key=f"ap_{r['student_id']}"):
                    due = date.today() + timedelta(days=30)
                    conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", (due, r['student_id']))
                    conn.commit()
                    st.rerun()
        
        st.divider()
        st.subheader("Assign Seats (Gate 2)")
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        for _, s in seatless.iterrows():
            c1, c2 = st.columns(2)
            c1.write(f"Assign for: **{s['name']}**")
            avail = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            sel = c2.selectbox("Seat", avail['seat_label'], key=f"ss_{s['student_id']}")
            if c2.button("Confirm", key=f"cf_{s['student_id']}"):
                sid = conn.execute(f"SELECT seat_id FROM seats WHERE seat_label='{sel}'").fetchone()[0]
                conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (sid,))
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (sid, s['student_id']))
                conn.commit()
                st.rerun()

    # --- TAB 4: OPS ---
    with tab4:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Expenses")
            with st.form("exp"):
                cat = st.selectbox("Cat", ["Rent", "Elec", "Staff"])
                amt = st.number_input("Amt")
                if st.form_submit_button("Add"):
                    conn.execute("INSERT INTO expenses (category, amount, date) VALUES (?,?,?)", (cat, amt, date.today()))
                    conn.commit()
                    st.success("Added")
        with c2:
            st.subheader("Notice Board")
            msg = st.text_input("Message")
            if st.button("Post"):
                conn.execute("INSERT INTO notices (message, type) VALUES (?,?)", (msg, 'General'))
                conn.commit()
                st.success("Posted")

    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD (WITH NOTIFICATIONS)
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked:
        st.error(msg)
        st.stop()

    st.title("🎓 Dashboard")
    
    # NOTIFICATIONS
    conn = get_db()
    notifs = pd.read_sql(f"SELECT * FROM notifications WHERE student_id={user[0]} ORDER BY id DESC LIMIT 3", conn)
    conn.close()
    if not notifs.empty:
        for _, n in notifs.iterrows():
            st.info(f"🔔 {n['date']}: {n['message']}")

    c1, c2 = st.columns([1, 2])
    with c1:
        if user[9]: st.image(user[9], width=150)
        st.write(f"**Name:** {user[1]}")
        st.write(f"**Seat:** A-{user[15]}")
    with c2:
        st.markdown(f"""
        <div style="background-color:#e8f4f8;padding:15px;border-radius:10px;">
            <h3>📅 Membership</h3>
            <p><b>Joined:</b> {user[11]}</p>
            <p><b>Valid Till:</b> {user[12]}</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    st.link_button("💬 Chat Admin", "https://wa.me/919999999999")

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

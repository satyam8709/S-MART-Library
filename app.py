import streamlit as st
import sqlite3
import pandas as pd
import os
import random
import time
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART V9", page_icon="🏢", layout="wide")

if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v9.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # CORE TABLES
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    
    c.execute('''CREATE TABLE IF NOT EXISTS seats (
        seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available'
    )''')
    
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
    
    # OPERATIONS
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount INTEGER, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, message TEXT, date DATE, is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS complaints (ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, category TEXT, message TEXT, status TEXT DEFAULT 'Open', date DATE)''')

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
            elif today > due: return False, f"⚠️ WARNING: Fees Overdue"
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
    if 'selected_student_id' not in st.session_state: st.session_state['selected_student_id'] = None
    st.sidebar.header("👮 Admin")
    
    if st.session_state['selected_student_id']:
        conn = get_db()
        stu = pd.read_sql(f"SELECT * FROM students WHERE student_id={st.session_state['selected_student_id']}", conn).iloc[0]
        conn.close()
        with st.sidebar:
            st.info("👤 Profile")
            if stu['photo_path']: st.image(stu['photo_path'], width=150)
            st.write(f"**Name:** {stu['name']}")
            st.write(f"**Father:** {stu['father_name']}")
            st.divider()
            if st.button("Close"):
                st.session_state['selected_student_id'] = None
                st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Map", "🛎️ Requests", "🚦 Approvals", "⚙️ Ops"])
    conn = get_db()
    
    with tab1: # MAP
        st.subheader("Floor Plan")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        active_s = pd.read_sql("SELECT assigned_seat_id, student_id FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        s_map = {row['assigned_seat_id']: row['student_id'] for _, row in active_s.iterrows()}
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    btn = "primary" if s['status'] != 'Available' else "secondary"
                    if cols[i].button(s['seat_label'], key=f"m_{s['seat_id']}", type=btn):
                        if s['seat_id'] in s_map:
                            st.session_state['selected_student_id'] = s_map[s['seat_id']]
                            st.rerun()

    with tab2: # REQUESTS
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Seat Moves")
            moves = pd.read_sql("SELECT * FROM seat_requests WHERE status='Pending'", conn)
            if moves.empty: st.info("No requests.")
            for _, m in moves.iterrows():
                st.warning(f"Student {m['student_id']} wants {m['requested_seat']}")
                if st.button("Approve", key=f"mv_{m['req_id']}"):
                    conn.execute("UPDATE seat_requests SET status='Approved' WHERE req_id=?", (m['req_id'],))
                    conn.commit()
                    st.rerun()
        with c2:
            st.subheader("Complaints")
            comps = pd.read_sql("SELECT * FROM complaints WHERE status='Open'", conn)
            if comps.empty: st.info("No active complaints.")
            for _, c in comps.iterrows():
                st.error(f"[{c['category']}] {c['message']}")
                if st.button("Resolve", key=f"cmp_{c['ticket_id']}"):
                    conn.execute("UPDATE complaints SET status='Resolved' WHERE ticket_id=?", (c['ticket_id'],))
                    conn.commit()
                    st.rerun()

    with tab3: # APPROVALS
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            c1, c2 = st.columns([3,1])
            c1.write(f"New: **{p['name']}**")
            if c2.button("Approve", key=p['student_id']):
                due = date.today() + timedelta(days=30)
                conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", (due, p['student_id']))
                conn.commit()
                st.rerun()
        st.divider()
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        for _, s in seatless.iterrows():
            c1, c2 = st.columns(2)
            c1.write(f"Assign: **{s['name']}**")
            avail = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            sel = c2.selectbox("Seat", avail['seat_label'], key=f"ss_{s['student_id']}")
            if c2.button("Confirm", key=f"cf_{s['student_id']}"):
                sid = conn.execute(f"SELECT seat_id FROM seats WHERE seat_label='{sel}'").fetchone()[0]
                conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (sid,))
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (sid, s['student_id']))
                conn.commit()
                st.rerun()

    with tab4: # OPS
        c1, c2 = st.columns(2)
        with c1:
            with st.form("exp"):
                cat = st.selectbox("Expense", ["Rent", "Elec"])
                amt = st.number_input("Amt")
                if st.form_submit_button("Add"):
                    conn.execute("INSERT INTO expenses (category, amount, date) VALUES (?,?,?)", (cat, amt, date.today()))
                    conn.commit()
                    st.success("Added")
        with c2:
            st.subheader("Post Notice")
            msg = st.text_input("Message")
            if st.button("Post"):
                conn.execute("INSERT INTO notices (message, type, date) VALUES (?,?,?)", (msg, 'General', date.today()))
                conn.commit()
                st.success("Posted")
    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD (V9 NOTICE CENTER)
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked:
        st.error(msg)
        st.stop()
    
    st.title(f"👋 Welcome, {user[1]}")

    # --- 📌 CENTRAL NOTICE BOARD (NEW) ---
    conn = get_db()
    latest_notice = pd.read_sql("SELECT * FROM notices ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    
    if not latest_notice.empty:
        n = latest_notice.iloc[0]
        # Styled Notice Box in the Center
        st.markdown(f"""
        <div style="
            background-color: #fff3cd;
            color: #856404;
            padding: 20px;
            border: 2px solid #ffeeba;
            border-radius: 12px;
            text-align: center;
            margin-bottom: 25px;
            box-shadow: 0px 4px 6px rgba(0,0,0,0.1);
        ">
            <h2 style='margin-top:0;'>📌 NOTICE BOARD</h2>
            <p style='font-size:18px; font-weight:bold;'>{n['message']}</p>
            <p style='font-size:12px; opacity:0.8;'>Posted on: {n['date']}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align:center; padding: 20px; color: grey; border: 1px dashed grey; border-radius: 10px; margin-bottom: 20px;">
            No new notices today.
        </div>
        """, unsafe_allow_html=True)

    # TABS
    tab1, tab2, tab3 = st.tabs(["🏠 My Hub", "🛎️ Concierge", "🧘 Zen Zone"])
    
    with tab1: # MY HUB
        c1, c2 = st.columns([1, 2])
        with c1:
            if user[9]: st.image(user[9], width=180)
            st.write(f"**Seat:** A-{user[15]}")
        with c2:
            # ID CARD (Black Text)
            st.markdown(f"""
            <div style="background-color:#e8f4f8;padding:20px;border-radius:15px;color:black;border-left:8px solid #FFD700;">
                <h3 style='margin:0'>🆔 S-MART ELITE</h3>
                <p><b>Name:</b> {user[1]}</p>
                <p><b>Exam:</b> {user[4]}</p>
                <p><b>Valid Till:</b> {user[12]}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # PERSONAL NOTIFICATIONS
            conn = get_db()
            notifs = pd.read_sql(f"SELECT * FROM notifications WHERE student_id={user[0]} ORDER BY id DESC LIMIT 3", conn)
            conn.close()
            if not notifs.empty:
                st.write("#### 🔔 Alerts")
                for _, n in notifs.iterrows():
                    st.info(f"{n['message']}")

    with tab2: # CONCIERGE
        st.subheader("🛎️ Services")
        with st.expander("📢 Lodge Complaint"):
            with st.form("comp"):
                cat = st.selectbox("Category", ["AC", "Cleanliness", "Noise", "WiFi"])
                msg = st.text_area("Details")
                if st.form_submit_button("Submit"):
                    conn = get_db()
                    conn.execute("INSERT INTO complaints (student_id, category, message, status, date) VALUES (?,?,?,?,?)",
                                 (user[0], cat, msg, 'Open', date.today()))
                    conn.commit()
                    st.success("Ticket Created")
        
        with st.expander("💺 Request Seat Change"):
            with st.form("mv"):
                new_s = st.text_input("New Seat")
                res = st.selectbox("Reason", ["AC", "Lighting", "Noise"])
                if st.form_submit_button("Request"):
                    conn = get_db()
                    conn.execute("INSERT INTO seat_requests (student_id, current_seat, requested_seat, reason, status) VALUES (?,?,?,?,?)",
                                 (user[0], f"A-{user[15]}", new_s, res, 'Pending'))
                    conn.commit()
                    st.success("Requested")

    with tab3: # ZEN ZONE
        st.subheader("🧘 Focus Tools")
        c1, c2 = st.columns(2)
        with c1: st.link_button("🎵 Lo-Fi Beats", "https://www.youtube.com/watch?v=jfKfPfyJRdk")
        with c2: st.link_button("🌧️ Rain Sounds", "https://www.youtube.com/watch?v=mPZkdNFkNps")
            
    st.divider()
    st.link_button("💬 Chat with Admin", "https://wa.me/919999999999")

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
        if menu == "🏠 Home": st.title("S-MART Library"); st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
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

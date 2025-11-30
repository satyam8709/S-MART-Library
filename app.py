import streamlit as st
import sqlite3
import pandas as pd
import os
import random
import time
import altair as alt
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION & CSS MAGIC
# ==========================================
st.set_page_config(page_title="S-MART INFINITY V16", page_icon="🏫", layout="wide")

# Custom CSS for "World Class" Look
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px; border-left: 5px solid #4CAF50;}
    .id-card {background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);}
    .notice-board {background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 10px; border: 1px solid #ffeeba;}
    .stButton>button {width: 100%; border-radius: 8px;}
</style>
""", unsafe_allow_html=True)

if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v16.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. CORE
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    c.execute('''CREATE TABLE IF NOT EXISTS seats (seat_id INTEGER PRIMARY KEY AUTOINCREMENT, seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available')''')
    
    # 2. STUDENTS (Added Gamification Columns)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        email TEXT, father_name TEXT, guardian_phone TEXT, address TEXT,
        photo_path TEXT, govt_id_path TEXT,
        joining_date DATE, due_date DATE,
        is_profile_approved INTEGER DEFAULT 0, is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER, mercy_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending',
        xp_points INTEGER DEFAULT 0,
        badges TEXT DEFAULT 'Newbie'
    )''')
    
    # 3. OPS & FINANCE
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount INTEGER, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS income (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, amount INTEGER, date DATE, remarks TEXT, transaction_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, message TEXT, date DATE, is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS complaints (ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, category TEXT, priority TEXT, message TEXT, status TEXT DEFAULT 'Open', date DATE)''')
    
    # 4. PRODUCTIVITY & GAMIFICATION
    c.execute('''CREATE TABLE IF NOT EXISTS study_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, date DATE, start_time TIMESTAMP, end_time TIMESTAMP, duration_minutes INTEGER, session_type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, task TEXT, is_done INTEGER DEFAULT 0, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS student_targets (student_id INTEGER PRIMARY KEY, daily_target_hours INTEGER DEFAULT 6)''')
    
    # 5. NEW: INVENTORY & GUESTS (V16)
    c.execute('''CREATE TABLE IF NOT EXISTS books (book_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, subject TEXT, author TEXT, status TEXT DEFAULT 'Available')''')
    c.execute('''CREATE TABLE IF NOT EXISTS guests (guest_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, date DATE, amount_paid INTEGER)''')

    # Seed Seats
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
        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_in_app_notification(student_id, message):
    conn = get_db()
    conn.execute("INSERT INTO notifications (student_id, message, date) VALUES (?,?,?)", (student_id, message, date.today()))
    conn.commit(); conn.close()

def check_lockout(student_id):
    conn = get_db()
    try:
        s = pd.read_sql(f"SELECT * FROM students WHERE student_id={student_id}", conn).iloc[0]
        if s['status'] == 'Active':
            today = date.today()
            try: due = datetime.strptime(str(s['due_date']), '%Y-%m-%d').date()
            except: due = today
            limit = due + timedelta(days=5 + int(s['mercy_days'] or 0))
            if today > limit: return True, "⛔ ACCOUNT SUSPENDED: Dues Pending"
        elif s['status'] == 'Locked': return True, "⛔ ACCOUNT LOCKED"
        return False, "Welcome"
    except: return False, "Error"

def update_xp(student_id, minutes):
    # Gamification Logic: 1 min = 1 XP
    conn = get_db()
    conn.execute(f"UPDATE students SET xp_points = xp_points + {minutes} WHERE student_id={student_id}")
    conn.commit(); conn.close()

# ==========================================
# 3. REGISTRATION
# ==========================================
def show_registration_page():
    st.header("📝 Join S-MART Elite")
    with st.form("kyc"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name"); father = c2.text_input("Father Name")
        c3, c4 = st.columns(2)
        exam = c3.selectbox("Exam", ["UPSC", "NEET", "Other"]); phone = c4.text_input("Phone (Login ID)")
        pw = st.text_input("Password", type="password")
        
        c5, c6 = st.columns(2)
        photo = c5.file_uploader("Photo")
        gid = c6.file_uploader("ID Proof")
        
        if st.form_submit_button("Submit"):
            conn = get_db()
            try:
                p_path = save_uploaded_file(photo, phone) if photo else None
                g_path = save_uploaded_file(gid, phone) if gid else None
                conn.execute("""INSERT INTO students (name, phone, password, exam, father_name, photo_path, govt_id_path, joining_date, status, xp_points) VALUES (?,?,?,?,?,?,?,?,?,?)""", 
                             (name, phone, pw, exam, father, p_path, g_path, date.today(), 'Pending', 0))
                conn.commit(); st.success("Registered! Wait for Approval.")
            except: st.error("Phone used")
            conn.close()

# ==========================================
# 4. ADMIN DASHBOARD (CEO EDITION)
# ==========================================
def show_admin_dashboard():
    if 'selected_student_id' not in st.session_state: st.session_state['selected_student_id'] = None
    st.sidebar.header("👮 Admin Command")
    
    # --- SIDEBAR DOSSIER ---
    if st.session_state['selected_student_id']:
        conn = get_db()
        sid = st.session_state['selected_student_id']
        stu = pd.read_sql(f"SELECT * FROM students WHERE student_id={sid}", conn).iloc[0]
        with st.sidebar:
            st.info("📂 Dossier")
            if stu['photo_path']: st.image(stu['photo_path'], width=150)
            st.write(f"**{stu['name']}** ({stu['xp_points']} XP)")
            st.write(f"📞 {stu['phone']}")
            
            try: due = datetime.strptime(str(stu['due_date']), '%Y-%m-%d').date()
            except: due = date.today()
            days_left = (due - date.today()).days
            
            if days_left < 0: st.error(f"🔴 EXPIRED ({abs(days_left)} days ago)")
            else: st.success(f"🔵 Active ({days_left} days)")

            if st.button("💰 Renew (+30 Days)"):
                new_due = due + timedelta(days=30)
                tx_id = f"TXN{random.randint(10000,99999)}"
                conn.execute("UPDATE students SET due_date=?, status='Active' WHERE student_id=?", (new_due, sid))
                conn.execute("INSERT INTO income (source, amount, date, remarks, transaction_id) VALUES (?,?,?,?,?)", (f"Fee: {stu['name']}", 800, date.today(), 'Monthly', tx_id))
                send_in_app_notification(sid, f"Membership Renewed until {new_due}")
                conn.commit(); st.success("Renewed!"); st.rerun()
                
            if st.button("Close"): st.session_state['selected_student_id'] = None; st.rerun()
        conn.close()

    # TABS
    t1, t2, t3, t4, t5, t6 = st.tabs(["🗺️ Map", "👥 Users", "💰 Finance", "📚 Library", "🎫 Guests", "🚦 Approvals"])
    conn = get_db()
    
    with t1: # MAP
        st.subheader("Live Floor Plan")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        students = pd.read_sql("SELECT student_id, assigned_seat_id, due_date FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        seat_data = {row['assigned_seat_id']: row for _, row in students.iterrows()}
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    sid = s['seat_id']
                    btn_type = "secondary"
                    label = s['seat_label']
                    if sid in seat_data:
                        try:
                            d_date = datetime.strptime(str(seat_data[sid]['due_date']), '%Y-%m-%d').date()
                            days = (d_date - date.today()).days
                            if days < 0: label = f"🔴 {label}"; btn_type="primary"
                            elif days < 7: label = f"🟠 {label}"; btn_type="primary"
                            else: label = f"🔵 {label}"; btn_type="primary"
                        except: btn_type="primary"
                    if cols[i].button(label, key=f"m_{sid}", type=btn_type):
                        if sid in seat_data: st.session_state['selected_student_id'] = seat_data[sid]['student_id']; st.rerun()

    with t2: # USERS
        st.subheader("Student Database")
        filter_opt = st.radio("Filter", ["Active", "Defaulters"], horizontal=True)
        all_students = pd.read_sql("SELECT * FROM students WHERE status != 'Pending'", conn)
        
        for _, r in all_students.iterrows():
            show = True
            try:
                dd = datetime.strptime(str(r['due_date']), '%Y-%m-%d').date()
                if filter_opt == "Defaulters" and (dd - date.today()).days >= 5: show = False
            except: pass
            
            if show:
                with st.expander(f"{r['name']} ({r['xp_points']} XP) - {r['phone']}"):
                    c1, c2 = st.columns(2)
                    if c1.button("📂 Open Dossier", key=f"od_{r['student_id']}"): st.session_state['selected_student_id'] = r['student_id']; st.rerun()
                    msg = f"Dear {r['name']}, Fees Due."
                    c2.link_button("🔔 WhatsApp", f"https://wa.me/91{r['phone']}?text={msg}")

    with t3: # FINANCE
        inc = pd.read_sql("SELECT sum(amount) FROM income", conn).iloc[0,0] or 0
        exp = pd.read_sql("SELECT sum(amount) FROM expenses", conn).iloc[0,0] or 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Income", f"₹{inc}"); c2.metric("Expense", f"₹{exp}"); c3.metric("Profit", f"₹{inc-exp}")
        
        with st.form("add_inc"):
            amt = st.number_input("Misc Income"); rem = st.text_input("Source")
            if st.form_submit_button("Add Income"):
                conn.execute("INSERT INTO income (source, amount, date, remarks) VALUES (?,?,?,?)", ('Misc', amt, date.today(), rem)); conn.commit(); st.rerun()

    with t4: # LIBRARY INVENTORY
        st.subheader("📚 Book Inventory")
        with st.form("add_book"):
            c1, c2 = st.columns(2)
            ti = c1.text_input("Book Title"); sub = c2.text_input("Subject")
            if st.form_submit_button("Add Book"):
                conn.execute("INSERT INTO books (title, subject, author) VALUES (?,?,?)", (ti, sub, 'Unknown')); conn.commit(); st.success("Added")
        
        books = pd.read_sql("SELECT * FROM books", conn)
        st.dataframe(books)

    with t5: # GUESTS (NEW)
        st.subheader("🎫 Daily Guest Pass")
        with st.form("guest"):
            gn = st.text_input("Guest Name"); gp = st.text_input("Phone")
            if st.form_submit_button("Issue Pass (₹50)"):
                conn.execute("INSERT INTO guests (name, phone, date, amount_paid) VALUES (?,?,?,?)", (gn, gp, date.today(), 50))
                conn.execute("INSERT INTO income (source, amount, date, remarks) VALUES (?,?,?,?)", (f"Guest: {gn}", 50, date.today(), 'Guest Pass'))
                conn.commit(); st.success("Pass Issued & Revenue Logged")
        
        guests = pd.read_sql("SELECT * FROM guests ORDER BY guest_id DESC", conn)
        st.dataframe(guests)

    with t6: # APPROVALS
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            c1, c2 = st.columns([3,1])
            c1.write(f"New: **{p['name']}**")
            if c2.button("Approve", key=p['student_id']):
                due = date.today() + timedelta(days=30)
                conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", (due, p['student_id']))
                conn.execute("INSERT INTO income (source, amount, date, remarks) VALUES (?,?,?,?)", (f"Join: {p['name']}", 800, date.today(), 'Fee'))
                conn.commit(); st.rerun()
        
        st.write("---")
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        for _, s in seatless.iterrows():
            c1, c2 = st.columns(2)
            c1.write(f"Assign: **{s['name']}**")
            avail = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            sel = c2.selectbox("Seat", avail['seat_label'], key=f"ss_{s['student_id']}")
            if c2.button("Confirm", key=f"cf_{s['student_id']}"):
                sid = conn.execute(f"SELECT seat_id FROM seats WHERE seat_label='{sel}'").fetchone()[0]
                conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (sid,))
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (sid, s['student_id'])); conn.commit(); st.rerun()
    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD (GAMIFIED)
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked: st.error(msg); st.stop()

    conn = get_db()
    
    # --- HEADER & GAMIFICATION ---
    xp = user[17] if user[17] else 0
    rank = "Novice"
    if xp > 500: rank = "Scholar"
    if xp > 2000: rank = "Grandmaster"
    
    c1, c2 = st.columns([3, 1])
    with c1: st.title(f"👋 {user[1]}")
    with c2: st.metric("XP Points", f"{xp} ⭐", f"{rank}")

    # NOTICE
    latest_notice = pd.read_sql("SELECT * FROM notices ORDER BY id DESC LIMIT 1", conn)
    if not latest_notice.empty: st.markdown(f"<div class='notice-board'>📌 <b>NOTICE:</b> {latest_notice.iloc[0]['message']}</div>", unsafe_allow_html=True)
    st.write("")

    # --- TABS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["⏱️ Focus OS", "🏆 Leaderboard", "🏠 My Profile", "📚 Library", "🧘 Zen"])
    
    with tab1: # FOCUS OS
        st.subheader("🚀 Productivity")
        today_str = str(date.today())
        logs = pd.read_sql(f"SELECT * FROM study_logs WHERE student_id={user[0]} AND date='{today_str}'", conn)
        study_mins = logs[logs['session_type']=='Study']['duration_minutes'].sum()
        
        # Timer Logic
        if 'timer_state' not in st.session_state: st.session_state['timer_state'] = 'Idle'
        
        c_a, c_b = st.columns(2)
        with c_a:
            st.metric("Minutes Today", int(study_mins))
            if st.session_state['timer_state'] == 'Idle':
                if st.button("▶️ START SESSION", type="primary"):
                    st.session_state['timer_state'] = 'Studying'; st.session_state['start_time'] = datetime.now(); st.rerun()
            elif st.session_state['timer_state'] == 'Studying':
                st.success("🔥 FOCUSING...")
                if st.button("⏹️ STOP & SAVE XP"):
                    end = datetime.now(); dur = (end - st.session_state['start_time']).total_seconds() / 60
                    conn.execute("INSERT INTO study_logs (student_id, date, start_time, end_time, duration_minutes, session_type) VALUES (?,?,?,?,?,?)", (user[0], today_str, st.session_state['start_time'], end, int(dur), 'Study'))
                    update_xp(user[0], int(dur)) # GAMIFICATION UPDATE
                    conn.commit()
                    st.session_state['timer_state'] = 'Idle'; st.balloons(); st.rerun()
        
        with c_b:
            st.write("#### ✅ Tasks")
            with st.form("task"):
                t = st.text_input("Goal"); 
                if st.form_submit_button("Add"): conn.execute("INSERT INTO tasks (student_id, task, date) VALUES (?,?,?)", (user[0], t, date.today())); conn.commit(); st.rerun()
            tasks = pd.read_sql(f"SELECT * FROM tasks WHERE student_id={user[0]} AND is_done=0", conn)
            for _, t in tasks.iterrows():
                if st.checkbox(t['task'], key=f"t_{t['task_id']}"): conn.execute("UPDATE tasks SET is_done=1 WHERE task_id=?", (t['task_id'],)); conn.commit(); st.rerun()

    with tab2: # LEADERBOARD (NEW)
        st.subheader("🏆 Top Students (Weekly)")
        leaders = pd.read_sql("SELECT name, xp_points FROM students ORDER BY xp_points DESC LIMIT 5", conn)
        st.dataframe(leaders, use_container_width=True)
        st.caption("Earn XP by using the Study Timer!")

    with tab3: # PROFILE
        c1, c2 = st.columns([1, 2])
        with c1: 
            if user[9]: st.image(user[9], width=150)
        with c2:
            st.markdown(f"""
            <div class="id-card">
                <h3>🆔 S-MART ELITE</h3>
                <h2>{user[1]}</h2>
                <p>Exam: {user[4]}</p>
                <p>Valid Till: {user[12]}</p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🎫 Complaint / Move Request"):
                with st.form("req"):
                    cat = st.selectbox("Type", ["Complaint", "Seat Move"])
                    msg = st.text_area("Details")
                    if st.form_submit_button("Send"):
                        if cat == "Complaint": conn.execute("INSERT INTO complaints (student_id, category, message, status, date) VALUES (?,?,?,?,?)", (user[0], 'General', 'Low', msg, 'Open', date.today()))
                        else: conn.execute("INSERT INTO seat_requests (student_id, current_seat, reason, status) VALUES (?,?,?,?)", (user[0], f"A-{user[15]}", msg, 'Pending'))
                        conn.commit(); st.success("Sent")

    with tab4: # LIBRARY (NEW)
        st.subheader("📚 Book Search")
        books = pd.read_sql("SELECT title, subject, status FROM books", conn)
        st.dataframe(books, use_container_width=True)

    with tab5: # ZEN
        st.subheader("🧘 Zen Zone")
        c1, c2 = st.columns(2)
        with c1: st.link_button("🎵 Lo-Fi Beats", "https://www.youtube.com/watch?v=jfKfPfyJRdk")
        with c2: st.link_button("🌧️ Rain Sounds", "https://www.youtube.com/watch?v=mPZkdNFkNps")
        st.info("🌬️ Breathe: 4s In -> 7s Hold -> 8s Out")

    conn.close()
    st.divider(); st.link_button("💬 Chat Admin", "https://wa.me/919999999999")

# ==========================================
# 6. ROUTER
# ==========================================
def main():
    if 'user' not in st.session_state: st.session_state['user'] = None
    if st.session_state['user']:
        if st.sidebar.button("Logout"): st.session_state['user'] = None; st.rerun()
        if st.session_state['role'] == 'Super': show_admin_dashboard()
        else: show_student_dashboard(st.session_state['user'])
    else:
        menu = st.sidebar.radio("Menu", ["🏠 Home", "📝 Join", "🔐 Login"])
        if menu == "🏠 Home": 
            st.title("S-MART Library"); st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
            st.success("World Class Facilities • Silent Zone • 24/7 Access")
        elif menu == "📝 Join": show_registration_page()
        elif menu == "🔐 Login":
            st.header("Login"); role = st.selectbox("Role", ["Student", "Admin"]); u = st.text_input("User/Phone"); p = st.text_input("Password", type="password")
            if st.button("Enter"):
                conn = get_db()
                if role == 'Admin':
                    user = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (u,p)).fetchone()
                    if user: st.session_state['user'] = user; st.session_state['role'] = 'Super'; st.rerun()
                    else: st.error("Bad Admin Pass")
                else:
                    user = conn.execute("SELECT * FROM students WHERE phone=? AND password=?", (u,p)).fetchone()
                    if user:
                        if user[13] == 0: st.warning("Pending Approval")
                        else: st.session_state['user'] = user; st.session_state['role'] = 'Student'; st.rerun()
                    else: st.error("User not found")
                conn.close()

if __name__ == "__main__":
    main()

import streamlit as st
import sqlite3
import pandas as pd
import os
import random
import time
import altair as alt
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART ULTIMATE V15", page_icon="🏢", layout="wide")

if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v15.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. CORE & AUTH
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    c.execute('''CREATE TABLE IF NOT EXISTS seats (seat_id INTEGER PRIMARY KEY AUTOINCREMENT, seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available')''')
    
    # 2. STUDENTS (FULL KYC PROFILE)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        email TEXT, father_name TEXT, guardian_phone TEXT, address TEXT,
        photo_path TEXT, govt_id_path TEXT,
        joining_date DATE, 
        last_payment_date DATE,
        due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        mercy_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending'
    )''')
    
    # 3. FINANCE & OPS
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount INTEGER, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS income (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, amount INTEGER, date DATE, remarks TEXT, transaction_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, message TEXT, date DATE, is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS complaints (ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, category TEXT, priority TEXT, message TEXT, status TEXT DEFAULT 'Open', date DATE)''')
    
    # 4. PRODUCTIVITY & ANALYTICS
    c.execute('''CREATE TABLE IF NOT EXISTS study_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, date DATE, start_time TIMESTAMP, end_time TIMESTAMP, duration_minutes INTEGER, session_type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS student_targets (student_id INTEGER PRIMARY KEY, daily_target_hours INTEGER DEFAULT 6)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, task TEXT, is_done INTEGER DEFAULT 0, date DATE)''')

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
        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
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
        if s['status'] == 'Active':
            today = date.today()
            try: due = datetime.strptime(str(s['due_date']), '%Y-%m-%d').date()
            except: due = today
            limit = due + timedelta(days=5 + int(s['mercy_days'] or 0))
            if today > limit: return True, "⛔ MEMBERSHIP EXPIRED. Contact Admin."
        return False, "Welcome"
    except: return False, "Error"

# ==========================================
# 3. REGISTRATION (FULL KYC + OTP)
# ==========================================
def show_registration_page():
    st.header("📝 S-MART Admission")
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
            if st.button("Verify OTP"): st.session_state['reg_verified'] = True; st.rerun()
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
            address = st.text_area("Address")
            exam = st.selectbox("Exam", ["UPSC", "NEET", "Other"])
            pw = st.text_input("Password", type="password")
            
            st.subheader("Uploads")
            c5, c6 = st.columns(2)
            photo = c5.file_uploader("Photo")
            gid = c6.file_uploader("ID Proof")
            
            if st.form_submit_button("Submit Application"):
                if photo and gid:
                    p_path = save_uploaded_file(photo, st.session_state['reg_phone'])
                    id_path = save_uploaded_file(gid, st.session_state['reg_phone'])
                    conn = get_db()
                    try:
                        conn.execute("""INSERT INTO students (name, phone, password, exam, email, father_name, guardian_phone, address, photo_path, govt_id_path, joining_date, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                     (name, st.session_state['reg_phone'], pw, exam, email, father, g_phone, address, p_path, id_path, date.today(), 'Pending'))
                        conn.commit(); st.success("Registered! Wait for Approval.")
                    except: st.error("Phone used")
                    conn.close()
                else: st.warning("Please upload Photo and ID")

# ==========================================
# 4. ADMIN DASHBOARD (FINANCE + OPS)
# ==========================================
def show_admin_dashboard():
    if 'selected_student_id' not in st.session_state: st.session_state['selected_student_id'] = None
    st.sidebar.header("👮 Admin Command")
    
    # SIDEBAR 360 VIEW
    if st.session_state['selected_student_id']:
        conn = get_db()
        sid = st.session_state['selected_student_id']
        stu = pd.read_sql(f"SELECT * FROM students WHERE student_id={sid}", conn).iloc[0]
        
        with st.sidebar:
            st.info("📂 Dossier")
            if stu['photo_path']: st.image(stu['photo_path'], width=150)
            st.write(f"**{stu['name']}**")
            st.write(f"📞 {stu['phone']}")
            st.write(f"👨 {stu['father_name']}")
            
            # Renew Logic
            if st.button("💰 Renew Membership"):
                try: due = datetime.strptime(str(stu['due_date']), '%Y-%m-%d').date()
                except: due = date.today()
                new_due = due + timedelta(days=30)
                tx_id = f"TXN{random.randint(10000,99999)}"
                conn.execute("UPDATE students SET due_date=?, last_payment_date=?, status='Active' WHERE student_id=?", (new_due, date.today(), sid))
                conn.execute("INSERT INTO income (student_id, amount, date, remarks, transaction_id) VALUES (?,?,?,?,?)", (sid, 800, date.today(), 'Fee', tx_id))
                send_in_app_notification(sid, f"Payment Received. Valid till {new_due}")
                conn.commit()
                st.success("Renewed!")
                rec_msg = f"Receipt: Received Rs 800 from {stu['name']} on {date.today()}. Txn: {tx_id}"
                st.link_button("📲 Send WhatsApp Receipt", f"https://wa.me/91{stu['phone']}?text={rec_msg}")

            if st.button("Close"): st.session_state['selected_student_id'] = None; st.rerun()
        conn.close()

    # TABS
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗺️ Map", "👥 Database", "💰 Finance", "🚦 Approvals", "📢 Ops"])
    conn = get_db()
    
    # TAB 1: MAP
    with tab1:
        st.subheader("Live Floor Plan")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        active_s = pd.read_sql("SELECT assigned_seat_id, student_id, due_date FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        s_map = {}
        for _, r in active_s.iterrows(): s_map[r['assigned_seat_id']] = r
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    sid = s['seat_id']
                    label = s['seat_label']
                    btn_type = "secondary"
                    if sid in s_map:
                        try:
                            dd = datetime.strptime(str(s_map[sid]['due_date']), '%Y-%m-%d').date()
                            days = (dd - date.today()).days
                            if days < 0: label = f"🔴 {label}"; btn_type="primary"
                            elif days < 7: label = f"🟠 {label}"; btn_type="primary"
                            else: label = f"🔵 {label}"; btn_type="primary"
                        except: btn_type="primary"
                    
                    if cols[i].button(label, key=f"m_{sid}", type=btn_type):
                        if sid in s_map: st.session_state['selected_student_id'] = s_map[sid]['student_id']; st.rerun()

    # TAB 2: DATABASE
    with tab2:
        st.subheader("Master List")
        filter_opt = st.radio("Filter", ["Active", "Defaulters"], horizontal=True)
        query = "SELECT * FROM students WHERE status != 'Pending'"
        df = pd.read_sql(query, conn)
        
        # Filter Logic in Python for date calc
        for _, r in df.iterrows():
            try:
                dd = datetime.strptime(str(r['due_date']), '%Y-%m-%d').date()
                days = (dd - date.today()).days
                is_defaulter = days < 5
            except: is_defaulter = False
            
            show = True
            if filter_opt == "Defaulters" and not is_defaulter: show = False
            
            if show:
                with st.expander(f"{r['name']} ({r['phone']}) - Due: {r['due_date']}"):
                    c1, c2 = st.columns(2)
                    if c1.button("📂 Open Dossier", key=f"od_{r['student_id']}"):
                        st.session_state['selected_student_id'] = r['student_id']; st.rerun()
                    
                    # Reminder
                    msg = f"Dear {r['name']}, your fees are due. Please pay to avoid suspension."
                    c2.link_button("🔔 WhatsApp Reminder", f"https://wa.me/91{r['phone']}?text={msg}")
                    if c2.button("📲 App Reminder", key=f"ar_{r['student_id']}"):
                        send_in_app_notification(r['student_id'], "URGENT: Fees Due."); st.success("Sent")

    # TAB 3: FINANCE
    with tab3:
        st.subheader("Financials")
        inc = pd.read_sql("SELECT sum(amount) FROM income", conn).iloc[0,0] or 0
        exp = pd.read_sql("SELECT sum(amount) FROM expenses", conn).iloc[0,0] or 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Income", f"₹{inc}"); c2.metric("Expense", f"₹{exp}"); c3.metric("Profit", f"₹{inc-exp}")
        
        with st.form("add_exp"):
            cat = st.selectbox("Category", ["Rent", "Elec", "Staff"])
            amt = st.number_input("Amount")
            if st.form_submit_button("Add Expense"):
                conn.execute("INSERT INTO expenses (category, amount, date) VALUES (?,?,?)", (cat, amt, date.today())); conn.commit(); st.rerun()

    # TAB 4: APPROVALS
    with tab4:
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            c1, c2 = st.columns([3,1])
            c1.write(f"New: **{p['name']}**")
            if c2.button("Approve", key=p['student_id']):
                due = date.today() + timedelta(days=30)
                conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=?, last_payment_date=? WHERE student_id=?", (due, date.today(), p['student_id']))
                conn.execute("INSERT INTO income (student_id, amount, date, remarks) VALUES (?,?,?,?)", (p['student_id'], 800, date.today(), 'Join Fee'))
                conn.commit(); st.rerun()
        
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
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (sid, s['student_id'])); conn.commit(); st.rerun()

    # TAB 5: OPS (Notices, Moves, Complaints)
    with tab5:
        st.write("#### 📢 Broadcast")
        msg = st.text_input("Message"); 
        if st.button("Post"): conn.execute("INSERT INTO notices (message, type, date) VALUES (?,?,?)", (msg, 'General', date.today())); conn.commit(); st.success("Posted")
        
        st.write("#### 🎫 Complaints")
        comps = pd.read_sql("SELECT * FROM complaints WHERE status='Open'", conn)
        for _, c in comps.iterrows():
            st.error(f"[{c['priority']}] {c['category']}: {c['message']}")
            if st.button("Resolve", key=f"cmp_{c['ticket_id']}"):
                conn.execute("UPDATE complaints SET status='Resolved' WHERE ticket_id=?", (c['ticket_id'],)); conn.commit(); st.rerun()

    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD (PRODUCTIVITY + ZEN)
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked: st.error(msg); st.stop()

    # --- HUD ---
    conn = get_db()
    today_str = str(date.today())
    logs = pd.read_sql(f"SELECT * FROM study_logs WHERE student_id={user[0]} AND date='{today_str}'", conn)
    study_mins = logs[logs['session_type']=='Study']['duration_minutes'].sum()
    break_mins = logs[logs['session_type']=='Break']['duration_minutes'].sum()
    
    if 'timer_state' not in st.session_state: st.session_state['timer_state'] = 'Idle' 
    if 'start_time' not in st.session_state: st.session_state['start_time'] = None

    st.markdown("""<style>div.stButton > button {width: 100%;}</style>""", unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a: st.metric("📚 Study", f"{int(study_mins)} min")
    with col_b: st.metric("☕ Break", f"{int(break_mins)} min")
    with col_c:
        if st.session_state['timer_state'] == 'Idle':
            if st.button("▶️ START FOCUS", type="primary"):
                st.session_state['timer_state'] = 'Studying'; st.session_state['start_time'] = datetime.now(); st.rerun()
        elif st.session_state['timer_state'] == 'Studying':
            c1, c2 = st.columns(2)
            with c1:
                if st.button("☕ BREAK"):
                    end = datetime.now(); dur = (end - st.session_state['start_time']).total_seconds() / 60
                    conn.execute("INSERT INTO study_logs (student_id, date, start_time, end_time, duration_minutes, session_type) VALUES (?,?,?,?,?,?)", (user[0], today_str, st.session_state['start_time'], end, int(dur), 'Study')); conn.commit()
                    st.session_state['timer_state'] = 'Breaking'; st.session_state['start_time'] = datetime.now(); st.rerun()
            with c2:
                if st.button("⏹️ END"):
                    end = datetime.now(); dur = (end - st.session_state['start_time']).total_seconds() / 60
                    conn.execute("INSERT INTO study_logs (student_id, date, start_time, end_time, duration_minutes, session_type) VALUES (?,?,?,?,?,?)", (user[0], today_str, st.session_state['start_time'], end, int(dur), 'Study')); conn.commit()
                    st.session_state['timer_state'] = 'Idle'; st.rerun()
        elif st.session_state['timer_state'] == 'Breaking':
            st.warning("☕ ON BREAK")
            if st.button("▶️ RESUME"):
                end = datetime.now(); dur = (end - st.session_state['start_time']).total_seconds() / 60
                conn.execute("INSERT INTO study_logs (student_id, date, start_time, end_time, duration_minutes, session_type) VALUES (?,?,?,?,?,?)", (user[0], today_str, st.session_state['start_time'], end, int(dur), 'Break')); conn.commit()
                st.session_state['timer_state'] = 'Studying'; st.session_state['start_time'] = datetime.now(); st.rerun()
    st.divider()

    # TABS
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏠 Hub", "📊 Stats", "🧘 Zen", "🎫 Support", "📜 Receipts"])
    
    with tab1: # HUB
        c1, c2 = st.columns([1, 2])
        with c1:
            if user[9]: st.image(user[9], width=180)
            st.write(f"**Seat:** A-{user[15]}")
        with c2:
            st.markdown(f"""<div style="background-color:#e8f4f8;padding:20px;border-radius:15px;color:black;"><h3>🆔 S-MART MEMBER</h3><p><b>Name:</b> {user[1]}</p><p><b>Valid Till:</b> {user[12]}</p></div>""", unsafe_allow_html=True)
            notifs = pd.read_sql(f"SELECT * FROM notifications WHERE student_id={user[0]} ORDER BY id DESC LIMIT 5", conn)
            if not notifs.empty:
                st.write("#### 🔔 Alerts")
                for _, n in notifs.iterrows(): st.info(f"{n['date']}: {n['message']}")
        
        # To-Do List
        st.write("#### ✅ Tasks")
        with st.form("task"):
            t = st.text_input("Add Task")
            if st.form_submit_button("Add"): conn.execute("INSERT INTO tasks (student_id, task, date) VALUES (?,?,?)", (user[0], t, date.today())); conn.commit(); st.rerun()
        tasks = pd.read_sql(f"SELECT * FROM tasks WHERE student_id={user[0]} AND is_done=0", conn)
        for _, t in tasks.iterrows():
            if st.checkbox(t['task'], key=f"t_{t['task_id']}"): conn.execute("UPDATE tasks SET is_done=1 WHERE task_id=?", (t['task_id'],)); conn.commit(); st.rerun()

    with tab2: # STATS
        hist = pd.read_sql(f"SELECT date, session_type, sum(duration_minutes) as mins FROM study_logs WHERE student_id={user[0]} GROUP BY date, session_type", conn)
        if not hist.empty:
            chart = alt.Chart(hist).mark_bar().encode(x='date', y='mins', color='session_type').properties(height=250)
            st.altair_chart(chart, use_container_width=True)
    
    with tab3: # ZEN
        st.subheader("🧘 Zen Lounge")
        c1, c2 = st.columns(2)
        with c1: st.link_button("🎵 Lo-Fi Music", "https://www.youtube.com/watch?v=jfKfPfyJRdk")
        with c2: st.link_button("🌧️ Rain Sounds", "https://www.youtube.com/watch?v=mPZkdNFkNps")
        st.info("🌬️ Breathe: Inhale (4s) -> Hold (7s) -> Exhale (8s)")

    with tab4: # SUPPORT
        with st.expander("🎫 Complaint"):
            with st.form("comp"):
                cat = st.selectbox("Category", ["AC", "Noise", "Other"]); prio = st.selectbox("Priority", ["Low", "High"]); msg = st.text_area("Message")
                if st.form_submit_button("Submit"): conn.execute("INSERT INTO complaints (student_id, category, priority, message, status, date) VALUES (?,?,?,?,?,?)", (user[0], cat, prio, msg, 'Open', date.today())); conn.commit(); st.success("Sent")
        with st.expander("💺 Seat Change"):
            with st.form("mv"):
                ns = st.text_input("New Seat"); res = st.selectbox("Reason", ["AC", "Noise"])
                if st.form_submit_button("Request"): conn.execute("INSERT INTO seat_requests (student_id, current_seat, requested_seat, reason, status) VALUES (?,?,?,?,?)", (user[0], f"A-{user[15]}", ns, res, 'Pending')); conn.commit(); st.success("Requested")

    with tab5: # RECEIPTS
        recs = pd.read_sql(f"SELECT * FROM income WHERE student_id={user[0]} ORDER BY id DESC", conn)
        for _, r in recs.iterrows(): st.success(f"✅ Rs {r['amount']} - {r['date']} (Txn: {r['transaction_id']})")

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
        if menu == "🏠 Home": st.title("S-MART Library"); st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
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

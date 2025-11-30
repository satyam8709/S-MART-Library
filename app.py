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
st.set_page_config(page_title="S-MART V14 FINANCE", page_icon="💳", layout="wide")

if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v14.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. CORE
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    c.execute('''CREATE TABLE IF NOT EXISTS seats (seat_id INTEGER PRIMARY KEY AUTOINCREMENT, seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available')''')
    
    # 2. STUDENTS
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
    # Income table acts as Receipt Log
    c.execute('''CREATE TABLE IF NOT EXISTS income (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        student_id INTEGER, 
        amount INTEGER, 
        date DATE, 
        remarks TEXT,
        transaction_id TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, message TEXT, date DATE, is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS complaints (ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, category TEXT, priority TEXT, message TEXT, status TEXT DEFAULT 'Open', date DATE)''')
    
    # 4. ANALYTICS
    c.execute('''CREATE TABLE IF NOT EXISTS study_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, date DATE, start_time TIMESTAMP, end_time TIMESTAMP, duration_minutes INTEGER, session_type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS student_targets (student_id INTEGER PRIMARY KEY, daily_target_hours INTEGER DEFAULT 6)''')

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
            if today > limit:
                return True, "⛔ MEMBERSHIP EXPIRED. Contact Admin."
        return False, "Welcome"
    except: return False, "Error"

# ==========================================
# 3. REGISTRATION
# ==========================================
def show_registration_page():
    st.header("📝 S-MART Admission")
    with st.form("kyc"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name"); father = c2.text_input("Father Name")
        c3, c4 = st.columns(2)
        exam = c3.selectbox("Exam", ["UPSC", "NEET", "Other"]); phone = c4.text_input("Phone (Login ID)")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Submit"):
            conn = get_db()
            try:
                conn.execute("""INSERT INTO students (name, phone, password, exam, father_name, joining_date, status) VALUES (?,?,?,?,?,?,?)""", 
                             (name, phone, pw, exam, father, date.today(), 'Pending'))
                conn.commit(); st.success("Registered! Wait for Approval.")
            except: st.error("Phone used")
            conn.close()

# ==========================================
# 4. ADMIN DASHBOARD (V14)
# ==========================================
def show_admin_dashboard():
    if 'selected_student_id' not in st.session_state: st.session_state['selected_student_id'] = None
    st.sidebar.header("👮 Admin Command")
    
    # --- SIDEBAR DOSSIER (RECEIPT GENERATOR) ---
    if st.session_state['selected_student_id']:
        conn = get_db()
        sid = st.session_state['selected_student_id']
        stu = pd.read_sql(f"SELECT * FROM students WHERE student_id={sid}", conn).iloc[0]
        
        with st.sidebar:
            st.info("📂 Student Dossier")
            if stu['photo_path']: st.image(stu['photo_path'], width=150)
            st.write(f"### {stu['name']}")
            st.write(f"**📞 Phone:** {stu['phone']}")
            
            # Status Logic
            today = date.today()
            try: due = datetime.strptime(str(stu['due_date']), '%Y-%m-%d').date()
            except: due = today
            days_left = (due - today).days
            
            if days_left < 0: st.error(f"🔴 EXPIRED ({abs(days_left)} days ago)")
            elif days_left < 7: st.warning(f"🟠 EXPIRING ({days_left} days)")
            else: st.success(f"🔵 ACTIVE ({days_left} days)")

            st.divider()
            st.write("#### 💸 Fee Operations")
            
            # RENEW & GENERATE RECEIPT
            if st.button("💰 Renew + Generate Receipt"):
                new_due = due + timedelta(days=30)
                tx_id = f"TXN{random.randint(10000,99999)}"
                
                # 1. Update Student
                conn.execute("UPDATE students SET due_date=?, last_payment_date=?, status='Active' WHERE student_id=?", (new_due, date.today(), sid))
                # 2. Log Income (Receipt)
                conn.execute("INSERT INTO income (student_id, amount, date, remarks, transaction_id) VALUES (?,?,?,?,?)", (sid, 800, date.today(), 'Monthly Fee', tx_id))
                # 3. Send App Notification
                send_in_app_notification(sid, f"Payment Received: Rs 800. Validity extended to {new_due}.")
                conn.commit()
                
                st.success("Renewed!")
                
                # WHATSAPP RECEIPT
                receipt_text = f"*S-MART LIBRARY RECEIPT* %0A%0A Name: {stu['name']} %0A Amount: Rs 800 %0A Date: {date.today()} %0A Valid Till: {new_due} %0A Txn ID: {tx_id} %0A%0A _Thank you for your payment!_"
                st.link_button("📲 Send Receipt on WhatsApp", f"https://wa.me/91{stu['phone']}?text={receipt_text}")

            if st.button("Close"): st.session_state['selected_student_id'] = None; st.rerun()
        conn.close()

    # MAIN TABS
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "👥 Students", "💰 Dues & Reminders", "📢 Notice Board"])
    conn = get_db()
    
    # --- TAB 1: DASHBOARD ---
    with tab1:
        st.subheader("Live Status")
        col_map, col_stats = st.columns([2, 1])
        
        with col_map:
            st.caption("🔵 Safe | 🟠 Expiring | 🔴 Expired | ⚪ Empty")
            seats = pd.read_sql("SELECT * FROM seats", conn)
            # Seat coloring logic
            students = pd.read_sql("SELECT student_id, assigned_seat_id, due_date FROM students WHERE assigned_seat_id IS NOT NULL", conn)
            seat_data = {}
            for _, s in students.iterrows(): seat_data[s['assigned_seat_id']] = s
            
            for r in range(0, 100, 10):
                cols = st.columns(10)
                for i in range(10):
                    if r+i < len(seats):
                        s = seats.iloc[r+i]
                        sid = s['seat_id']
                        btn_type = "secondary"
                        label = s['seat_label']
                        
                        if sid in seat_data:
                            # Color Logic
                            try:
                                d_date = datetime.strptime(str(seat_data[sid]['due_date']), '%Y-%m-%d').date()
                                d_left = (d_date - date.today()).days
                                if d_left < 0: label = f"🔴 {s['seat_label']}"; btn_type="primary"
                                elif d_left < 7: label = f"🟠 {s['seat_label']}"; btn_type="primary"
                                else: label = f"🔵 {s['seat_label']}"; btn_type="primary"
                            except: btn_type="primary"
                        
                        if cols[i].button(label, key=f"m_{sid}", type=btn_type):
                            if sid in seat_data: st.session_state['selected_student_id'] = seat_data[sid]['student_id']; st.rerun()

    # --- TAB 2: STUDENTS ---
    with tab2:
        st.subheader("Master Database")
        all_students = pd.read_sql("SELECT student_id, name, phone, due_date FROM students WHERE status != 'Pending'", conn)
        for _, r in all_students.iterrows():
            c1, c2, c3, c4 = st.columns([2,2,2,1])
            c1.write(f"**{r['name']}**")
            c2.write(f"{r['phone']}")
            c3.write(f"Due: {r['due_date']}")
            if c4.button("Open", key=f"o_{r['student_id']}"):
                st.session_state['selected_student_id'] = r['student_id']
                st.rerun()

    # --- TAB 3: DUES & REMINDERS (NEW) ---
    with tab3:
        st.subheader("🔔 Dues Management")
        st.info("List of students expiring in next 5 days or already expired.")
        
        # Filter Logic
        today_str = str(date.today())
        limit_str = str(date.today() + timedelta(days=5))
        
        defaulters = pd.read_sql(f"SELECT * FROM students WHERE due_date <= '{limit_str}' AND status != 'Alumni' AND status != 'Pending'", conn)
        
        if not defaulters.empty:
            for _, d in defaulters.iterrows():
                with st.expander(f"⚠️ {d['name']} (Due: {d['due_date']})"):
                    c1, c2 = st.columns(2)
                    
                    # APP REMINDER
                    if c1.button("📲 Send App Notification", key=f"notif_{d['student_id']}"):
                        send_in_app_notification(d['student_id'], "URGENT: Your fees are due. Please pay to avoid lockout.")
                        st.success("Sent!")
                    
                    # WHATSAPP REMINDER
                    msg = f"Dear {d['name']}, your library fee is due on {d['due_date']}. Please pay to avoid membership suspension."
                    c2.link_button("🟢 WhatsApp Reminder", f"https://wa.me/91{d['phone']}?text={msg}")
        else:
            st.success("No pending dues! Everyone is paid up.")

    # --- TAB 4: NOTICE BOARD ---
    with tab4:
        st.subheader("📢 Broadcast Notice")
        msg = st.text_area("Write Notice (e.g. 'Library Closed Tomorrow')")
        if st.button("Post to All Students"):
            conn.execute("INSERT INTO notices (message, type, date) VALUES (?,?,?)", (msg, 'General', date.today()))
            conn.commit()
            st.success("Broadcasted successfully!")
            
        st.write("#### Recent Notices")
        notices = pd.read_sql("SELECT * FROM notices ORDER BY id DESC LIMIT 5", conn)
        for _, n in notices.iterrows():
            st.info(f"{n['date']}: {n['message']}")

    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked: st.error(msg); st.stop()

    st.title(f"👋 {user[1]}")

    # NOTICE BOARD
    conn = get_db()
    latest_notice = pd.read_sql("SELECT * FROM notices ORDER BY id DESC LIMIT 1", conn)
    if not latest_notice.empty:
        n = latest_notice.iloc[0]
        st.error(f"📢 NOTICE: {n['message']}")

    tab1, tab2 = st.tabs(["🏠 My Hub", "📜 Payment History"])
    
    with tab1: # HUB
        c1, c2 = st.columns([1, 2])
        with c1:
            if user[9]: st.image(user[9], width=180)
            st.write(f"**Seat:** A-{user[15]}")
        with c2:
            st.markdown(f"""
            <div style="background-color:#e8f4f8;padding:20px;border-radius:15px;color:black;">
                <h3 style='margin:0'>🆔 S-MART MEMBER</h3>
                <p><b>Name:</b> {user[1]}</p>
                <p><b>Valid Till:</b> {user[12]}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # NOTIFICATIONS
            notifs = pd.read_sql(f"SELECT * FROM notifications WHERE student_id={user[0]} ORDER BY id DESC LIMIT 5", conn)
            if not notifs.empty:
                st.write("#### 🔔 Alerts")
                for _, n in notifs.iterrows(): st.info(f"{n['date']}: {n['message']}")

    with tab2: # PAYMENT HISTORY
        st.subheader("📜 My Receipts")
        receipts = pd.read_sql(f"SELECT * FROM income WHERE student_id={user[0]} ORDER BY id DESC", conn)
        
        if not receipts.empty:
            for _, r in receipts.iterrows():
                st.success(f"✅ **Rs {r['amount']}** paid on {r['date']} (Txn: {r['transaction_id']})")
        else:
            st.info("No payment history found.")

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

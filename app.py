import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import date, datetime, timedelta

# ==========================================
# 1. SYSTEM CONFIGURATION & DATABASE
# ==========================================
st.set_page_config(page_title="S-MART ULTIMATE", page_icon="🏢", layout="wide")

# *** CRITICAL: We renamed DB to v3 to fix your error ***
if not os.path.exists('data'): os.makedirs('data')
DB_NAME = 'data/smart_library_v3.db'

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
    
    # 3. STUDENTS (The Full Profile)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        joining_date DATE, 
        due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        mercy_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending' -- Pending, Active, Locked, Left
    )''')
    
    # 4. EXPENSES (New Feature)
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, amount INTEGER, date DATE, note TEXT
    )''')
    
    # 5. NOTICES (New Feature)
    c.execute('''CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT, type TEXT, date DATE
    )''')
    
    # 6. SEAT REQUESTS (New Feature - Move/Swap)
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (
        req_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT
    )''')

    # Auto-generate 100 Seats
    c.execute('SELECT count(*) FROM seats')
    if c.fetchone()[0] == 0:
        seats = [(f"A-{i}", 1 if i%5==0 else 0, 'Available') for i in range(1, 101)]
        c.executemany('INSERT INTO seats (seat_label, has_locker, status) VALUES (?,?,?)', seats)
        
    conn.commit()
    conn.close()

if not os.path.exists(DB_NAME): init_db()

# ==========================================
# 2. LOGIC ENGINES
# ==========================================

def check_lockout(student):
    # The "Digital Eviction" Logic
    # student tuple structure changes based on query, so we fetch by ID to be safe
    conn = get_db()
    s = pd.read_sql(f"SELECT * FROM students WHERE student_id={student[0]}", conn).iloc[0]
    conn.close()
    
    if s['status'] == 'Active':
        today = date.today()
        due = datetime.strptime(s['due_date'], '%Y-%m-%d').date() if s['due_date'] else today
        
        # Zone 3: Lockout (Due + 5 days + Mercy)
        limit = due + timedelta(days=5 + s['mercy_days'])
        
        if today > limit:
            # Auto-Lock
            conn = get_db()
            conn.execute("UPDATE students SET status='Locked' WHERE student_id=?", (s['student_id'],))
            conn.commit()
            conn.close()
            return True, "⛔ ACCOUNT LOCKED: Fees Overdue. Contact Admin."
            
        # Zone 2: Grace Period Warning
        elif today > due:
            days_left = (limit - today).days
            return False, f"⚠️ WARNING: Fees Overdue! Lockout in {days_left} days."
            
    elif s['status'] == 'Locked':
        return True, "⛔ ACCOUNT LOCKED: Fees Overdue. Contact Admin."
        
    return False, "Welcome"

# ==========================================
# 3. ADMIN DASHBOARD (The Command Center)
# ==========================================
def show_admin_dashboard():
    st.sidebar.markdown("---")
    st.sidebar.header("👮 Admin Controls")
    
    # TABS FOR EVERYTHING
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗺️ Map", "🚦 Approvals", "💸 Finance", "📢 Notices", "💺 Moves"])
    
    conn = get_db()
    
    # --- TAB 1: SEAT MAP ---
    with tab1:
        st.subheader("Live Floor Plan")
        st.caption("🔴 Occupied | 🟢 Available | 🟡 Mercy Mode")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    label = s['seat_label']
                    status = s['status']
                    btn_type = "primary" if status != 'Available' else "secondary"
                    display = f"⚠️ {label}" if status == 'Mercy' else label
                    
                    cols[i].button(display, key=f"map_{s['seat_id']}", type=btn_type)

    # --- TAB 2: APPROVALS ---
    with tab2:
        st.subheader("Gate 1: Profile Approvals")
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            c1, c2 = st.columns([3,1])
            c1.warning(f"New Applicant: **{p['name']}** ({p['phone']})")
            if c2.button("✅ Approve", key=f"ap_{p['student_id']}"):
                conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", 
                             (date.today() + timedelta(days=30), p['student_id']))
                conn.commit()
                st.rerun()

        st.divider()
        st.subheader("Gate 2: Assign Seats")
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        for _, s in seatless.iterrows():
            c1, c2, c3 = st.columns([2,2,1])
            c1.write(f"**{s['name']}** needs a seat.")
            avail = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            sel_seat = c2.selectbox("Seat", avail['seat_label'], key=f"ss_{s['student_id']}")
            if c3.button("Assign", key=f"assign_{s['student_id']}"):
                # Update Seat
                seat_id = conn.execute(f"SELECT seat_id FROM seats WHERE seat_label='{sel_seat}'").fetchone()[0]
                conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (seat_id,))
                # Update Student
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (seat_id, s['student_id']))
                conn.commit()
                st.success("Seat Assigned!")
                st.rerun()

    # --- TAB 3: FINANCE & EXPENSES ---
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📉 Add Expense")
            with st.form("exp_form"):
                cat = st.selectbox("Category", ["Electricity", "Rent", "Staff", "Maintenance"])
                amt = st.number_input("Amount", step=100)
                note = st.text_input("Note")
                if st.form_submit_button("Add Expense"):
                    conn.execute("INSERT INTO expenses (category, amount, date, note) VALUES (?,?,?,?)", (cat, amt, date.today(), note))
                    conn.commit()
                    st.success("Saved.")
        
        with c2:
            st.subheader("📊 Net Profit")
            fees = 50000 # Placeholder for total fees logic
            exps = pd.read_sql("SELECT sum(amount) FROM expenses", conn).iloc[0,0]
            exps = exps if exps else 0
            st.metric("Total Expenses", f"₹{exps}")
            st.metric("Estimated Profit", f"₹{fees - exps}")

    # --- TAB 4: NOTICES ---
    with tab4:
        st.subheader("📢 Digital Megaphone")
        txt = st.text_input("Broadcast Message")
        if st.button("Post Notice"):
            conn.execute("INSERT INTO notices (message, type, date) VALUES (?,?,?)", (txt, 'General', date.today()))
            conn.commit()
            st.success("Notice Posted to all Student Apps.")
            
    # --- TAB 5: SEAT MOVES ---
    with tab5:
        st.subheader("💺 Seat Change Requests")
        reqs = pd.read_sql("SELECT * FROM seat_requests WHERE status='Pending'", conn)
        if reqs.empty: st.info("No requests.")
        for _, r in reqs.iterrows():
            st.info(f"Student ID {r['student_id']} wants to move from {r['current_seat']} to {r['requested_seat']}. Reason: {r['reason']}")
            if st.button("Approve Move", key=f"mv_{r['req_id']}"):
                # Logic to free old seat and occupy new seat
                # (Simplified for v3)
                conn.execute("UPDATE seat_requests SET status='Approved' WHERE req_id=?", (r['req_id'],))
                conn.commit()
                st.success("Move Approved (Update map manually in v3)")
                st.rerun()

# ==========================================
# 4. STUDENT DASHBOARD
# ==========================================
def show_student_dashboard(user):
    # LOCKOUT CHECK
    is_locked, msg = check_lockout(user)
    
    if is_locked:
        st.error(msg)
        st.warning("Please pay your fees to unlock the app.")
        st.stop() # Kill Switch
        
    if "WARNING" in msg:
        st.warning(msg) # Zone 2 Warning

    # HEADER & ID CARD
    st.title(f"🎓 Dashboard")
    
    # Notices Marquee
    conn = get_db()
    notices = pd.read_sql("SELECT message FROM notices ORDER BY id DESC LIMIT 1", conn)
    if not notices.empty:
        st.info(f"📢 NOTICE: {notices.iloc[0]['message']}")
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown(f"""
        <div style="background-color:#f0f2f6;padding:15px;border-radius:10px;border-left:5px solid #00C851;">
            <h3>🆔 S-MART ID</h3>
            <b>Name:</b> {user[1]}<br>
            <b>ID:</b> {user[0]}<br>
            <b>Exam:</b> {user[4]}<br>
            <b>Seat:</b> A-{user[9]}
        </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.subheader("Request Seat Change")
        with st.form("move_form"):
            new_seat = st.text_input("Preferred Seat (e.g. B-5)")
            reason = st.selectbox("Reason", ["AC Issue", "Light Issue", "Too Noisy", "Friend"])
            if st.form_submit_button("Submit Request"):
                conn.execute("INSERT INTO seat_requests (student_id, current_seat, requested_seat, reason, status) VALUES (?,?,?,?,?)",
                             (user[0], f"A-{user[9]}", new_seat, reason, 'Pending'))
                conn.commit()
                st.success("Request sent to Admin.")

    st.divider()
    msg = f"Hi Admin, I am {user[1]}. Help needed."
    st.link_button("💬 Chat with Admin", f"https://wa.me/919999999999?text={msg}")

# ==========================================
# 5. MAIN ROUTER
# ==========================================
def main():
    if 'user' not in st.session_state: st.session_state['user'] = None
    
    if st.session_state['user']:
        # LOGGED IN
        user = st.session_state['user']
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()
            
        if st.session_state['role'] == 'Super': show_admin_dashboard()
        else: show_student_dashboard(user)
        
    else:
        # PUBLIC / LOGIN
        menu = st.sidebar.radio("Menu", ["🏠 Home", "📝 Join", "🔐 Login"])
        
        if menu == "🏠 Home":
            st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
            st.title("S-MART Library")
            st.success("Lead Trap: Check Availability below (Login required to see map in v3)")
            
        elif menu == "📝 Join":
            st.header("New Admission")
            with st.form("reg"):
                name = st.text_input("Name")
                phone = st.text_input("Phone")
                pw = st.text_input("Password", type="password")
                exam = st.selectbox("Exam", ["UPSC", "NEET", "Other"])
                if st.form_submit_button("Register"):
                    conn = get_db()
                    try:
                        conn.execute("INSERT INTO students (name, phone, password, exam, joining_date, due_date) VALUES (?,?,?,?,?,?)", 
                                     (name, phone, pw, exam, date.today(), date.today()+timedelta(days=30)))
                        conn.commit()
                        st.success("Registered! Wait for Approval.")
                    except: st.error("Phone used.")
                    
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
                        if user[7] == 0: st.warning("Profile Pending Approval")
                        else:
                            st.session_state['user'] = user
                            st.session_state['role'] = 'Student'
                            st.rerun()
                    else: st.error("User not found")

if __name__ == "__main__":
    main()

import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import date, datetime, timedelta

# ==========================================
# 1. SYSTEM CONFIGURATION & DATABASE
# ==========================================
st.set_page_config(page_title="S-MART ULTIMATE", page_icon="🏢", layout="wide")

# Database Path
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
    
    # 3. STUDENTS
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        joining_date DATE, 
        due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        mercy_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending' 
    )''')
    
    # 4. EXPENSES
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, amount INTEGER, date DATE, note TEXT
    )''')
    
    # 5. NOTICES
    c.execute('''CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT, type TEXT, date DATE
    )''')
    
    # 6. SEAT REQUESTS
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
# 2. LOGIC ENGINES (The Brains)
# ==========================================

def check_lockout(student_id):
    # Retrieve fresh student data
    conn = get_db()
    # Handle case where student ID might not be found
    try:
        df = pd.read_sql(f"SELECT * FROM students WHERE student_id={student_id}", conn)
        conn.close()
        
        if df.empty:
            return False, "User not found"

        s = df.iloc[0]
        
        # *** SAFETY FIX: Handle Empty Mercy Days ***
        mercy = s['mercy_days']
        if pd.isna(mercy) or mercy is None:
            mercy = 0
        else:
            mercy = int(mercy)

        if s['status'] == 'Active':
            today = date.today()
            # Parse Due Date safely
            try:
                if s['due_date']:
                    due = datetime.strptime(str(s['due_date']), '%Y-%m-%d').date()
                else:
                    due = today # Fallback
            except:
                due = today

            # Logic: Due Date + 5 Days Buffer + Mercy Days
            limit = due + timedelta(days=5 + mercy)
            
            if today > limit:
                # Auto-Lock in DB
                conn = get_db()
                conn.execute("UPDATE students SET status='Locked' WHERE student_id=?", (student_id,))
                conn.commit()
                conn.close()
                return True, "⛔ ACCOUNT LOCKED: Fees Overdue. Contact Admin."
                
            elif today > due:
                days_left = (limit - today).days
                return False, f"⚠️ WARNING: Fees Overdue! Lockout in {days_left} days."
                
        elif s['status'] == 'Locked':
            return True, "⛔ ACCOUNT LOCKED: Fees Overdue. Contact Admin."
            
        return False, "Welcome"
    except Exception as e:
        return False, f"System Check Error: {e}"

# ==========================================
# 3. ADMIN DASHBOARD
# ==========================================
def show_admin_dashboard():
    st.sidebar.markdown("---")
    st.sidebar.header("👮 Admin Controls")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗺️ Map", "🚦 Approvals", "💸 Finance", "📢 Notices", "💺 Moves"])
    
    conn = get_db()
    
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

    with tab2:
        st.subheader("Profile Approvals")
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            c1, c2 = st.columns([3,1])
            c1.warning(f"New: **{p['name']}** ({p['phone']})")
            if c2.button("✅ Approve", key=f"ap_{p['student_id']}"):
                # Set due date to 30 days from now upon approval
                next_month = date.today() + timedelta(days=30)
                conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=?, mercy_days=0 WHERE student_id=?", 
                             (next_month, p['student_id']))
                conn.commit()
                st.rerun()

        st.divider()
        st.subheader("Assign Seats")
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        for _, s in seatless.iterrows():
            c1, c2, c3 = st.columns([2,2,1])
            c1.write(f"**{s['name']}**")
            avail = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            sel_seat = c2.selectbox("Seat", avail['seat_label'], key=f"ss_{s['student_id']}")
            if c3.button("Assign", key=f"assign_{s['student_id']}"):
                seat_id = conn.execute(f"SELECT seat_id FROM seats WHERE seat_label='{sel_seat}'").fetchone()[0]
                conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (seat_id,))
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (seat_id, s['student_id']))
                conn.commit()
                st.success("Assigned!")
                st.rerun()

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Expense")
            with st.form("exp"):
                cat = st.selectbox("Type", ["Electricity", "Rent", "Staff", "Other"])
                amt = st.number_input("Amount", step=100)
                if st.form_submit_button("Save"):
                    conn.execute("INSERT INTO expenses (category, amount, date) VALUES (?,?,?)", (cat, amt, date.today()))
                    conn.commit()
                    st.success("Saved")
        with c2:
            st.subheader("Net Profit")
            exps = pd.read_sql("SELECT sum(amount) FROM expenses", conn).iloc[0,0]
            st.metric("Total Expenses", f"₹{exps if exps else 0}")

    with tab4:
        st.subheader("Post Notice")
        txt = st.text_input("Message")
        if st.button("Post"):
            conn.execute("INSERT INTO notices (message, type, date) VALUES (?,?,?)", (txt, 'General', date.today()))
            conn.commit()
            st.success("Posted")

    with tab5:
        st.subheader("Seat Moves")
        reqs = pd.read_sql("SELECT * FROM seat_requests WHERE status='Pending'", conn)
        if reqs.empty: st.info("No requests")
        for _, r in reqs.iterrows():
            st.info(f"Student {r['student_id']} wants {r['requested_seat']} ({r['reason']})")
            if st.button("Approve", key=f"mv_{r['req_id']}"):
                conn.execute("UPDATE seat_requests SET status='Approved' WHERE req_id=?", (r['req_id'],))
                conn.commit()
                st.success("Approved")
                st.rerun()

# ==========================================
# 4. STUDENT DASHBOARD
# ==========================================
def show_student_dashboard(user):
    # Pass just the ID to check_lockout safely
    is_locked, msg = check_lockout(user[0])
    
    if is_locked:
        st.error(msg)
        st.stop()
        
    if "WARNING" in msg: st.warning(msg)

    st.title(f"🎓 Dashboard")
    
    # Notices
    conn = get_db()
    notices = pd.read_sql("SELECT message FROM notices ORDER BY id DESC LIMIT 1", conn)
    if not notices.empty: st.info(f"📢 {notices.iloc[0]['message']}")
    
    # ID Card
    seat_display = f"A-{user[9]}" if user[9] else "Pending"
    st.markdown(f"""
    <div style="background-color:#f0f2f6;padding:15px;border-radius:10px;border-left:5px solid #00C851;">
        <h3>🆔 S-MART ID</h3>
        <b>Name:</b> {user[1]}<br>
        <b>Phone:</b> {user[2]}<br>
        <b>Exam:</b> {user[4]}<br>
        <b>Seat:</b> {seat_display}
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # Seat Request
    with st.expander("Request Seat Change"):
        with st.form("move"):
            new_s = st.text_input("New Seat (e.g. B-5)")
            reason = st.selectbox("Reason", ["AC", "Noise", "Friend"])
            if st.form_submit_button("Send"):
                conn.execute("INSERT INTO seat_requests (student_id, current_seat, requested_seat, reason, status) VALUES (?,?,?,?,?)",
                             (user[0], seat_display, new_s, reason, 'Pending'))
                conn.commit()
                st.success("Sent")

    st.link_button("💬 Chat with Admin", f"https://wa.me/919999999999?text=Hi Admin, I am {user[1]}")

# ==========================================
# 5. MAIN ROUTER
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
        
        if menu == "🏠 Home":
            st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
            st.title("S-MART Library")
            st.success("Login to view map")
            
        elif menu == "📝 Join":
            st.header("Register")
            with st.form("reg"):
                name = st.text_input("Name")
                phone = st.text_input("Phone")
                pw = st.text_input("Password", type="password")
                exam = st.selectbox("Exam", ["UPSC", "NEET", "Other"])
                if st.form_submit_button("Submit"):
                    conn = get_db()
                    try:
                        conn.execute("INSERT INTO students (name, phone, password, exam, joining_date, mercy_days, status) VALUES (?,?,?,?,?,?,?)", 
                                     (name, phone, pw, exam, date.today(), 0, 'Pending'))
                        conn.commit()
                        st.success("Registered!")
                    except: st.error("Phone used")
                    
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
                    else: st.error("Wrong Admin Pass")
                else:
                    user = conn.execute("SELECT * FROM students WHERE phone=? AND password=?", (u,p)).fetchone()
                    if user:
                        if user[7] == 0: st.warning("Pending Approval")
                        else:
                            st.session_state['user'] = user
                            st.session_state['role'] = 'Student'
                            st.rerun()
                    else: st.error("User not found")

if __name__ == "__main__":
    main()

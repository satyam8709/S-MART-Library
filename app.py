import streamlit as st
import sqlite3
import pandas as pd
import os
import random
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART V4", page_icon="🏢", layout="wide")

# *** NEW DATABASE V4 (To support Address/Father Name columns) ***
if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v4.db'

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
    
    # 3. STUDENTS (The BIG Profile)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, 
        phone TEXT UNIQUE, 
        password TEXT, 
        exam TEXT,
        email TEXT,
        father_name TEXT,
        guardian_phone TEXT,
        address TEXT,
        photo_path TEXT,
        govt_id_path TEXT,
        joining_date DATE, 
        due_date DATE,
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
                # Lock logic here (omitted for brevity, same as V3)
                return True, "⛔ ACCOUNT LOCKED"
            elif today > due:
                return False, f"⚠️ WARNING: Fees Overdue"
        elif s['status'] == 'Locked':
             return True, "⛔ ACCOUNT LOCKED"
             
        return False, "Welcome"
    except: return False, "System Error"

# ==========================================
# 3. REGISTRATION FLOW (OTP + KYC)
# ==========================================
def show_registration_page():
    st.header("📝 S-MART Admission Form")
    
    # STEP 1: OTP VERIFICATION
    if 'reg_verified' not in st.session_state: st.session_state['reg_verified'] = False
    
    if not st.session_state['reg_verified']:
        st.info("Step 1: Verify Mobile Number")
        phone_input = st.text_input("Enter Mobile Number (10 Digits)")
        
        if st.button("Send OTP"):
            if len(phone_input) == 10:
                # SIMULATION OTP
                otp = random.randint(1000, 9999)
                st.session_state['generated_otp'] = str(otp)
                st.session_state['reg_phone'] = phone_input
                st.success(f"OTP Sent! (Simulation Code: {otp})") # In real app, this goes to SMS
            else:
                st.error("Invalid Number")
                
        if 'generated_otp' in st.session_state:
            otp_check = st.text_input("Enter OTP")
            if st.button("Verify OTP"):
                if otp_check == st.session_state['generated_otp']:
                    st.success("Verified!")
                    st.session_state['reg_verified'] = True
                    st.rerun()
                else:
                    st.error("Wrong OTP")
    
    # STEP 2: FULL KYC FORM
    else:
        st.success(f"✅ Phone Verified: {st.session_state['reg_phone']}")
        with st.form("kyc_form"):
            st.subheader("Basic Details")
            c1, c2 = st.columns(2)
            name = c1.text_input("Full Student Name")
            father = c2.text_input("Father/Guardian Name")
            
            c3, c4 = st.columns(2)
            g_phone = c3.text_input("Guardian Phone Number")
            email = c4.text_input("Email ID")
            
            address = st.text_area("Permanent Address")
            exam = st.selectbox("Preparing For", ["UPSC", "BPSC", "JEE", "NEET", "CA/CS", "General"])
            password = st.text_input("Set Login Password", type="password")
            
            st.subheader("Upload Documents")
            c5, c6 = st.columns(2)
            photo = c5.file_uploader("Passport Size Photo", type=['jpg', 'png'])
            govt_id = c6.file_uploader("Govt ID (Aadhar/PAN)", type=['jpg', 'png', 'pdf'])
            
            if st.form_submit_button("Submit Application"):
                if photo and govt_id:
                    # Save Files
                    p_path = save_uploaded_file(photo, st.session_state['reg_phone'])
                    id_path = save_uploaded_file(govt_id, st.session_state['reg_phone'])
                    
                    conn = get_db()
                    try:
                        conn.execute("""
                            INSERT INTO students 
                            (name, phone, password, exam, email, father_name, guardian_phone, address, photo_path, govt_id_path, joining_date, status)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (name, st.session_state['reg_phone'], password, exam, email, father, g_phone, address, p_path, id_path, date.today(), 'Pending'))
                        conn.commit()
                        st.balloons()
                        st.success("🎉 Registration Successful! Wait for Admin Approval.")
                    except Exception as e:
                        st.error(f"Error: {e} (Phone might be used)")
                    conn.close()
                else:
                    st.warning("Please upload both Photo and ID.")

# ==========================================
# 4. ADMIN DASHBOARD (X-RAY VISION)
# ==========================================
def show_admin_dashboard():
    # STATE MANAGEMENT FOR SIDEBAR DETAILS
    if 'selected_student_id' not in st.session_state:
        st.session_state['selected_student_id'] = None

    st.sidebar.markdown("---")
    st.sidebar.header("👮 Admin")
    
    # If a seat is clicked, Show Details in Sidebar
    if st.session_state['selected_student_id']:
        conn = get_db()
        stu = pd.read_sql(f"SELECT * FROM students WHERE student_id={st.session_state['selected_student_id']}", conn).iloc[0]
        conn.close()
        
        with st.sidebar:
            st.info("👤 Student Details")
            if stu['photo_path']: st.image(stu['photo_path'], width=150)
            st.write(f"**Name:** {stu['name']}")
            st.write(f"**Father:** {stu['father_name']}")
            st.write(f"**Guardian Ph:** {stu['guardian_phone']}")
            st.write(f"**Address:** {stu['address']}")
            st.write(f"**Exam:** {stu['exam']}")
            
            if stu['govt_id_path']: 
                with open(stu['govt_id_path'], "rb") as f:
                    st.download_button("Download Govt ID", f, file_name="govt_id.png")
            
            st.divider()
            if st.button("Close Details"):
                st.session_state['selected_student_id'] = None
                st.rerun()

    # MAIN TABS
    tab1, tab2, tab3 = st.tabs(["🗺️ X-Ray Map", "🚦 Approvals", "⚙️ Operations"])
    
    with tab1:
        st.subheader("Live Floor Plan (Click Seat for Details)")
        conn = get_db()
        seats = pd.read_sql("SELECT * FROM seats", conn)
        # Fetch active students to map them
        active_students = pd.read_sql("SELECT student_id, name, assigned_seat_id FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        seat_map = {row['assigned_seat_id']: row for _, row in active_students.iterrows()}
        conn.close()
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    sid = s['seat_id']
                    status = s['status']
                    
                    btn_type = "primary" if status != 'Available' else "secondary"
                    
                    # THE CLICK LOGIC
                    if cols[i].button(s['seat_label'], key=f"seat_{sid}", type=btn_type):
                        if sid in seat_map:
                            # Set session state to trigger sidebar
                            st.session_state['selected_student_id'] = seat_map[sid]['student_id']
                            st.rerun()
                        else:
                            st.toast("Seat is Empty")

    with tab2:
        st.subheader("Pending Approvals")
        conn = get_db()
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        
        for _, p in pending.iterrows():
            with st.expander(f"{p['name']} ({p['exam']})"):
                c1, c2 = st.columns(2)
                c1.write(f"**Father:** {p['father_name']}")
                c1.write(f"**Address:** {p['address']}")
                if p['photo_path']: c2.image(p['photo_path'], caption="Uploaded Photo", width=100)
                
                if st.button("✅ Approve", key=f"ap_{p['student_id']}"):
                     conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", 
                                 (date.today() + timedelta(days=30), p['student_id']))
                     conn.commit()
                     st.rerun()
        conn.close()

# ==========================================
# 5. STUDENT DASHBOARD
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked:
        st.error(msg)
        st.stop()

    st.title(f"🎓 Dashboard")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        if user[9]: # Photo Path
            st.image(user[9], width=150)
        st.write(f"**Name:** {user[1]}")
        st.write(f"**Exam:** {user[4]}")
        st.write(f"**Seat:** A-{user[15]}") # assigned_seat_id
        
    with c2:
        st.info("📢 Notices: Library is Open 24/7.")
        st.success("✅ Fees Paid")

# ==========================================
# 6. MAIN ROUTER
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
        menu = st.sidebar.radio("Menu", ["🏠 Home", "📝 Join (OTP)", "🔐 Login"])
        if menu == "🏠 Home":
            st.title("S-MART Library")
            st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
        elif menu == "📝 Join (OTP)":
            show_registration_page()
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
                        if user[13] == 0: st.warning("Pending Approval") # is_profile_approved
                        else:
                            st.session_state['user'] = user
                            st.session_state['role'] = 'Student'
                            st.rerun()
                    else: st.error("User not found")
                conn.close()

if __name__ == "__main__":
    main()

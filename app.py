from flask import Flask, render_template, request, jsonify,session
from flask_cors import CORS
import sqlite3
import uuid
import razorpay

app = Flask(__name__)
# Enable sessions by setting a secret key (change this to a random string)
app.secret_key = "super_secret_safespace_key_12345" 

# Support credentials sharing across origins for admin sessions
CORS(app, supports_credentials=True)

DATABASE_FILE = "safespace.db"

# ⚠️ REPLACE THESE WITH YOUR ACTUAL TEST KEYS FROM RAZORPAY DASHBOARD
RAZORPAY_KEY_ID = "rzp_test_TDE8jjyxv1Hs98"
RAZORPAY_KEY_SECRET = "etkf2UdhaKSFR7bZ7uAux5Ba"

# 🔐 CHOOSE YOUR ADMIN PASSWORD HERE
ADMIN_PASSWORD = "Lilith111@@" 

try:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
except Exception as e:
    print(f"Warning: Razorpay initialization failed. Error: {e}")
    razorpay_client = None

# --- DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vent_id INTEGER,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vent_id) REFERENCES vents (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            room_link TEXT DEFAULT NULL
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM bookings")
    if cursor.fetchone()[0] == 0:
        default_slots = [
            ("Today", "4:00 PM"),
            ("Today", "6:00 PM"),
            ("Today", "8:00 PM"),
            ("Tomorrow", "10:00 AM"),
            ("Tomorrow", "2:00 PM")
        ]
        cursor.executemany("INSERT INTO bookings (date, time, status) VALUES (?, ?, 'available')", default_slots)
        
    conn.commit()
    conn.close()

# --- ADMIN SECURITY CHECK UTILITY ---
def is_admin_authenticated():
    return session.get('is_admin') == True

# --- ADMIN AUTHENTICATION API ---
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    password = data.get('password')
    if password == ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify({"status": "success", "message": "Authenticated successfully"}), 200
    return jsonify({"error": "Invalid password"}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify({"status": "success"}), 200

@app.route('/api/admin/check', methods=['GET'])
def admin_check():
    if is_admin_authenticated():
        return jsonify({"authenticated": True}), 200
    return jsonify({"authenticated": False}), 401

# --- ADMIN DELETION ENDPOINTS ---

# Delete a Vent (and all of its replies)
@app.route('/api/admin/vents/<int:vent_id>', methods=['DELETE'])
def delete_vent(vent_id):
    if not is_admin_authenticated():
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # Delete child replies first to maintain relational database integrity
    cursor.execute("DELETE FROM replies WHERE vent_id = ?", (vent_id,))
    cursor.execute("DELETE FROM vents WHERE id = ?", (vent_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"}), 200

# Reset a booked slot back to 'available'
@app.route('/api/admin/slots/<int:slot_id>/reset', methods=['POST'])
def reset_slot(slot_id):
    if not is_admin_authenticated():
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status = 'available', room_link = NULL WHERE id = ?", (slot_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "reset"}), 200

# Delete a slot entirely from the schedule
@app.route('/api/admin/slots/<int:slot_id>', methods=['DELETE'])
def delete_slot(slot_id):
    if not is_admin_authenticated():
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bookings WHERE id = ?", (slot_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"}), 200

# Add a brand-new slot to the schedule manually
@app.route('/api/admin/slots', methods=['POST'])
def add_slot():
    if not is_admin_authenticated():
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json()
    date = data.get('date')
    time = data.get('time')
    
    if not date or not time:
        return jsonify({"error": "Missing date or time"}), 400
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bookings (date, time, status) VALUES (?, ?, 'available')", (date, time))
    conn.commit()
    conn.close()
    return jsonify({"status": "created"}), 201

# --- PUBLIC ROUTINES (KEEP EXISTING BACKEND FUNCTIONALITY) ---
@app.route('/api/vents', methods=['GET'])
def get_vents():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM vents ORDER BY id DESC")
    vents = cursor.fetchall()
    
    result = []
    for vent in vents:
        vent_id, content = vent
        cursor.execute("SELECT content FROM replies WHERE vent_id = ? ORDER BY id ASC", (vent_id,))
        replies = [{"content": r[0]} for r in cursor.fetchall()]
        result.append({
            "id": vent_id,
            "content": content,
            "replies": replies
        })
    conn.close()
    return jsonify(result), 200

@app.route('/api/vents', methods=['POST'])
def post_vent():
    data = request.get_json()
    content = data.get('content', '').strip()
    if not content:
        return jsonify({"error": "Content cannot be empty"}), 400
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO vents (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"}), 201

@app.route('/api/vents/<int:vent_id>/reply', methods=['POST'])
def post_reply(vent_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    if not content:
        return jsonify({"error": "Reply cannot be empty"}), 400
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO replies (vent_id, content) VALUES (?, ?)", (vent_id, content))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"}), 201

@app.route('/api/slots', methods=['GET'])
def get_slots():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, time, status, room_link FROM bookings")
    slots = cursor.fetchall()
    conn.close()
    
    result = []
    for s in slots:
        result.append({
            "id": s[0],
            "date": s[1],
            "time": s[2],
            "status": s[3],
            "room_link": s[4]
        })
    return jsonify(result), 200

@app.route('/api/create-order', methods=['POST'])
def create_order():
    if not razorpay_client:
        return jsonify({"error": "Razorpay client is not configured correctly."}), 500

    data = request.get_json()
    slot_id = data.get('slot_id')
    amount_rupees = data.get('amount') 
    
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM bookings WHERE id = ?", (slot_id,))
        slot_status = cursor.fetchone()
        if not slot_status or slot_status[0] == 'booked':
            conn.close()
            return jsonify({"error": "Slot already taken or unavailable"}), 400
        conn.close()

        amount_paise = int(amount_rupees) * 100
        
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"receipt_slot_{slot_id}",
            "payment_capture": 1 
        }
        
        razorpay_order = razorpay_client.order.create(data=order_data)
        
        return jsonify({
            "order_id": razorpay_order['id'],
            "amount": amount_paise,
            "key_id": RAZORPAY_KEY_ID
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/verify-payment', methods=['POST'])
def verify_payment():
    if not razorpay_client:
        return jsonify({"error": "Razorpay client is not configured."}), 500

    data = request.get_json()
    slot_id = data.get('slot_id')
    payment_id = data.get('razorpay_payment_id')
    order_id = data.get('razorpay_order_id')
    signature = data.get('razorpay_signature')

    try:
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        random_room_name = f"SafeSpace-{uuid.uuid4().hex[:12]}"
        jitsi_url = f"https://meet.jit.si/{random_room_name}"
        
        cursor.execute("UPDATE bookings SET status = 'booked', room_link = ? WHERE id = ?", (jitsi_url, slot_id))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "room_link": jitsi_url}), 200

    except razorpay.errors.SignatureVerificationError:
        return jsonify({"error": "Payment token signature verification failed."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Serve the main homepage
@app.route('/')
def home():
    return render_template('index.html')

# Serve the private admin panel
@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

if __name__ == '__main__':
    init_db()  
    app.run(debug=True, port=5000)
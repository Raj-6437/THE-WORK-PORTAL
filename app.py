from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import uuid
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure upload folders
UPLOAD_FOLDER = 'static/uploads'
PROFILE_PHOTOS_FOLDER = 'static/profile_photos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROFILE_PHOTOS_FOLDER'] = PROFILE_PHOTOS_FOLDER

# Create upload folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PHOTOS_FOLDER, exist_ok=True)

# Initialize SocketIO after app
socketio = SocketIO(app, cors_allowed_origins="*")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 email TEXT UNIQUE NOT NULL,
                 password TEXT NOT NULL,
                 phone TEXT,
                 dob TEXT,
                 profession TEXT,
                 education TEXT,
                 profile_photo TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Works table with all columns
    c.execute('''CREATE TABLE IF NOT EXISTS works
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 title TEXT NOT NULL,
                 description TEXT,
                 file_path TEXT,
                 user_id INTEGER NOT NULL,
                 category TEXT,
                 business_name TEXT,
                 contact_email TEXT,
                 budget REAL,
                 deadline TEXT,
                 duration INTEGER,
                 status TEXT DEFAULT 'open',
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Add missing columns if they don't exist
    c.execute("PRAGMA table_info(works)")
    columns = [col[1] for col in c.fetchall()]
    
    # List of columns to add
    columns_to_add = [
        ('business_name', 'TEXT'),
        ('contact_email', 'TEXT'),
        ('budget', 'REAL'),
        ('deadline', 'TEXT'),
        ('duration', 'INTEGER'),
        ('status', 'TEXT')
    ]
    
    for column, col_type in columns_to_add:
        if column not in columns:
            c.execute(f"ALTER TABLE works ADD COLUMN {column} {col_type}")
    
    # Bids table
    c.execute('''CREATE TABLE IF NOT EXISTS bids
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 work_id INTEGER NOT NULL,
                 user_id INTEGER NOT NULL,
                 amount REAL NOT NULL,
                 message TEXT,
                 status TEXT DEFAULT 'pending',  -- pending/accepted/rejected
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(work_id) REFERENCES works(id),
                 FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 sender_id INTEGER NOT NULL,
                 receiver_id INTEGER NOT NULL,
                 bid_id INTEGER NOT NULL,
                 message TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(sender_id) REFERENCES users(id),
                 FOREIGN KEY(receiver_id) REFERENCES users(id),
                 FOREIGN KEY(bid_id) REFERENCES bids(id))''')
    
    # Invoices table
    c.execute('''CREATE TABLE IF NOT EXISTS invoices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 work_id INTEGER NOT NULL,
                 bid_id INTEGER NOT NULL,
                 amount REAL NOT NULL,
                 status TEXT DEFAULT 'pending',  -- pending/paid
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(work_id) REFERENCES works(id),
                 FOREIGN KEY(bid_id) REFERENCES bids(id))''')
    
    # Notifications table
    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 message TEXT NOT NULL,
                 is_read BOOLEAN DEFAULT 0,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Payments table
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 invoice_id INTEGER NOT NULL,
                 amount REAL NOT NULL,
                 payment_type TEXT NOT NULL,  -- advance/full
                 status TEXT DEFAULT 'pending',  -- pending/completed
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(invoice_id) REFERENCES invoices(id))''')
    
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/profile_photos/<filename>')
def profile_photo(filename):
    return send_from_directory(app.config['PROFILE_PHOTOS_FOLDER'], filename)

# Landing Page Route - FIXED
@app.route('/')
def landing():
    return render_template('page.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

# Signup Route with Profile Photo and Phone
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        phone = request.form.get('phone', '')
        dob = request.form['dob']
        profession = request.form['profession']
        education = request.form['education']
        profile_photo = None
        
        # Handle profile photo upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file.filename != '' and allowed_file(file.filename):
                filename = f"{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}"
                filepath = os.path.join(app.config['PROFILE_PHOTOS_FOLDER'], filename)
                file.save(filepath)
                profile_photo = filename
        
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO users (username, email, password, phone, dob, profession, education, profile_photo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, email, password, phone, dob, profession, education, profile_photo))
            conn.commit()
            conn.close()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists', 'error')
    
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Get works from OTHER users for discover section
    works = conn.execute('''
        SELECT works.*, users.username, users.profile_photo 
        FROM works 
        JOIN users ON works.user_id = users.id
        WHERE works.user_id != ?
        ORDER BY works.created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    # Get ONLY current user's works for "My Work" section
    user_works = conn.execute('SELECT * FROM works WHERE user_id = ?', (session['user_id'],)).fetchall()
    
    # Get user's notifications including bid_id
    notifications = conn.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? AND is_read = 0
        ORDER BY created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    # Get invoices for both parties
    invoices = conn.execute('''
        SELECT invoices.*, works.title
        FROM invoices
        JOIN works ON invoices.work_id = works.id
        WHERE works.user_id = ? OR invoices.bid_id IN (
            SELECT id FROM bids WHERE user_id = ?
        )
    ''', (session['user_id'], session['user_id'])).fetchall()
    
    # Get bids for user's works
    bids = {}
    for work in user_works:
        work_bids = conn.execute('''
            SELECT bids.*, users.username 
            FROM bids 
            JOIN users ON bids.user_id = users.id
            WHERE work_id = ?
        ''', (work['id'],)).fetchall()
        bids[work['id']] = work_bids
    
    conn.close()
    
    return render_template('dashboard.html', user=user, works=works, 
                           user_works=user_works, notifications=notifications,
                           invoices=invoices, bids=bids)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

@app.route('/upload_work', methods=['POST'])
def upload_work():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['work-title']
        description = request.form['work-description']
        category = request.form.get('category', 'Other')
        files = request.files.getlist('work-files')
        file_paths = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = f"{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                file_paths.append(filename)
        # New fields
        business_name = request.form.get('business-name', '')
        contact_email = request.form.get('contact-email', '')
        budget = request.form.get('budget', None)
        deadline = request.form.get('deadline', None)
        duration = request.form.get('duration', None)
        
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO works (title, description, file_path, user_id, category, 
                                  business_name, contact_email, budget, deadline, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, description, ','.join(file_paths), session['user_id'], category,
                  business_name, contact_email, budget, deadline, duration))
            conn.commit()
            conn.close()
            flash('Work uploaded successfully!', 'success')
        except Exception as e:
            flash(f'Error uploading work: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

def create_notification(user_id, message, bid_id=None):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO notifications (user_id, message, bid_id)
        VALUES (?, ?, ?)
    ''', (user_id, message, bid_id))
    conn.commit()
    conn.close()

@app.route('/submit_bid', methods=['POST'])
def submit_bid():
    if 'user_id' not in session:
        flash('Please login to place bids', 'error')
        return redirect(url_for('login'))

    work_id = request.form['work_id']
    amount = float(request.form['amount'])
    message = request.form.get('message', '')

    try:
        conn = get_db_connection()
        # Insert bid into database
        conn.execute('''
            INSERT INTO bids (work_id, user_id, amount, message)
            VALUES (?, ?, ?, ?)
        ''', (work_id, session['user_id'], amount, message))
        bid_id = conn.execute('SELECT last_insert_rowid() as id').fetchone()['id']

        # Notify work owner
        work_row = conn.execute('SELECT user_id, title FROM works WHERE id = ?', (work_id,)).fetchone()
        work_owner = work_row['user_id']
        work_title = work_row['title']
        create_notification(work_owner, f"New bid of ${amount} on your work '{work_title}'!", bid_id)

        conn.commit()
        conn.close()

        # Live update: emit new bid event to work owner if online
        socketio.emit('new_bid', {
            'work_id': work_id,
            'bid_id': bid_id,
            'amount': amount,
            'message': message,
            'bidder_id': session['user_id'],
            'work_owner': work_owner
        }, room=f'user_{work_owner}')

        flash('Bid submitted successfully!', 'success')
    except Exception as e:
        flash(f'Error submitting bid: {str(e)}', 'error')

    return redirect(url_for('dashboard'))

@app.route('/get_invoice_details/<int:invoice_id>')
def get_invoice_details(invoice_id):
    conn = get_db_connection()
    invoice = conn.execute('''
        SELECT invoices.*, works.title, users.username AS freelancer_name
        FROM invoices
        JOIN works ON invoices.work_id = works.id
        JOIN bids ON invoices.bid_id = bids.id
        JOIN users ON bids.user_id = users.id
        WHERE invoices.id = ?
    ''', (invoice_id,)).fetchone()
    conn.close()
    
    if invoice:
        return jsonify(dict(invoice))
    return jsonify({'error': 'Invoice not found'}), 404

@app.route('/get_bidder_info/<int:bid_id>')
def get_bidder_info(bid_id):
    conn = get_db_connection()
    bid = conn.execute('''
        SELECT bids.*, users.username, users.email, users.phone, users.profession
        FROM bids
        JOIN users ON bids.user_id = users.id
        WHERE bids.id = ?
    ''', (bid_id,)).fetchone()
    conn.close()
    
    if bid:
        return jsonify(dict(bid))
    return jsonify({'error': 'Bid not found'}), 404

@app.route('/confirm_bid', methods=['POST'])
def confirm_bid():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.json
    bid_id = data['bid_id']
    final_amount = data['final_amount']
    payment_method = data['payment_method']

    try:
        conn = get_db_connection()

        # Update bid status and final amount
        conn.execute('UPDATE bids SET status = "accepted", final_amount = ? WHERE id = ?', 
                    (final_amount, bid_id))

        # Get bid and work info
        bid = conn.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
        work = conn.execute('SELECT * FROM works WHERE id = ?', (bid['work_id'],)).fetchone()

        # Create invoice
        conn.execute('''
            INSERT INTO invoices (work_id, bid_id, amount, payment_method, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (work['id'], bid_id, final_amount, payment_method))

        # Notify freelancer
        notification_msg = (f"Your bid on '{work['title']}' has been accepted! "
                           f"Final amount: ${final_amount}. Payment method: {payment_method}")
        create_notification(bid['user_id'], notification_msg)

        # Create initial message with payment details
        payment_details = (f"Your bid has been accepted!\n\n"
                          f"Final Amount: ${final_amount}\n"
                          f"Payment Method: {payment_method}\n\n"
                          f"Please provide your payment details to receive funds.")

        conn.execute('''
            INSERT INTO messages (sender_id, receiver_id, bid_id, message)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], bid['user_id'], bid_id, payment_details))

        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    receiver_id = request.form['receiver_id']
    bid_id = request.form['bid_id']
    message = request.form['message']
    
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO messages (sender_id, receiver_id, bid_id, message)
        VALUES (?, ?, ?, ?)
    ''', (session['user_id'], receiver_id, bid_id, message))
    
    # Create notification for receiver
    sender = conn.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    notification_msg = f"New message from {sender['username']}"
    conn.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', 
                (receiver_id, notification_msg))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/get_messages/<int:bid_id>')
def get_messages(bid_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    messages = conn.execute('''
        SELECT messages.*, users.username, users.profile_photo
        FROM messages
        JOIN users ON messages.sender_id = users.id
        WHERE bid_id = ?
        ORDER BY created_at ASC
    ''', (bid_id,)).fetchall()
    
    # Mark messages as read
    conn.execute('UPDATE notifications SET is_read = 1 WHERE message LIKE ? AND user_id = ?', 
                (f"%message from%", session['user_id']))
    conn.commit()
    
    conn.close()
    return jsonify([dict(msg) for msg in messages])

@app.route('/mark_notification_read/<int:notif_id>')
def mark_notification_read(notif_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notif_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/get_conversations')
def get_conversations():
    if 'user_id' not in session:
        return jsonify([])
    
    conn = get_db_connection()
    user_id = session['user_id']
    
    # Get all bids where user is involved
    conversations = conn.execute('''
        SELECT bids.id AS bid_id, works.title AS work_title,
               CASE 
                   WHEN bids.user_id = ? THEN works.user_id
                   ELSE bids.user_id
               END AS partner_id,
               MAX(messages.created_at) AS last_message_time
        FROM bids
        JOIN works ON bids.work_id = works.id
        LEFT JOIN messages ON messages.bid_id = bids.id
        WHERE bids.user_id = ? OR works.user_id = ?
        GROUP BY bids.id
        ORDER BY last_message_time DESC
    ''', (user_id, user_id, user_id)).fetchall()
    
    result = []
    for conv in conversations:
        partner = conn.execute('SELECT username, profile_photo FROM users WHERE id = ?', 
                              (conv['partner_id'],)).fetchone()
        
        last_message = conn.execute('''
            SELECT message FROM messages 
            WHERE bid_id = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        ''', (conv['bid_id'],)).fetchone()
        
        result.append({
            'bid_id': conv['bid_id'],
            'work_title': conv['work_title'],
            'partner_id': conv['partner_id'],
            'partner_name': partner['username'] if partner else '',
            'partner_photo': partner['profile_photo'] if partner else '',
            'last_message': last_message['message'] if last_message else None
        })
    
    conn.close()
    return jsonify(result)

@app.route('/get_work_details/<int:work_id>')
def get_work_details(work_id):
    conn = get_db_connection()
    work = conn.execute('SELECT * FROM works WHERE id = ?', (work_id,)).fetchone()
    conn.close()
    
    if work:
        return jsonify(dict(work))
    return jsonify({'error': 'Work not found'}), 404

# Add before app.run
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        emit('connection_response', {'data': 'Connected'}, room=request.sid)

@socketio.on('join_chat')
def handle_join_chat(data):
    bid_id = data['bid_id']
    if 'user_id' in session:
        join_room(f'bid_{bid_id}')
        emit('status', {'msg': f'Joined chat for bid {bid_id}'}, room=request.sid)

@socketio.on('send_message')
def handle_send_message(data):
    bid_id = data['bid_id']
    message = data['message']
    sender_id = session['user_id']
    
    conn = get_db_connection()
    # Get receiver ID (opposite user in the bid)
    bid = conn.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
    work = conn.execute('SELECT * FROM works WHERE id = ?', (bid['work_id'],)).fetchone()
    
    if sender_id == bid['user_id']:
        receiver_id = work['user_id']
    else:
        receiver_id = bid['user_id']
    
    # Save to database
    conn.execute('''
        INSERT INTO messages (sender_id, receiver_id, bid_id, message)
        VALUES (?, ?, ?, ?)
    ''', (sender_id, receiver_id, bid_id, message))
    conn.commit()
    
    # Get sender info
    sender = conn.execute('SELECT username, profile_photo FROM users WHERE id = ?', (sender_id,)).fetchone()
    conn.close()
    
    # Broadcast to room
    emit('new_message', {
        'sender_id': sender_id,
        'sender_name': sender['username'],
        'profile_photo': sender['profile_photo'],
        'message': message,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M")
    }, room=f'bid_{bid_id}')

@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.json
    invoice_id = data['invoice_id']
    payment_type = data['payment_type']  # 'advance' or 'full'
    amount = data['amount']
    
    try:
        conn = get_db_connection()
        # Get invoice details
        invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
        
        if not invoice:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        
        # Update invoice status
        new_status = 'partially_paid' if payment_type == 'advance' else 'paid'
        conn.execute('UPDATE invoices SET status = ?, amount_paid = ? WHERE id = ?',
                    (new_status, amount, invoice_id))
        
        # Create payment record
        conn.execute('''
            INSERT INTO payments (invoice_id, amount, payment_type, status)
            VALUES (?, ?, ?, 'completed')
        ''', (invoice_id, amount, payment_type))
        
        # Notify both parties
        work = conn.execute('SELECT * FROM works WHERE id = ?', (invoice['work_id'],)).fetchone()
        bid = conn.execute('SELECT * FROM bids WHERE id = ?', (invoice['bid_id'],)).fetchone()
        
        # Notification for freelancer
        freelancer_msg = f"Payment of ${amount} ({payment_type}) received for work '{work['title']}'"
        conn.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', 
                    (bid['user_id'], freelancer_msg))
        
        # Notification for client
        client_msg = f"Payment of ${amount} ({payment_type}) processed for work '{work['title']}'"
        conn.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', 
                    (work['user_id'], client_msg))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/accept_bid/<int:bid_id>', methods=['POST'])
def accept_bid(bid_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        # Get bid details
        bid = conn.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
        if not bid:
            return jsonify({'success': False, 'error': 'Bid not found'}), 404

        # Get work details
        work = conn.execute('SELECT * FROM works WHERE id = ?', (bid['work_id'],)).fetchone()
        if work['user_id'] != session['user_id']:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        # Update bid status to accepted
        conn.execute('UPDATE bids SET status = "accepted" WHERE id = ?', (bid_id,))

        # Create invoice
        conn.execute('''
            INSERT INTO invoices (work_id, bid_id, amount, status, created_at)
            VALUES (?, ?, ?, 'pending', datetime('now'))
        ''', (work['id'], bid_id, bid['amount']))
        invoice_id = conn.execute('SELECT last_insert_rowid() AS id').fetchone()['id']

        # Notify freelancer
        notification_msg = f"Your bid for '{work['title']}' has been accepted! Invoice #{invoice_id} generated."
        conn.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', 
                    (bid['user_id'], notification_msg))

        # Create initial message
        conn.execute('''
            INSERT INTO messages (sender_id, receiver_id, bid_id, message)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], bid['user_id'], bid_id, 
              f"Your bid has been accepted! We've generated invoice #{invoice_id} for ${bid['amount']}. Let's discuss project details."))

        conn.commit()
        conn.close()

        # Live update: emit invoice and bid status update to freelancer if online
        socketio.emit('bid_accepted', {
            'bid_id': bid_id,
            'invoice_id': invoice_id,
            'amount': bid['amount'],
            'work_title': work['title'],
            'client_id': session['user_id'],
            'freelancer_id': bid['user_id']
        }, room=f'user_{bid['user_id']}')

        return jsonify({'success': True, 'invoice_id': invoice_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/get_user_invoices')
def get_user_invoices():
    if 'user_id' not in session:
        return jsonify([])
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    invoices = conn.execute('''
        SELECT invoices.*, works.title, 
               client.username AS client_name,
               freelancer.username AS freelancer_name
        FROM invoices
        JOIN works ON invoices.work_id = works.id
        JOIN bids ON invoices.bid_id = bids.id
        JOIN users AS client ON works.user_id = client.id
        JOIN users AS freelancer ON bids.user_id = freelancer.id
        WHERE works.user_id = ? OR bids.user_id = ?
    ''', (user_id, user_id)).fetchall()
    
    conn.close()
    return jsonify([dict(invoice) for invoice in invoices])

# SocketIO: Join user-specific room for live updates
@socketio.on('join_user_room')
def join_user_room(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f'user_{user_id}')

if __name__ == '__main__':
    socketio.run(app, debug=True)
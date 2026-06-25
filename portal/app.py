import os
import uuid
import logging
import psycopg2
import random
import datetime as dt
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import boto3
from botocore.client import Config as BotoConfig
from clickhouse_driver import Client as ClickHouseClient
from werkzeug.security import generate_password_hash, check_password_hash
import docker

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SUPERSET_SECRET_KEY", "portal-very-secret-key-12345")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB limit for multiple files

# Retrieve S3, ClickHouse, PostgreSQL environment variables
RUSTFS_ENDPOINT_URL = os.getenv("RUSTFS_ENDPOINT_URL", "http://rustfs:9000")
RUSTFS_ACCESS_KEY = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
RUSTFS_SECRET_KEY = os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin")
RUSTFS_BRONZE_BUCKET = os.getenv("RUSTFS_BRONZE_BUCKET", "bronze")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "analytics")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "dlh-postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "datalakehouse")
POSTGRES_USER = os.getenv("POSTGRES_USER", "dlh_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# External ports for dashboard links
DLH_SUPERSET_PORT = os.getenv("DLH_SUPERSET_PORT", "28088")
DLH_GRAFANA_PORT = os.getenv("DLH_GRAFANA_PORT", "23001")
DLH_CLOUDBEAVER_PORT = os.getenv("DLH_CLOUDBEAVER_PORT", "28978")

def get_db_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

def init_db():
    import time
    conn = None
    retries = 12
    while retries > 0:
        try:
            logger.info("Connecting to PostgreSQL...")
            conn = get_db_connection()
            break
        except Exception as e:
            logger.warning(f"PostgreSQL not ready yet, retrying in 4s... ({e})")
            time.sleep(4)
            retries -= 1
            
    if not conn:
        logger.error("ERROR: Failed to connect to PostgreSQL after multiple retries. Database initialization failed.")
        return

    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS portal_users (
                username VARCHAR(50) PRIMARY KEY,
                password VARCHAR(256) NOT NULL,
                role VARCHAR(20) NOT NULL,
                first_login BOOLEAN DEFAULT TRUE,
                passcode VARCHAR(10),
                passcode_expiry TIMESTAMP
            )
        """)
        
        # Check if admin user exists, if not create default admin/admin
        c.execute("SELECT * FROM portal_users WHERE role = 'admin'")
        if not c.fetchone():
            hashed_pass = generate_password_hash("admin")
            c.execute(
                "INSERT INTO portal_users (username, password, role, first_login) VALUES (%s, %s, 'admin', TRUE)",
                ("admin", hashed_pass)
            )
            logger.info("Default admin user created in PostgreSQL: admin/admin")
        conn.commit()
        c.close()
        conn.close()
    except Exception as e:
        logger.error(f"ERROR initializing database tables: {e}")

init_db()

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=RUSTFS_ENDPOINT_URL,
        aws_access_key_id=RUSTFS_ACCESS_KEY,
        aws_secret_access_key=RUSTFS_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

def get_ch_client():
    return ClickHouseClient(
        host=CLICKHOUSE_HOST,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=CLICKHOUSE_DB,
        connect_timeout=10
    )

# Decorators for auth
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        # If user must change password, redirect them (unless logout or change endpoint itself)
        if session.get('first_login'):
            if request.endpoint not in ['change_password_force', 'logout']:
                return redirect(url_for('change_password_force'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({"status": "error", "message": "Quyền truy cập bị từ chối: Chỉ có Admin mới có quyền thực hiện hành động này"}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        if session.get('first_login'):
            return redirect(url_for('change_password_force'))
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT username, password, role, first_login FROM portal_users WHERE username = %s", (username,))
            user = c.fetchone()
            c.close()
            conn.close()
            
            if user and check_password_hash(user[1], password):
                session['username'] = user[0]
                session['role'] = user[2]
                session['first_login'] = user[3]
                logger.info(f"User logged in: {username} ({user[2]})")
                
                if user[3]:
                    return redirect(url_for('change_password_force'))
                return redirect(url_for('index'))
            else:
                error = "Tài khoản hoặc mật khẩu không hợp lệ"
        except Exception as e:
            logger.error(f"Login database connection error: {e}")
            error = f"Lỗi kết nối cơ sở dữ liệu: {e}"
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    username = session.pop('username', None)
    session.pop('role', None)
    session.pop('first_login', None)
    if username:
        logger.info(f"User logged out: {username}")
    return redirect(url_for('login'))

@app.route('/change-password-force', methods=['GET', 'POST'])
def change_password_force():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    error = None
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            error = "Mật khẩu xác nhận không khớp"
        elif len(new_password) < 5:
            error = "Mật khẩu phải từ 5 ký tự trở lên"
        else:
            username = session['username']
            hashed = generate_password_hash(new_password)
            try:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    "UPDATE portal_users SET password = %s, first_login = FALSE WHERE username = %s",
                    (hashed, username)
                )
                conn.commit()
                c.close()
                conn.close()
                
                session['first_login'] = False
                logger.info(f"User {username} changed password on first login.")
                return redirect(url_for('index'))
            except Exception as e:
                error = f"Lỗi hệ thống: {e}"
                
    return render_template('change_password_force.html', error=error)

@app.route('/change-password-self', methods=['POST'])
@login_required
def change_password_self():
    data = request.json or {}
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    username = session['username']

    if not old_password or not new_password:
        return jsonify({"status": "error", "message": "Yêu cầu cung cấp đầy đủ thông tin"}), 400

    if len(new_password) < 5:
        return jsonify({"status": "error", "message": "Mật khẩu mới phải từ 5 ký tự trở lên"}), 400

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT password FROM portal_users WHERE username = %s", (username,))
        row = c.fetchone()
        
        if not row or not check_password_hash(row[0], old_password):
            c.close()
            conn.close()
            return jsonify({"status": "error", "message": "Mật khẩu cũ không chính xác"}), 400
            
        hashed = generate_password_hash(new_password)
        c.execute("UPDATE portal_users SET password = %s WHERE username = %s", (hashed, username))
        conn.commit()
        c.close()
        conn.close()
        
        logger.info(f"User {username} changed password via settings page.")
        return jsonify({"status": "success", "message": "Đã đổi mật khẩu thành công."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi: {e}"}), 500

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT username FROM portal_users WHERE username = %s", (username,))
            user = c.fetchone()
            
            if not user:
                c.close()
                conn.close()
                return render_template('forgot_password.html', error="Tên đăng nhập không tồn tại")
                
            # Generate 6-digit numeric passcode
            passcode = "".join([str(random.randint(0, 9)) for _ in range(6)])
            expiry = dt.datetime.now() + dt.timedelta(minutes=10)
            
            c.execute(
                "UPDATE portal_users SET passcode = %s, passcode_expiry = %s WHERE username = %s",
                (passcode, expiry, username)
            )
            conn.commit()
            c.close()
            conn.close()
            
            # Print passcode in container logs (IT will see this or users check logs)
            logger.info("\n" + "="*85 + f"\n[FORGOT PASSWORD REQUEST]\nUser: {username}\nVERIFICATION PASSCODE: {passcode}\nExpires at: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n" + "="*85 + "\n")
            
            return redirect(url_for('reset_password', username=username))
            
        except Exception as e:
            return render_template('forgot_password.html', error=f"Lỗi kết nối cơ sở dữ liệu: {e}")
            
    return render_template('forgot_password.html', error=None)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    username = request.args.get('username') or request.form.get('username')
    
    if request.method == 'POST':
        passcode = request.form.get('passcode')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            return render_template('reset_password.html', username=username, error="Mật khẩu xác nhận không khớp")
        if len(new_password) < 5:
            return render_template('reset_password.html', username=username, error="Mật khẩu mới phải từ 5 ký tự trở lên")
            
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT passcode, passcode_expiry FROM portal_users WHERE username = %s", (username,))
            row = c.fetchone()
            
            if not row:
                c.close()
                conn.close()
                return render_template('reset_password.html', username=username, error="Người dùng không hợp lệ")
                
            db_passcode, db_expiry = row[0], row[1]
            
            if not db_passcode or db_passcode != passcode:
                c.close()
                conn.close()
                return render_template('reset_password.html', username=username, error="Mã xác thực (passcode) không khớp")
                
            if db_expiry < dt.datetime.now():
                c.close()
                conn.close()
                return render_template('reset_password.html', username=username, error="Mã xác thực đã hết hạn (hiệu lực trong 10 phút)")
                
            hashed = generate_password_hash(new_password)
            c.execute(
                "UPDATE portal_users SET password = %s, first_login = FALSE, passcode = NULL, passcode_expiry = NULL WHERE username = %s",
                (hashed, username)
            )
            conn.commit()
            c.close()
            conn.close()
            
            logger.info(f"SUCCESS: Reset password via passcode verification for user: {username}")
            return render_template('login.html', error="Đã khôi phục mật khẩu thành công. Vui lòng đăng nhập lại.")
            
        except Exception as e:
            return render_template('reset_password.html', username=username, error=f"Lỗi: {e}")
            
    return render_template('reset_password.html', username=username, error=None)

@app.route('/')
@login_required
def index():
    return render_template(
        'index.html',
        username=session.get('username'),
        role=session.get('role'),
        superset_port=DLH_SUPERSET_PORT,
        grafana_port=DLH_GRAFANA_PORT,
        cloudbeaver_port=DLH_CLOUDBEAVER_PORT
    )

@app.route('/upload', methods=['POST'])
@login_required
def upload_files():
    if 'files' not in request.files:
        return jsonify({"status": "error", "message": "Không tìm thấy tệp tải lên"}), 400
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"status": "error", "message": "Chưa chọn tệp"}), 400

    uploaded_files = []
    errors = []
    s3 = get_s3_client()

    for file in files:
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in ['.csv', '.xlsx']:
            errors.append(f"Tệp '{filename}' không hợp lệ: Chỉ hỗ trợ tệp .csv hoặc .xlsx")
            continue

        try:
            if ext == '.csv':
                s_key = f"csv_upload/{filename}"
            else:
                s_key = f"excel_uploads/{filename}"

            logger.info(f"Uploading {filename} to s3://{RUSTFS_BRONZE_BUCKET}/{s_key}")
            
            file_bytes = file.read()
            s3.put_object(
                Bucket=RUSTFS_BRONZE_BUCKET,
                Key=s_key,
                Body=file_bytes
            )
            uploaded_files.append(filename)
        except Exception as e:
            errors.append(f"Không thể tải tệp '{filename}': {str(e)}")

    if not uploaded_files:
        return jsonify({"status": "error", "message": "Không có tệp nào được tải lên", "errors": errors}), 400

    msg = f"Đã tải lên thành công {len(uploaded_files)} tệp vào Data Lake."
    if errors:
        msg += f" Có {len(errors)} tệp bị lỗi."

    return jsonify({
        "status": "success" if not errors else "warning",
        "message": msg,
        "uploaded": uploaded_files,
        "errors": errors
    })

@app.route('/files', methods=['GET'])
@login_required
def list_files():
    from zoneinfo import ZoneInfo
    local_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    try:
        s3 = get_s3_client()
        files = []
        
        # List Excel files
        try:
            excel_res = s3.list_objects_v2(Bucket=RUSTFS_BRONZE_BUCKET, Prefix="excel_uploads/")
            for obj in excel_res.get('Contents', []):
                if obj['Key'] != "excel_uploads/" and obj['Size'] > 0:
                    local_dt = obj['LastModified'].astimezone(local_tz)
                    files.append({
                        "key": obj['Key'],
                        "filename": os.path.basename(obj['Key']),
                        "type": "Excel",
                        "size_bytes": obj['Size'],
                        "last_modified": local_dt.strftime("%Y-%m-%d %H:%M:%S")
                    })
        except Exception as e:
            logger.warning(f"Could not list excel files: {e}")

        # List CSV files
        try:
            csv_res = s3.list_objects_v2(Bucket=RUSTFS_BRONZE_BUCKET, Prefix="csv_upload/")
            for obj in csv_res.get('Contents', []):
                if obj['Key'] != "csv_upload/" and obj['Size'] > 0:
                    local_dt = obj['LastModified'].astimezone(local_tz)
                    files.append({
                        "key": obj['Key'],
                        "filename": os.path.basename(obj['Key']),
                        "type": "CSV",
                        "size_bytes": obj['Size'],
                        "last_modified": local_dt.strftime("%Y-%m-%d %H:%M:%S")
                    })
        except Exception as e:
            logger.warning(f"Could not list csv files: {e}")
            
        files.sort(key=lambda x: x['last_modified'], reverse=True)
        return jsonify(files)
    except Exception as e:
        logger.error(f"Failed to list S3 files: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/delete-files', methods=['POST'])
@login_required
def delete_files():
    data = request.json or {}
    keys = data.get('keys', [])
    if not keys:
        return jsonify({"status": "error", "message": "Không có tệp nào được chọn để xóa"}), 400
    try:
        s3 = get_s3_client()
        for key in keys:
            logger.info(f"Deleting object from S3: {key}")
            s3.delete_object(Bucket=RUSTFS_BRONZE_BUCKET, Key=key)
        return jsonify({"status": "success", "message": f"Đã xóa thành công {len(keys)} tệp tin."})
    except Exception as e:
        logger.error(f"Failed to delete files: {e}")
        return jsonify({"status": "error", "message": f"Không thể xóa tệp: {str(e)}"}), 500

@app.route('/run-etl', methods=['POST'])
@admin_required
def run_etl():
    data = request.json or {}
    pipeline_name = data.get('pipeline')
    
    if pipeline_name not in ['etl_excel_to_lakehouse', 'etl_csv_upload_to_reporting']:
        return jsonify({"status": "error", "message": "Tên tiến trình ETL không hợp lệ"}), 400

    try:
        logger.info(f"Connecting to docker daemon to run Mage pipeline: {pipeline_name}")
        docker_client = docker.from_env()
        mage_container = docker_client.containers.get('dlh-mage')
        
        cmd = f"mage run /home/src {pipeline_name}"
        logger.info(f"Running command in dlh-mage: {cmd}")
        mage_container.exec_run(cmd, detach=True)
        
        return jsonify({
            "status": "success", 
            "message": f"Đã kích hoạt thủ công tiến trình ETL ({pipeline_name}) thành công."
        })
    except Exception as e:
        logger.error(f"Failed to run Mage pipeline: {e}")
        return jsonify({"status": "error", "message": f"Lỗi kích hoạt tiến trình: {str(e)}"}), 500

# User Management endpoints
@app.route('/users', methods=['GET', 'POST'])
@admin_required
def manage_users():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        if request.method == 'POST':
            data = request.json or {}
            username = data.get('username')
            password = data.get('password')
            role = data.get('role', 'staff')
            
            if not username or not password:
                c.close()
                conn.close()
                return jsonify({"status": "error", "message": "Thiếu thông tin người dùng"}), 400
                
            hashed_pass = generate_password_hash(password)
            try:
                c.execute(
                    "INSERT INTO portal_users (username, password, role, first_login) VALUES (%s, %s, %s, TRUE)", 
                    (username, hashed_pass, role)
                )
                conn.commit()
                c.close()
                conn.close()
                return jsonify({"status": "success", "message": f"Đã tạo người dùng '{username}' thành công."})
            except psycopg2.IntegrityError:
                c.close()
                conn.close()
                return jsonify({"status": "error", "message": f"Tên đăng nhập '{username}' đã tồn tại."}), 400
                
        c.execute("SELECT username, role, first_login FROM portal_users")
        rows = c.fetchall()
        users_list = []
        for r in rows:
            users_list.append({"username": r[0], "role": r[1], "first_login": r[2]})
        c.close()
        conn.close()
        return jsonify(users_list)
    except Exception as e:
        logger.error(f"Failed to manage users: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/users/delete', methods=['POST'])
@admin_required
def delete_user():
    data = request.json or {}
    username = data.get('username')
    
    if not username:
        return jsonify({"status": "error", "message": "Thiếu tên người dùng"}), 400
        
    if username == session.get('username'):
        return jsonify({"status": "error", "message": "Không thể tự xóa tài khoản của chính mình"}), 400
        
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM portal_users WHERE username = %s", (username,))
        conn.commit()
        c.close()
        conn.close()
        return jsonify({"status": "success", "message": f"Đã xóa người dùng '{username}' thành công."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/users/change-password', methods=['POST'])
@admin_required
def admin_change_user_password():
    data = request.json or {}
    target_username = data.get('username')
    new_password = data.get('new_password')
    
    if not target_username or not new_password:
        return jsonify({"status": "error", "message": "Thiếu thông tin yêu cầu"}), 400
        
    if len(new_password) < 5:
        return jsonify({"status": "error", "message": "Mật khẩu mới phải từ 5 ký tự trở lên"}), 400
        
    try:
        conn = get_db_connection()
        c = conn.cursor()
        hashed = generate_password_hash(new_password)
        # We do NOT force first_login = TRUE anymore, only new accounts get forced first login.
        c.execute("UPDATE portal_users SET password = %s, first_login = FALSE WHERE username = %s", (hashed, target_username))
        conn.commit()
        c.close()
        conn.close()
        
        logger.info(f"Admin {session.get('username')} reset password for user {target_username}.")
        return jsonify({"status": "success", "message": f"Đã đổi mật khẩu cho user '{target_username}' thành công."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/history', methods=['GET'])
@login_required
def upload_history():
    from zoneinfo import ZoneInfo
    local_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    history = []
    try:
        ch = get_ch_client()
        
        csv_query = """
        SELECT source_key, etag, source_size, status, row_count, processed_at, error_message
        FROM analytics.csv_upload_events
        ORDER BY processed_at DESC
        LIMIT 10
        """
        try:
            csv_rows = ch.execute(csv_query)
            for row in csv_rows:
                proc_dt = row[5]
                if proc_dt:
                    if proc_dt.tzinfo:
                        proc_dt = proc_dt.astimezone(local_tz)
                    proc_str = proc_dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    proc_str = ""
                history.append({
                    "filename": os.path.basename(row[0]),
                    "type": "CSV",
                    "size_bytes": row[2],
                    "status": row[3],
                    "rows": row[4],
                    "processed_at": proc_str,
                    "error": row[6] or ""
                })
        except Exception as e:
            logger.warning(f"Could not fetch CSV upload history: {e}")

        excel_query = """
        SELECT source_key, etag, source_size, status, row_count, processed_at, error_message
        FROM analytics.excel_upload_events
        ORDER BY processed_at DESC
        LIMIT 10
        """
        try:
            excel_rows = ch.execute(excel_query)
            for row in excel_rows:
                proc_dt = row[5]
                if proc_dt:
                    if proc_dt.tzinfo:
                        proc_dt = proc_dt.astimezone(local_tz)
                    proc_str = proc_dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    proc_str = ""
                history.append({
                    "filename": os.path.basename(row[0]),
                    "type": "Excel",
                    "size_bytes": row[2],
                    "status": row[3],
                    "rows": row[4],
                    "processed_at": proc_str,
                    "error": row[6] or ""
                })
        except Exception as e:
            logger.warning(f"Could not fetch Excel upload history: {e}")

        history.sort(key=lambda x: x["processed_at"], reverse=True)
        history = history[:15]

    except Exception as e:
        logger.error(f"Failed to fetch upload history from ClickHouse: {e}")
        
    return jsonify(history)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)

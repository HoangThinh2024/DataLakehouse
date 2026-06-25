import sys
import os
import argparse
import psycopg2
from werkzeug.security import generate_password_hash

def main():
    parser = argparse.ArgumentParser(description="IT Password Reset Script for DataLakehouse Portal")
    parser.add_argument("--username", required=True, help="Username to reset")
    parser.add_argument("--password", required=True, help="New password")
    args = parser.parse_args()

    host = os.getenv("POSTGRES_HOST", "dlh-postgres")
    db = os.getenv("POSTGRES_DB", "datalakehouse")
    user = os.getenv("POSTGRES_USER", "dlh_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    try:
        conn = psycopg2.connect(
            host=host,
            database=db,
            user=user,
            password=password
        )
        c = conn.cursor()
        hashed = generate_password_hash(args.password)
        
        # Check if user exists
        c.execute("SELECT * FROM portal_users WHERE username = %s", (args.username,))
        row = c.fetchone()
        if not row:
            # Create user as admin by default if they don't exist
            c.execute(
                "INSERT INTO portal_users (username, password, role, first_login) VALUES (%s, %s, 'admin', TRUE)",
                (args.username, hashed)
            )
            print(f"SUCCESS: Created new admin user '{args.username}'")
        else:
            # Update password and set first_login = FALSE so they log in directly
            c.execute(
                "UPDATE portal_users SET password = %s, first_login = FALSE WHERE username = %s",
                (hashed, args.username)
            )
            print(f"SUCCESS: Reset password for user '{args.username}'.")
            
        conn.commit()
        c.close()
        conn.close()
    except Exception as e:
        print(f"ERROR: Failed to connect or execute SQL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

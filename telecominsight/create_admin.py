"""Create a platform administrator.   Run:  python -m telecominsight.create_admin"""
import getpass
import sys

from sqlalchemy.exc import IntegrityError

from . import auth, db


def main() -> None:
    engine = db.get_engine()
    db.init_db(engine)
    username = input("Admin username: ").strip().lower()
    if not username:
        sys.exit("A username is required.")
    password = getpass.getpass(f"Password (min {auth.MIN_PASSWORD_LENGTH} characters): ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    try:
        user_id = db.create_user(engine, username, auth.hash_password(password), auth.ROLE_ADMIN)
    except ValueError as exc:                 # password too short
        sys.exit(str(exc))
    except IntegrityError:
        sys.exit("That username already exists.")
    db.log_event(engine, user_id, None, "admin_created", "created with create_admin.py")
    print(f"Administrator '{username}' created.")


if __name__ == "__main__":
    main()
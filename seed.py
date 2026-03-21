"""
seed.py – Creates tables and inserts default roles + admin user.
Run once:  python seed.py
"""
from app.core.database import engine, SessionLocal
from app.core.database import Base
from app.core.security import get_password_hash
# Import models so Base knows about them
from app.models.user import Role, User, Task, Document, DocumentChunk, ActivityLog  # noqa


def seed():
    print("Creating tables …")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ── Roles ────────────────────────────────────────────────────────────
        if not db.query(Role).filter(Role.name == "admin").first():
            db.add(Role(name="admin", description="Full system access"))
            print("  Role 'admin' created.")

        if not db.query(Role).filter(Role.name == "user").first():
            db.add(Role(name="user", description="Standard user access"))
            print("  Role 'user' created.")

        db.commit()

        # ── Default admin account ────────────────────────────────────────────
        if not db.query(User).filter(User.username == "admin").first():
            admin_role = db.query(Role).filter(Role.name == "admin").first()
            db.add(
                User(
                    username="admin",
                    email="admin@example.com",
                    hashed_password=get_password_hash("Admin@123"),
                    full_name="System Administrator",
                    role_id=admin_role.id,
                )
            )
            db.commit()
            print("  Default admin user created  (username=admin  password=Admin@123)")
        else:
            print("  Admin user already exists – skipped.")

        # ── Sample regular user ──────────────────────────────────────────────
        if not db.query(User).filter(User.username == "john").first():
            user_role = db.query(Role).filter(Role.name == "user").first()
            db.add(
                User(
                    username="john",
                    email="john@example.com",
                    hashed_password=get_password_hash("User@123"),
                    full_name="John Doe",
                    role_id=user_role.id,
                )
            )
            db.commit()
            print("  Sample user 'john' created  (password=User@123)")

        print("\nDatabase seeded successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()

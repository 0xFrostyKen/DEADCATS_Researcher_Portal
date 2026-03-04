from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL      = os.getenv("DATABASE_URL")
JWT_SECRET        = os.getenv("JWT_SECRET", "changeme")
JWT_ALGORITHM     = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES= int(os.getenv("JWT_EXPIRE_MINUTES", 480))
ADMIN_HANDLE      = os.getenv("ADMIN_HANDLE", "admin")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "changeme")
FRONTEND_ORIGIN   = os.getenv("FRONTEND_ORIGIN", "http://localhost:5500")
REGISTER_TOKEN    = os.getenv("REGISTER_TOKEN", "")
MASTER_HANDLE     = os.getenv("MASTER_HANDLE", "deadcats_master333")
CTFTIME_TEAM_ID   = os.getenv("CTFTIME_TEAM_ID", "367609")
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uuid
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx

app = FastAPI(title="Auth Service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pairuser:pairpass@postgres:5432/pairdb")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "paircode-auth")

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(200),
            firebase_uid VARCHAR(200) UNIQUE,
            role VARCHAR(50) DEFAULT 'student'
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

class UserRegister(BaseModel):
    username: str
    email: str
    firebase_uid: str
    role: str = "student"

class UserLogin(BaseModel):
    firebase_uid: str
    email: str
    username: str = ""

async def verify_firebase_token(id_token: str) -> dict:
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=AIzaSyAd_x7XxX1WRpqaaySmuTz_nYSH3gB6RCg"
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={"idToken": id_token})
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Token de Firebase inválido")
        data = response.json()
        if "users" not in data or len(data["users"]) == 0:
            raise HTTPException(status_code=401, detail="Usuario no encontrado en Firebase")
        return data["users"][0]

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "auth-service", "auth_provider": "firebase"}

@app.post("/auth/register")
async def register(user: UserRegister):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE firebase_uid = %s", (user.firebase_uid,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return {"message": "Usuario ya existe", "username": user.username}
    cur.execute("SELECT id FROM users WHERE username = %s", (user.username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Nombre de usuario ya en uso")
    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, username, email, firebase_uid, role) VALUES (%s, %s, %s, %s, %s)",
        (user_id, user.username, user.email, user.firebase_uid, user.role)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Usuario registrado exitosamente", "username": user.username, "role": user.role}

@app.post("/auth/login")
async def login(user: UserLogin):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE firebase_uid = %s", (user.firebase_uid,))
    stored = cur.fetchone()
    cur.close()
    conn.close()
    if not stored:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en el sistema")
    token = str(uuid.uuid4())
    return {
        "message": "Login exitoso",
        "token": token,
        "username": stored["username"],
        "email": stored["email"],
        "role": stored["role"],
        "auth_provider": "firebase"
    }

@app.get("/auth/users")
def get_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT username, email, role FROM users")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return {"users": [{"username": u["username"], "email": u["email"], "role": u["role"]} for u in users]}
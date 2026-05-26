from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import hashlib
import uuid
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="Auth Service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pairuser:pairpass@postgres:5432/pairdb")

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(256) NOT NULL,
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
    password: str
    role: str = "student"

class UserLogin(BaseModel):
    username: str
    password: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "auth-service"}

@app.post("/auth/register")
def register(user: UserRegister):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = %s", (user.username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, username, password, role) VALUES (%s, %s, %s, %s)",
        (user_id, user.username, hash_password(user.password), user.role)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Usuario registrado exitosamente", "username": user.username}

@app.post("/auth/login")
def login(user: UserLogin):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (user.username,))
    stored = cur.fetchone()
    cur.close()
    conn.close()
    if not stored:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if stored["password"] != hash_password(user.password):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    token = str(uuid.uuid4())
    return {"message": "Login exitoso", "token": token, "username": user.username, "role": stored["role"]}

@app.get("/auth/users")
def get_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT username, role FROM users")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return {"users": [{"username": u["username"], "role": u["role"]} for u in users]}
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json

app = FastAPI(title="Editor Service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pairuser:pairpass@postgres:5432/pairdb")

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            owner VARCHAR(100) NOT NULL,
            language VARCHAR(50) DEFAULT 'python',
            participants TEXT DEFAULT '[]',
            code TEXT DEFAULT '',
            created_at VARCHAR(50)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

class Session(BaseModel):
    name: str
    owner: str
    language: str = "python"

class CodeUpdate(BaseModel):
    session_id: str
    user: str
    code: str

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "editor-service"}

@app.post("/sessions")
def create_session(session: Session):
    session_id = str(uuid.uuid4())
    participants = json.dumps([session.owner])
    created_at = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions (id, name, owner, language, participants, code, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (session_id, session.name, session.owner, session.language, participants, "", created_at)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Sesión creada", "session": {
        "id": session_id, "name": session.name, "owner": session.owner,
        "language": session.language, "participants": [session.owner], "created_at": created_at
    }}

@app.get("/sessions")
def get_sessions():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    sessions = []
    for r in rows:
        s = dict(r)
        s["participants"] = json.loads(s["participants"])
        sessions.append(s)
    return {"sessions": sessions}

@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    s = dict(row)
    s["participants"] = json.loads(s["participants"])
    return s

@app.post("/sessions/{session_id}/join")
def join_session(session_id: str, username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    participants = json.loads(row["participants"])
    if username not in participants:
        participants.append(username)
        cur.execute("UPDATE sessions SET participants = %s WHERE id = %s",
                    (json.dumps(participants), session_id))
        conn.commit()
    cur.close()
    conn.close()
    return {"message": f"{username} se unió a la sesión", "participants": participants}

@app.put("/sessions/{session_id}/code")
def update_code(session_id: str, update: CodeUpdate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM sessions WHERE id = %s", (session_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    cur.execute("UPDATE sessions SET code = %s WHERE id = %s", (update.code, session_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Código actualizado", "session_id": session_id, "updated_by": update.user}

@app.get("/sessions/{session_id}/code")
def get_code(session_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT code FROM sessions WHERE id = %s", (session_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return {"session_id": session_id, "code": row["code"]}
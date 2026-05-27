from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import httpx

app = FastAPI(title="API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_SERVICE = "http://auth-service:8001"
EDITOR_SERVICE = "http://editor-service:8002"
AI_SERVICE = "http://ai-service:8003"

# ─── TOKEN STORE (en memoria, simple para demo) ───────────────────────────────
# Guarda: token -> {username, role, email}
active_sessions = {}

async def forward_request(method: str, url: str, data: dict = None):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=data)
            elif method == "PUT":
                response = await client.put(url, json=data)
            elif method == "DELETE":
                response = await client.delete(url)
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail=f"Servicio no disponible: {url}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail=f"Servicio tardó demasiado: {url}")

def get_current_user(request: Request) -> Optional[dict]:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token or token not in active_sessions:
        return None
    return active_sessions[token]

def require_role(request: Request, allowed_roles: list) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado — inicia sesión primero")
    if user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Acceso denegado — se requiere rol: {', '.join(allowed_roles)}. Tu rol es: {user['role']}"
        )
    return user

@app.get("/health")
async def health_check():
    services = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in [("auth-service", AUTH_SERVICE), ("editor-service", EDITOR_SERVICE), ("ai-service", AI_SERVICE)]:
            try:
                r = await client.get(f"{url}/health")
                services[name] = r.json()
            except:
                services[name] = {"status": "down"}
    return {"status": "ok", "service": "api-gateway", "downstream": services}

# ─── AUTH ROUTES ───────────────────────────────────────────────────────────────
@app.post("/api/auth/register")
async def register(request: Request):
    body = await request.json()
    return await forward_request("POST", f"{AUTH_SERVICE}/auth/register", body)

@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    result = await forward_request("POST", f"{AUTH_SERVICE}/auth/login", body)
    if "token" in result:
        active_sessions[result["token"]] = {
            "username": result.get("username"),
            "role": result.get("role"),
            "email": result.get("email")
        }
    return result

@app.post("/api/auth/logout")
async def logout(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token in active_sessions:
        del active_sessions[token]
    return {"message": "Sesión cerrada"}

# Solo teacher y admin pueden ver todos los usuarios
@app.get("/api/auth/users")
async def get_users(request: Request):
    require_role(request, ["teacher", "admin"])
    return await forward_request("GET", f"{AUTH_SERVICE}/auth/users")

# ─── EDITOR ROUTES ─────────────────────────────────────────────────────────────
# Todos los roles pueden crear sesiones
@app.post("/api/sessions")
async def create_session(request: Request):
    require_role(request, ["student", "teacher", "admin"])
    body = await request.json()
    return await forward_request("POST", f"{EDITOR_SERVICE}/sessions", body)

# Teacher y admin ven TODAS las sesiones, student solo las suyas
@app.get("/api/sessions")
async def get_sessions(request: Request):
    user = get_current_user(request)
    result = await forward_request("GET", f"{EDITOR_SERVICE}/sessions")
    if user and user["role"] == "student":
        sessions = result.get("sessions", [])
        filtered = [s for s in sessions if s.get("owner") == user["username"] or user["username"] in (s.get("participants") or [])]
        return {"sessions": filtered, "note": "Mostrando solo tus sesiones"}
    return result

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    return await forward_request("GET", f"{EDITOR_SERVICE}/sessions/{session_id}")

@app.post("/api/sessions/{session_id}/join")
async def join_session(session_id: str, request: Request):
    require_role(request, ["student", "teacher", "admin"])
    body = await request.json()
    username = body.get("username", "")
    return await forward_request("POST", f"{EDITOR_SERVICE}/sessions/{session_id}/join?username={username}")

@app.put("/api/sessions/{session_id}/code")
async def update_code(session_id: str, request: Request):
    require_role(request, ["student", "teacher", "admin"])
    body = await request.json()
    return await forward_request("PUT", f"{EDITOR_SERVICE}/sessions/{session_id}/code", body)

@app.get("/api/sessions/{session_id}/code")
async def get_code(session_id: str):
    return await forward_request("GET", f"{EDITOR_SERVICE}/sessions/{session_id}/code")

# Solo admin puede eliminar sesiones
@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    require_role(request, ["admin"])
    return await forward_request("DELETE", f"{EDITOR_SERVICE}/sessions/{session_id}")

# ─── AI ROUTES ─────────────────────────────────────────────────────────────────
@app.post("/api/ai/analyze")
async def analyze_code(request: Request):
    require_role(request, ["student", "teacher", "admin"])
    body = await request.json()
    return await forward_request("POST", f"{AI_SERVICE}/ai/analyze", body)

@app.get("/api/ai/history")
async def get_ai_history(request: Request):
    require_role(request, ["teacher", "admin"])
    return await forward_request("GET", f"{AI_SERVICE}/ai/history")

@app.get("/api/ai/history/{session_id}")
async def get_ai_history_by_session(session_id: str):
    return await forward_request("GET", f"{AI_SERVICE}/ai/history/{session_id}")

@app.post("/api/ai/circuit-breaker/open")
async def open_circuit_breaker(request: Request):
    require_role(request, ["admin"])
    return await forward_request("POST", f"{AI_SERVICE}/ai/circuit-breaker/open")

@app.post("/api/ai/circuit-breaker/close")
async def close_circuit_breaker(request: Request):
    require_role(request, ["admin"])
    return await forward_request("POST", f"{AI_SERVICE}/ai/circuit-breaker/close")
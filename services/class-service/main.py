import os
import uuid
from datetime import datetime
from typing import Optional, List

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import register_uuid  # add this to fix psycopg2.ProgrammingError: can't adapt type 'UUID'
register_uuid() # (global uuid registration)
from fastapi import FastAPI, HTTPException, Header # easy REST
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://yoga:yoga@postgres:5432/yoga")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme")

# db
pool: Optional[SimpleConnectionPool] = None

app = FastAPI(title="Class Service", version="1.0.3")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# models
class ClassCreate(BaseModel):
    title: str
    instructor: str
    start_time: str  # ISO8601, e.g. 2025-10-01T18:00:00Z
    capacity: int = Field(ge=1)

class SeatChange(BaseModel):
    seats: int = Field(default=1, ge=1)

class ClassOut(BaseModel):
    id: str
    title: str
    instructor: str
    start_time: str
    capacity: int
    available_seats: int

# lifecycle
@app.on_event("startup")
def startup():
    global pool
    pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)

@app.on_event("shutdown")
def shutdown():
    global pool
    if pool:
        pool.closeall()

# health
@app.get("/health")
def health():
    return {"status": "ok"}

# HTML
@app.get("/")
def root():
    return HTMLResponse(
        """
<!doctype html><html><head><meta charset="utf-8"><title>Class Service</title></head>
<body style="font-family: system-ui; margin: 2rem;">
  <h1>Class Service</h1>
  <p>Use <a href="/admin">/admin</a> to create classes or <a href="/docs">/docs</a> for the API.</p>
</body></html>
"""
    )

@app.get("/admin")
def admin_page():
    return HTMLResponse(
        """
<!doctype html><html><head><meta charset="utf-8"><title>Create Class</title></head>
<body style="font-family: system-ui; margin: 2rem; max-width: 700px;">
  <h1>Create class</h1>
  <form id="f">
    <label>Title <input name="title" required></label><br><br>
    <label>Instructor <input name="instructor" required></label><br><br>
    <label>Start time (ISO) <input name="start_time" value="2025-10-01T18:00:00Z" required></label><br><br>
    <label>Capacity <input type="number" name="capacity" value="12" min="1" required></label><br><br>
    <label>Admin token <input name="token" value="changeme" required></label><br><br>
    <button>Create</button>
  </form>
  <pre id="out" style="background:#f6f6f6; padding:1rem; border-radius:8px; white-space:pre-wrap;"></pre>
  <h2>Existing classes</h2>
  <ul id="list"></ul>
  <script>
    async function load() {
      const res = await fetch('/classes');
      const data = await res.json();
      const ul = document.getElementById('list');
      ul.innerHTML = '';
      data.forEach(c => {
        const li = document.createElement('li');
        li.textContent = `${c.id} — ${c.title} with ${c.instructor} at ${c.start_time} (capacity ${c.capacity}, available ${c.available_seats})`;
        ul.appendChild(li);
      });
    }
    document.getElementById('f').addEventListener('submit', async (e)=>{
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = {
        title: fd.get('title'),
        instructor: fd.get('instructor'),
        start_time: fd.get('start_time'),
        capacity: Number(fd.get('capacity'))
      };
      const res = await fetch('/classes', {
        method:'POST',
        headers:{'Content-Type':'application/json','x-admin-token':fd.get('token')},
        body: JSON.stringify(body)
      });
      document.getElementById('out').textContent = await res.text();
      load();
    });
    load();
  </script>
</body></html>
"""
    )

# API
@app.get("/classes", response_model=List[ClassOut])
def list_classes():
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, instructor, "
                "to_char(start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), "
                "capacity, available_seats "
                "FROM classes ORDER BY start_time"
            )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "title": r[1],
                    "instructor": r[2],
                    "start_time": r[3],
                    "capacity": r[4],
                    "available_seats": r[5],
                }
                for r in rows
            ]
    finally:
        pool.putconn(conn)

@app.get("/classes/{class_id}", response_model=ClassOut)
def get_class(class_id: str):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, instructor, "
                "to_char(start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), "
                "capacity, available_seats "
                "FROM classes WHERE id=%s",
                (uuid.UUID(class_id),),
            )
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "Class not found")
            return {
                "id": str(r[0]),
                "title": r[1],
                "instructor": r[2],
                "start_time": r[3],
                "capacity": r[4],
                "available_seats": r[5],
            }
    finally:
        pool.putconn(conn)

@app.post("/classes", response_model=dict)
def create_class(payload: ClassCreate, x_admin_token: str = Header(default="")):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    # parse ISO time (allow trailing Z)
    try:
        dt = datetime.fromisoformat(payload.start_time.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "start_time must be ISO8601, e.g. 2025-10-01T18:00:00Z")

    cid = uuid.uuid4()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO classes(id, title, instructor, start_time, capacity, available_seats) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (cid, payload.title, payload.instructor, dt, payload.capacity, payload.capacity),
                )
        return {"id": str(cid)}
    finally:
        pool.putconn(conn)

@app.post("/classes/{class_id}/reserve", response_model=dict)
def reserve_seat(class_id: str, body: SeatChange):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE classes SET available_seats = available_seats - %s "
                    "WHERE id=%s AND available_seats >= %s "
                    "RETURNING available_seats",
                    (body.seats, uuid.UUID(class_id), body.seats),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(409, "Not enough seats")
                return {"ok": True, "available_seats": row[0]}
    finally:
        pool.putconn(conn)

@app.post("/classes/{class_id}/release", response_model=dict)
def release_seat(class_id: str, body: SeatChange):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE classes SET available_seats = available_seats + %s "
                    "WHERE id=%s RETURNING available_seats",
                    (body.seats, uuid.UUID(class_id)),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Class not found")
                return {"ok": True, "available_seats": row[0]}
    finally:
        pool.putconn(conn)

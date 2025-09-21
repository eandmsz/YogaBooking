import os
import uuid
from typing import Optional, List

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import register_uuid  # add this to fix psycopg2.ProgrammingError: can't adapt type 'UUID'
register_uuid() # (global uuid registration)
import requests
from fastapi import FastAPI, HTTPException, Query # easy REST
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://yoga:yoga@postgres:5432/yoga")
CLASS_SERVICE_BASE = os.getenv("CLASS_SERVICE_BASE_URL", "http://class-service:8000")

# db pool
pool: Optional[SimpleConnectionPool] = None

app = FastAPI(title="Booking Service", version="1.0.3")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# models
class BookingCreate(BaseModel):
    class_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)  # keep it simple

class BookingOut(BaseModel):
    id: str
    class_id: str
    name: str
    email: str
    created_at: str

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
INDEX_HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>Book a Class</title></head>
<body style="font-family: system-ui; margin: 2rem; max-width: 700px;">
  <h1>Book a class</h1>
  <p>Pick a class and enter your details.</p>
  <label>Class <select id="class"></select></label><br><br>
  <label>Name <input id="name" required></label><br><br>
  <label>Email <input id="email" required></label><br><br>
  <button id="book">Book</button>
  <pre id="out" style="background:#f6f6f6; padding:1rem; border-radius:8px; white-space:pre-wrap;"></pre>
  <script>
    async function loadClasses() {
      const res = await fetch('/classes');
      const data = await res.json();
      const sel = document.getElementById('class');
      sel.innerHTML = '';
      data.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.title} with ${c.instructor} at ${c.start_time} (avail ${c.available_seats})`;
        sel.appendChild(opt);
      });
    }
    document.getElementById('book').addEventListener('click', async ()=>{
      const class_id = document.getElementById('class').value;
      const name = document.getElementById('name').value;
      const email = document.getElementById('email').value;
      const res = await fetch('/bookings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({class_id, name, email})});
      document.getElementById('out').textContent = await res.text();
      loadClasses();
    });
    loadClasses();
  </script>
</body></html>
"""

@app.get("/", response_class=HTMLResponse)
def booking_page():
    return HTMLResponse(INDEX_HTML)

# helper: pass-through to class service for the UI
@app.get("/classes")
def list_classes_passthrough():
    try:
        r = requests.get(f"{CLASS_SERVICE_BASE}/classes", timeout=5)
        if r.status_code != 200:
            raise HTTPException(502, f"class-service returned {r.status_code}: {r.text}")
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(502, f"class-service unreachable: {e}")

# API
@app.get("/bookings", response_model=List[BookingOut])
def list_bookings(class_id: Optional[uuid.UUID] = Query(default=None)):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if class_id:
                cur.execute(
                    "SELECT id, class_id, name, email, "
                    "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
                    "FROM bookings WHERE class_id=%s ORDER BY created_at DESC",
                    (class_id,),
                )
            else:
                cur.execute(
                    "SELECT id, class_id, name, email, "
                    "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
                    "FROM bookings ORDER BY created_at DESC"
                )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "class_id": str(r[1]),
                    "name": r[2],
                    "email": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
    finally:
        pool.putconn(conn)

@app.post("/bookings", response_model=dict)
def create_booking(payload: BookingCreate):
    class_id_str = str(payload.class_id)

    # 1) Reserve seat via class-service
    try:
        r = requests.post(
            f"{CLASS_SERVICE_BASE}/classes/{class_id_str}/reserve",
            json={"seats": 1},
            timeout=5,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"class-service unreachable: {e}")

    if r.status_code != 200:
        raise HTTPException(r.status_code, f"Seat reservation failed: {r.text}")

    # 2) Insert booking; on failure, compensate by releasing seat
    conn = pool.getconn()
    try:
        bid = uuid.uuid4()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO bookings(id, class_id, name, email) VALUES (%s,%s,%s,%s)",
                        (bid, payload.class_id, payload.name, payload.email),
                    )
        except Exception as e:
            # compensate
            try:
                requests.post(
                    f"{CLASS_SERVICE_BASE}/classes/{class_id_str}/release",
                    json={"seats": 1},
                    timeout=5,
                )
            except Exception:
                pass
            raise HTTPException(500, f"Booking insert failed: {e}")
        return {"id": str(bid), "message": "Booking confirmed"}
    finally:
        pool.putconn(conn)

import os, uuid, json
from typing import Optional, List

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import register_uuid # add this to fix psycopg2.ProgrammingError: can't adapt type 'UUID'
import requests
import pika # For RabbitMQ
from fastapi import FastAPI, HTTPException, Query, status # For REST
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# --- config ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://yoga:yoga@postgres:5432/yoga")
CLASS_SERVICE_BASE = os.getenv("CLASS_SERVICE_BASE_URL", "http://class-service:8000")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rabbit:rabbit@rabbitmq:5672/%2f")
QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "booking_requests")

register_uuid()

# --- db pool ---
pool: Optional[SimpleConnectionPool] = None

app = FastAPI(title="Booking Service", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- models ---
class BookingCreate(BaseModel):
    class_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)

class BookingOut(BaseModel):
    id: str
    class_id: str
    name: str
    email: str
    created_at: str
    status: str
    error: Optional[str] = None

# --- lifecycle ---
@app.on_event("startup")
def startup():
    global pool
    pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)

@app.on_event("shutdown")
def shutdown():
    global pool
    if pool:
        pool.closeall()

# --- health ---
@app.get("/health")
def health():
    return {"status": "ok"}

# --- HTML (polls for status) ---
INDEX_HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>Book a Class</title></head>
<body style="font-family: system-ui; margin: 2rem; max-width: 700px;">
  <h1>Book a class</h1>
  <p>Pick a class and enter your details. Booking is async, status will update.</p>
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
    async function poll(id) {
      for (let i=0; i<20; i++) {
        const r = await fetch('/bookings/' + id);
        const b = await r.json();
        if (b.status !== 'pending') return b;
        await new Promise(res => setTimeout(res, 1000));
      }
      return {id, status: 'pending'};
    }
    document.getElementById('book').addEventListener('click', async ()=>{
      const class_id = document.getElementById('class').value;
      const name = document.getElementById('name').value;
      const email = document.getElementById('email').value;
      const res = await fetch('/bookings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({class_id, name, email})});
      const data = await res.json();
      document.getElementById('out').textContent = 'Booking ' + data.id + ' is ' + data.status + '...';
      const final = await poll(data.id);
      document.getElementById('out').textContent = JSON.stringify(final, null, 2);
    });
    loadClasses();
  </script>
</body></html>
"""

@app.get("/", response_class=HTMLResponse)
def booking_page():
    return HTMLResponse(INDEX_HTML)

# --- pass-through for classes ---
@app.get("/classes")
def list_classes_passthrough():
    try:
        r = requests.get(f"{CLASS_SERVICE_BASE}/classes", timeout=5)
        if r.status_code != 200:
            raise HTTPException(502, f"class-service returned {r.status_code}: {r.text}")
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(502, f"class-service unreachable: {e}")

# --- helpers ---
def publish_booking(msg: dict):
    params = pika.URLParameters(RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=QUEUE_NAME, durable=True)
    ch.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(msg).encode("utf-8"),
        properties=pika.BasicProperties(
            delivery_mode=2,           # persist to disk
            content_type="application/json",
        ),
    )
    conn.close()

# --- API ---
@app.get("/bookings", response_model=List[BookingOut])
def list_bookings(class_id: Optional[uuid.UUID] = Query(default=None)):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if class_id:
                cur.execute(
                    "SELECT id, class_id, name, email, "
                    "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), "
                    "status, error FROM bookings WHERE class_id=%s ORDER BY created_at DESC",
                    (class_id,),
                )
            else:
                cur.execute(
                    "SELECT id, class_id, name, email, "
                    "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), "
                    "status, error FROM bookings ORDER BY created_at DESC"
                )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "class_id": str(r[1]),
                    "name": r[2],
                    "email": r[3],
                    "created_at": r[4],
                    "status": r[5],
                    "error": r[6],
                }
                for r in rows
            ]
    finally:
        pool.putconn(conn)

@app.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: uuid.UUID):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, class_id, name, email, "
                "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), "
                "status, error FROM bookings WHERE id=%s",
                (booking_id,),
            )
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "Not found")
            return {
                "id": str(r[0]),
                "class_id": str(r[1]),
                "name": r[2],
                "email": r[3],
                "created_at": r[4],
                "status": r[5],
                "error": r[6],
            }
    finally:
        pool.putconn(conn)

@app.post("/bookings", status_code=status.HTTP_202_ACCEPTED)
def create_booking(payload: BookingCreate):
    bid = uuid.uuid4()
    # 1) insert pending
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO bookings(id, class_id, name, email, status) VALUES (%s,%s,%s,%s,'pending')",
                    (bid, payload.class_id, payload.name, payload.email),
                )
    finally:
        pool.putconn(conn)
    # 2) publish message
    publish_booking({"booking_id": str(bid), "class_id": str(payload.class_id)})
    # 3) respond
    return {"id": str(bid), "status": "pending"}


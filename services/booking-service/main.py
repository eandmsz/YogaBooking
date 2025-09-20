import os
opt.textContent = `${{c.title}} with ${{c.instructor}} at ${{c.start_time}} (avail ${{c.available_seats}})`;
sel.appendChild(opt);
}});
}}
document.getElementById('book').addEventListener('click', async ()=>{{
const class_id = document.getElementById('class').value;
const name = document.getElementById('name').value;
const email = document.getElementById('email').value;
const res = await fetch('/bookings', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{class_id, name, email}})}});
document.getElementById('out').textContent = await res.text();
loadClasses();
}});
loadClasses();
</script>
</body></html>
""")


@app.get("/bookings")
def list_bookings(class_id: Optional[str] = None):
conn = pool.getconn()
try:
with conn.cursor() as cur:
if class_id:
cur.execute("SELECT id, class_id, name, email, to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD""T""HH24:MI:SS""Z""') FROM bookings WHERE class_id=%s ORDER BY created_at DESC", (uuid.UUID(class_id),))
else:
cur.execute("SELECT id, class_id, name, email, to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD""T""HH24:MI:SS""Z""') FROM bookings ORDER BY created_at DESC")
rows = cur.fetchall()
return [
{"id": str(r[0]), "class_id": str(r[1]), "name": r[2], "email": r[3], "created_at": r[4]} for r in rows
]
finally:
pool.putconn(conn)


@app.post("/bookings")
def create_booking(request: Request):
body_raw = request._body if hasattr(request, '_body') else None
try:
body = json.loads(body_raw.decode() if body_raw else request.body())
if not isinstance(body, dict):
body = json.loads(body)
except Exception:
body = {}
class_id = body.get('class_id')
name = body.get('name')
email = body.get('email')
if not class_id or not name or not email:
raise HTTPException(400, "class_id, name, email required")


# 1) Reserve seat via class-service
r = requests.post(f"{CLASS_SERVICE_BASE}/classes/{class_id}/reserve", json={"seats": 1}, timeout=5)
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
(bid, uuid.UUID(class_id), name, email),
)
except Exception as e:
# compensate
try:
requests.post(f"{CLASS_SERVICE_BASE}/classes/{class_id}/release", json={"seats": 1}, timeout=5)
except Exception:
pass
raise HTTPException(500, f"Booking insert failed: {str(e)}")
return {"id": str(bid), "message": "Booking confirmed"}
finally:
pool.putconn(conn)

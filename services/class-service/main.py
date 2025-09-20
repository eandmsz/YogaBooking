import os
def create_class(request: Request, x_admin_token: str = Header(default="")):
if x_admin_token != ADMIN_TOKEN:
raise HTTPException(401, "Unauthorized")
body = json.loads(request._body.decode() if hasattr(request, '_body') else (request._body if request._body else request.body()))
# Fallback if running under Uvicorn without body pre-read
try:
body = body if isinstance(body, dict) else json.loads(body)
except Exception:
body = {}
title = body.get('title')
instructor = body.get('instructor')
start_time = body.get('start_time')
capacity = int(body.get('capacity', 0))
if not title or not instructor or not start_time or capacity < 1:
raise HTTPException(400, "Invalid payload")
cid = uuid.uuid4()
conn = pool.getconn()
try:
with conn:
with conn.cursor() as cur:
cur.execute(
"INSERT INTO classes(id, title, instructor, start_time, capacity, available_seats) VALUES (%s,%s,%s,%s,%s,%s)",
(cid, title, instructor, datetime.fromisoformat(start_time.replace('Z','+00:00')), capacity, capacity),
)
return {"id": str(cid)}
finally:
pool.putconn(conn)


@app.post("/classes/{class_id}/reserve")
def reserve_seat(class_id: str, request: Request):
body = json.loads(request._body.decode() if hasattr(request, '_body') else (request._body if request._body else request.body()))
try:
body = body if isinstance(body, dict) else json.loads(body)
except Exception:
body = {}
seats = int(body.get('seats', 1))
if seats < 1:
raise HTTPException(400, "seats must be >= 1")
conn = pool.getconn()
try:
with conn:
with conn.cursor() as cur:
cur.execute(
"UPDATE classes SET available_seats = available_seats - %s WHERE id=%s AND available_seats >= %s RETURNING available_seats",
(seats, uuid.UUID(class_id), seats),
)
if cur.rowcount == 0:
raise HTTPException(409, "Not enough seats")
new_avail = cur.fetchone()[0]
return {"ok": True, "available_seats": new_avail}
finally:
pool.putconn(conn)


@app.post("/classes/{class_id}/release")
def release_seat(class_id: str, request: Request):
body = json.loads(request._body.decode() if hasattr(request, '_body') else (request._body if request._body else request.body()))
try:
body = body if isinstance(body, dict) else json.loads(body)
except Exception:
body = {}
seats = int(body.get('seats', 1))
if seats < 1:
raise HTTPException(400, "seats must be >= 1")
conn = pool.getconn()
try:
with conn:
with conn.cursor() as cur:
cur.execute(
"UPDATE classes SET available_seats = available_seats + %s WHERE id=%s RETURNING available_seats",
(seats, uuid.UUID(class_id)),
)
if cur.rowcount == 0:
raise HTTPException(404, "Class not found")
new_avail = cur.fetchone()[0]
return {"ok": True, "available_seats": new_avail}
finally:
pool.putconn(conn)

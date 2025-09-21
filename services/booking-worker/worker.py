import os, json, uuid, time
import requests
import pika
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import register_uuid

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://yoga:yoga@postgres:5432/yoga")
CLASS_SERVICE_BASE = os.getenv("CLASS_SERVICE_BASE_URL", "http://class-service:8000")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rabbit:rabbit@rabbitmq:5672/%2f")
QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "booking_requests")

register_uuid()
pool = None

def get_pool():
    global pool
    if pool is None:
        pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=DATABASE_URL)
    return pool

def process_message(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        booking_id = uuid.UUID(msg["booking_id"])
        class_id = msg["class_id"]

        # 1) reserve seat
        r = requests.post(f"{CLASS_SERVICE_BASE}/classes/{class_id}/reserve",
                          json={"seats": 1}, timeout=5)
        if r.status_code != 200:
            err = f"reserve failed: {r.status_code} {r.text}"
            update_status(booking_id, "failed", err)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 2) update booking -> confirmed
        update_status(booking_id, "confirmed", None)

        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        # Mark failed to avoid poison loops; in real life you might dead-letter
        try:
            update_status(booking_id, "failed", f"worker error: {e}")
        except Exception:
            pass
        ch.basic_ack(delivery_tag=method.delivery_tag)

def update_status(booking_id: uuid.UUID, status: str, error: str | None):
    conn = get_pool().getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                if error:
                    cur.execute("UPDATE bookings SET status=%s, error=%s WHERE id=%s",
                                (status, error, booking_id))
                else:
                    cur.execute("UPDATE bookings SET status=%s, error=NULL WHERE id=%s",
                                (status, booking_id))
    finally:
        get_pool().putconn(conn)

def main():
    # wait for postgres & class-service at startup
    for _ in range(30):
        try:
            conn = psycopg2.connect(DATABASE_URL); conn.close(); break
        except Exception: time.sleep(1)
    for _ in range(30):
        try:
            requests.get(f"{CLASS_SERVICE_BASE}/health", timeout=2); break
        except Exception: time.sleep(1)

    params = pika.URLParameters(RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=QUEUE_NAME, durable=True)
    ch.basic_qos(prefetch_count=10)
    ch.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message, auto_ack=False)
    print("worker ready; waiting for messages")
    ch.start_consuming()

if __name__ == "__main__":
    main()

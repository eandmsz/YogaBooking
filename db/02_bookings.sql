CREATE TABLE IF NOT EXISTS bookings (
  id         UUID PRIMARY KEY,
  class_id   UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  email      TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'pending'
             CHECK (status IN ('pending','confirmed','failed')),
  error      TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Common lookups
CREATE INDEX IF NOT EXISTS idx_bookings_class_id   ON bookings(class_id);
CREATE INDEX IF NOT EXISTS idx_bookings_created_at ON bookings(created_at);
CREATE INDEX IF NOT EXISTS idx_bookings_status     ON bookings(status);

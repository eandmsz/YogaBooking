CREATE TABLE IF NOT EXISTS bookings (
id UUID PRIMARY KEY,
class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
name TEXT NOT NULL,
email TEXT NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bookings_class_id ON bookings(class_id);

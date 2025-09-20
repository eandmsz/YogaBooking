CREATE TABLE IF NOT EXISTS classes (
id UUID PRIMARY KEY,
title TEXT NOT NULL,
instructor TEXT NOT NULL,
start_time TIMESTAMPTZ NOT NULL,
capacity INT NOT NULL CHECK (capacity > 0),
available_seats INT NOT NULL CHECK (available_seats >= 0),
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_classes_start_time ON classes(start_time);

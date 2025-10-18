-- Blood Requests Database Schema
-- This file shows the SQLite table structure for the simplified blood requests system

-- Table: blood_request_simple
-- Stores simplified blood requests with the requested fields
CREATE TABLE IF NOT EXISTS blood_request_simple (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(15) NOT NULL,
    blood_type VARCHAR(5) NOT NULL,
    city VARCHAR(50) NOT NULL,
    message TEXT,
    date_requested DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Sample data insertion (optional)
-- INSERT INTO blood_request_simple (name, email, phone, blood_type, city, message) 
-- VALUES ('John Doe', 'john@example.com', '1234567890', 'O+', 'New York', 'Urgent blood needed for surgery');

-- Index for better performance
CREATE INDEX IF NOT EXISTS idx_blood_request_simple_date ON blood_request_simple(date_requested);
CREATE INDEX IF NOT EXISTS idx_blood_request_simple_blood_type ON blood_request_simple(blood_type);
CREATE INDEX IF NOT EXISTS idx_blood_request_simple_city ON blood_request_simple(city);

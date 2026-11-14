-- Database Schema for KAWU Registration System

CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reg_number TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    id_number TEXT UNIQUE NOT NULL,
    staff_number TEXT UNIQUE NOT NULL,
    gender TEXT CHECK(gender IN ('Male', 'Female', 'Other')) NOT NULL,
    employer_id INTEGER NOT NULL,
    reg_date DATE NOT NULL,
    status TEXT CHECK(status IN ('Active', 'Suspended', 'Exited')) DEFAULT 'Active',
    qr_code_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employer_id) REFERENCES employers (id)
);

-- Seed Official KAWU Employer Categories
INSERT OR IGNORE INTO employers (name) VALUES 
('Kenya Airways'),
('Kenya Airports Authority (KAA)'),
('Jambojet'),
('Swissport Kenya'),
('KCAA (Kenya Civil Aviation Authority)'),
('Kenya Aerotek'),
('Tradewinds Aviation'),
('Eurocraft'),
('Bolloré Transport & Logistics');
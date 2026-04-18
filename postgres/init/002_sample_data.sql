-- =============================================================
-- Sample data for Demo table
-- Used by Mage ETL pipeline to demonstrate Bronze/Silver/Gold flow
-- =============================================================

CREATE TABLE IF NOT EXISTS public."Demo" (
    id          SERIAL PRIMARY KEY,
    name        TEXT,
    category    TEXT,
    value       NUMERIC(12, 2),
    quantity    INTEGER,
    order_date  DATE,
    region      TEXT,
    status      TEXT,
    customer_email TEXT,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public."Demo" (name, category, value, quantity, order_date, region, status, customer_email, notes)
VALUES
    ('Nguyen Van A',   'Electronics',   1500000, 2, '2024-01-05', 'Hanoi',         'completed', 'a@example.com',  'First order'),
    ('Tran Thi B',     'Fashion',        350000, 3, '2024-01-07', 'Ho Chi Minh',   'completed', 'b@example.com',  NULL),
    ('Le Van C',       'Electronics',   3200000, 1, '2024-01-10', 'Da Nang',       'pending',   'c@example.com',  'Awaiting stock'),
    ('Pham Thi D',     'Home & Garden',  420000, 5, '2024-01-12', 'Hanoi',         'completed', 'd@example.com',  NULL),
    ('Hoang Van E',    'Sports',         780000, 2, '2024-01-15', 'Can Tho',       'cancelled', 'e@example.com',  'Customer request'),
    ('Vu Thi F',       'Electronics',   2100000, 1, '2024-01-18', 'Ho Chi Minh',   'completed', 'f@example.com',  NULL),
    ('Dang Van G',     'Fashion',        210000, 4, '2024-01-20', 'Hanoi',         'completed', 'g@example.com',  NULL),
    ('Bui Thi H',      'Books',           95000, 6, '2024-01-22', 'Hai Phong',     'completed', 'h@example.com',  'Gift wrap'),
    ('Nguyen Van I',   'Home & Garden',  560000, 3, '2024-01-25', 'Da Nang',       'processing','i@example.com',  NULL),
    ('Tran Van J',     'Electronics',   4500000, 1, '2024-01-28', 'Ho Chi Minh',   'completed', 'j@example.com',  'High value'),
    ('Le Thi K',       'Sports',         320000, 2, '2024-02-01', 'Hanoi',         'completed', 'k@example.com',  NULL),
    ('Pham Van L',     'Books',           75000, 8, '2024-02-03', 'Can Tho',       'completed', 'l@example.com',  NULL),
    ('Hoang Thi M',   'Fashion',         480000, 2, '2024-02-06', 'Ho Chi Minh',   'returned',  'm@example.com',  'Size issue'),
    ('Vu Van N',       'Electronics',   1800000, 1, '2024-02-09', 'Hanoi',         'completed', 'n@example.com',  NULL),
    ('Dang Thi O',     'Home & Garden',  290000, 4, '2024-02-12', 'Da Nang',       'completed', 'o@example.com',  NULL),
    ('Bui Van P',      'Sports',         650000, 3, '2024-02-15', 'Hai Phong',     'completed', 'p@example.com',  NULL),
    ('Nguyen Thi Q',   'Books',          110000, 5, '2024-02-18', 'Ho Chi Minh',   'completed', 'q@example.com',  NULL),
    ('Tran Van R',     'Electronics',   5200000, 1, '2024-02-20', 'Hanoi',         'pending',   'r@example.com',  'Backorder'),
    ('Le Van S',       'Fashion',        390000, 2, '2024-02-22', 'Can Tho',       'completed', 's@example.com',  NULL),
    ('Pham Thi T',     'Home & Garden',  730000, 2, '2024-02-25', 'Ho Chi Minh',   'completed', 't@example.com',  NULL),
    ('Hoang Van U',    'Sports',         420000, 1, '2024-03-01', 'Hanoi',         'completed', 'u@example.com',  NULL),
    ('Vu Thi V',       'Electronics',   2750000, 2, '2024-03-04', 'Da Nang',       'completed', 'v@example.com',  NULL),
    ('Dang Van W',     'Books',           85000, 7, '2024-03-07', 'Hai Phong',     'completed', 'w@example.com',  NULL),
    ('Bui Thi X',      'Fashion',        520000, 3, '2024-03-10', 'Ho Chi Minh',   'completed', 'x@example.com',  NULL),
    ('Nguyen Van Y',   'Home & Garden',  340000, 6, '2024-03-13', 'Hanoi',         'processing','y@example.com',  NULL),
    ('Tran Thi Z',     'Sports',         870000, 2, '2024-03-16', 'Can Tho',       'completed', 'z@example.com',  NULL),
    ('Le Van AA',      'Electronics',   3900000, 1, '2024-03-19', 'Ho Chi Minh',   'completed', 'aa@example.com', 'Premium product'),
    ('Pham Van BB',    'Fashion',        160000, 5, '2024-03-22', 'Da Nang',       'cancelled', 'bb@example.com', NULL),
    ('Hoang Thi CC',   'Books',           65000, 10,'2024-03-25', 'Hanoi',         'completed', 'cc@example.com', 'Bulk order'),
    ('Vu Van DD',      'Home & Garden',  810000, 3, '2024-03-28', 'Hai Phong',     'completed', 'dd@example.com', NULL)
ON CONFLICT DO NOTHING;

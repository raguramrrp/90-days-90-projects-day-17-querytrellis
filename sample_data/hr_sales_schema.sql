-- QueryTrellis Sample Enterprise Analytics SQL Schema & Seed
CREATE TABLE departments (
    department_id INTEGER PRIMARY KEY,
    department_name VARCHAR(80) NOT NULL UNIQUE,
    annual_budget NUMERIC(12, 2) NOT NULL
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(160) NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    salary NUMERIC(10, 2) NOT NULL,
    sales_target NUMERIC(12, 2) NOT NULL
);

CREATE TABLE quarterly_deals (
    deal_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    region VARCHAR(60) NOT NULL,
    closed_at DATE NOT NULL,
    deal_amount NUMERIC(12, 2) NOT NULL,
    profit_margin NUMERIC(5, 2) NOT NULL
);

INSERT INTO departments (department_id, department_name, annual_budget) VALUES
(1, 'Enterprise Sales', 950000.00),
(2, 'Strategic Accounts', 1100000.00),
(3, 'Channel Partners', 490000.00);

INSERT INTO employees (employee_id, full_name, email, department_id, salary, sales_target) VALUES
(1, 'Aarav Sharma', 'aarav@demo.local', 1, 85000.00, 120000.00),
(2, 'Maya Patel', 'maya@demo.local', 2, 92000.00, 150000.00),
(3, 'Liam Carter', 'liam@demo.local', 1, 79000.00, 110000.00),
(4, 'Sofia Lindqvist', 'sofia@demo.local', 3, 74000.00, 95000.00);

INSERT INTO quarterly_deals (deal_id, employee_id, region, closed_at, deal_amount, profit_margin) VALUES
(101, 1, 'Asia Pacific', '2026-01-15', 45000.00, 0.34),
(102, 2, 'North America', '2026-01-22', 62000.00, 0.39),
(103, 1, 'Asia Pacific', '2026-02-11', 54000.00, 0.36),
(104, 3, 'Europe West', '2026-02-19', 38000.00, 0.28),
(105, 4, 'Europe West', '2026-03-04', 41000.00, 0.31),
(106, 2, 'North America', '2026-03-14', 71000.00, 0.41);

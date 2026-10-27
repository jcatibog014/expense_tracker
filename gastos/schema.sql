-- The tables of Ang Gastos! This SQL runs on SQLite and on PostgreSQL.
-- (db.schema_sql() changes the "id INTEGER PRIMARY KEY" lines for Postgres.)
--
-- Money is a whole number of centavos: P 1,234.50 is stored as 123450.
-- Decimal numbers (floats) can't hold 0.10 exactly, and money must add up exactly.
-- Dates are text in ISO order: '2026-10-28'. Months are '2026-10'.
-- True/false is 1/0, which both databases understand.

-- Children before parents: a table can't be dropped while another one points at it.
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS budgets;
DROP TABLE IF EXISTS recurring;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    demo_reset_at TEXT,                 -- when the demo data was last made fresh
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT                   -- too many wrong passwords: wait until then
);

-- Wallets: where the money is (Cash, GCash, a bank account...).
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('cash', 'ewallet', 'bank')),
    opening_balance INTEGER NOT NULL DEFAULT 0,  -- the money it had before the first transaction
    archived INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, name)
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    color TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, name, kind)
);

-- Things that repeat every month: salary, rent, Netflix...
CREATE TABLE recurring (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    note TEXT NOT NULL DEFAULT '',
    day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    start_date TEXT NOT NULL,
    end_date TEXT                        -- empty: it never stops
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense', 'transfer')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    date TEXT NOT NULL,
    -- No ON DELETE here: a wallet or category that is still used can't be
    -- deleted (the database says no). The app archives it instead.
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    to_account_id INTEGER REFERENCES accounts (id),
    category_id INTEGER REFERENCES categories (id),
    note TEXT NOT NULL DEFAULT '',
    recurring_id INTEGER REFERENCES recurring (id) ON DELETE SET NULL,
    -- A transfer moves money between two wallets and has no category.
    -- Income and expenses have a category and only one wallet.
    CHECK (
        (kind = 'transfer' AND to_account_id IS NOT NULL AND category_id IS NULL)
        OR (kind <> 'transfer' AND to_account_id IS NULL AND category_id IS NOT NULL)
    ),
    -- A repeating item is added at most once per date, however often we check.
    UNIQUE (recurring_id, date)
);

-- Almost every page asks "this user's transactions in this date range".
-- An index lets the database jump to them instead of reading every row.
CREATE INDEX transactions_user_date ON transactions (user_id, date);

CREATE TABLE budgets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    UNIQUE (user_id, category_id, month)
);

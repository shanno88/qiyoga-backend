import sqlite3 from 'sqlite3';

const db = new sqlite3.Database('./transactions.db');

function initializeDatabase() {
  db.serialize(() => {
    db.run(`
      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT UNIQUE NOT NULL,
        customer_email TEXT,
        amount REAL,
        currency TEXT,
        status TEXT,
        product TEXT,
        created_at TEXT,
        processed_at TEXT DEFAULT CURRENT_TIMESTAMP
      )
    `, (err) => {
      if (err) {
        console.error('Database initialization error:', err);
      } else {
        console.log('✓ Database initialized');
      }
    });
  });
}

initializeDatabase();

export default db;

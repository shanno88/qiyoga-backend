import sqlite3 from 'sqlite3';

const db = new sqlite3.Database('./transactions.db');

export async function initializeDatabase() {
  return new Promise((resolve, reject) => {
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
          reject(err);
        } else {
          console.log('Database initialized');
          resolve();
        }
      });
    });
  });
}

export async function saveTransaction(transactionData) {
  return new Promise((resolve, reject) => {
    const stmt = db.prepare(`
      INSERT OR REPLACE INTO transactions 
      (transaction_id, customer_email, amount, currency, status, product, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      transactionData.transaction_id,
      transactionData.customer_email,
      transactionData.amount,
      transactionData.currency,
      transactionData.status,
      transactionData.product,
      transactionData.created_at,
      function(err) {
        if (err) {
          reject(err);
        } else {
          resolve({ id: this.lastID, ...transactionData });
        }
      }
    );

    stmt.finalize();
  });
}

export async function getTransaction(transactionId) {
  return new Promise((resolve, reject) => {
    db.get(
      'SELECT * FROM transactions WHERE transaction_id = ?',
      [transactionId],
      (err, row) => {
        if (err) {
          reject(err);
        } else {
          resolve(row);
        }
      }
    );
  });
}

export async function getTransactionsByEmail(email) {
  return new Promise((resolve, reject) => {
    db.all(
      'SELECT * FROM transactions WHERE customer_email = ? ORDER BY created_at DESC',
      [email],
      (err, rows) => {
        if (err) {
          reject(err);
        } else {
          resolve(rows);
        }
      }
    );
  });
}

export default db;

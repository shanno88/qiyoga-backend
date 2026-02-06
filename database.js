const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

let db = null;

function initializeDatabase(dbPath) {
  db = new sqlite3.Database(dbPath);

  db.serialize(() => {
    db.run(`
      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT UNIQUE NOT NULL,
        customer_id TEXT,
        customer_email TEXT,
        amount TEXT,
        currency TEXT,
        custom_data TEXT,
        status TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE NOT NULL,
        email TEXT,
        has_access INTEGER DEFAULT 0,
        access_granted_at DATETIME,
        access_expires_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS user_access_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        customer_email TEXT,
        granted_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );
    `);
  });
}

function grantUserAccess(customerEmail, userId) {
  const now = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

  db.run(
    `UPDATE users SET has_access = 1, access_granted_at = ?, access_expires_at = ? WHERE email = ?`,
    [now, expiresAt, customerEmail]
  );

  db.run(
    `INSERT OR REPLACE INTO user_access_log (user_id, customer_email, granted_at) VALUES (?, ?, ?)`,
    [userId, customerEmail, now]
  );
}

function hasUserAccess(customerEmail) {
  return new Promise((resolve, reject) => {
    db.get(
      `SELECT access_granted_at, access_expires_at FROM users WHERE email = ?`,
      [customerEmail],
      (err, row) => {
        if (err) {
          reject(err);
          return;
        }

        if (!row) {
          resolve(false);
          return;
        }

        const now = new Date();
        const grantedAt = new Date(row.access_granted_at);
        const expiresAt = row.access_expires_at ? new Date(row.access_expires_at) : null;

        if (!row.has_access || !grantedAt) {
          resolve(false);
          return;
        }

        if (expiresAt && now > expiresAt) {
          db.run(
            `UPDATE users SET has_access = 0 WHERE email = ?`,
            [customerEmail]
          );
          resolve(false);
          return;
        }

        resolve(true);
      }
    );
  });
}

module.exports = {
  initializeDatabase,
  grantUserAccess,
  hasUserAccess
};

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');

const ocrRouter = require('./routes/ocr');
const paddleVerify = require('./middleware/paddleVerify');
const db = require('./database');

// 定义数据库路径
const dbPath = process.env.DB_PATH || path.join(__dirname, 'database.sqlite');
console.log('📊 Database path:', dbPath);

const app = express();

const PORT = process.env.PORT || 3001;
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:5173'];

app.use(cors({
  origin: ALLOWED_ORIGINS,
  credentials: true
}));

app.use(express.json());

app.use(express.urlencoded({ extended: true }));

app.get('/', (req, res) => {
  res.json({
    service: 'QiYoga Backend',
    version: '1.0.0',
    endpoints: {
      health: '/health',
      webhook: '/webhook/paddle',
      ocr: '/api/ocr'
    }
  });
});

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'QiYoga Backend is running',
    timestamp: new Date().toISOString()
  });
});

app.post('/webhook/paddle', paddleVerify, async (req, res) => {
  const event = req.body;
  console.log('\n=== WEBHOOK RECEIVED ===');
  console.log('Event ID:', event.event_id);
  console.log('Event Type:', event.event_type);

  try {
    if (event.event_type === 'transaction.completed' || event.event_type === 'payment.succeeded') {
      const data = event.data;
      console.log('💰 Payment/Transaction succeeded!');
      console.log('Transaction ID:', data.id);
      console.log('Customer ID:', data.customer_id);
      console.log('Amount:', data.amount);
      console.log('Currency:', data.currency);
      console.log('Customer Email:', data.customer?.email);
      console.log('Custom Data:', data.custom_data);

      // Store transaction in database
      db.run(`
        INSERT INTO transactions (transaction_id, customer_id, customer_email, amount, currency, custom_data, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'succeeded', CURRENT_TIMESTAMP)
      `, [data.id, data.customer_id, data.customer?.email, data.amount, data.currency, JSON.stringify(data.custom_data)]);

      // Check and grant user access
      if (data.customer?.email) {
        const hasAccess = await db.hasUserAccess(data.customer.email);
        if (!hasAccess) {
          db.grantUserAccess(data.customer.email, data.custom_data?.user_id);
          console.log('✅ Granted 30-day access to user:', data.customer.email);
        } else {
          console.log('ℹ️  User already has access:', data.customer.email);
        }
      }

      const transactionRecord = {
        transaction_id: data.id,
        customer_id: data.customer_id,
        customer_email: data.customer?.email,
        amount: data.amount,
        currency: data.currency,
        custom_data: data.custom_data,
        status: 'succeeded',
        timestamp: new Date().toISOString()
      };

      console.log('💾 Transaction record:', JSON.stringify(transactionRecord, null, 2));
    } else {
      console.log('ℹ️  Received event:', event.event_type);
    }

    res.status(200).json({ received: true });
    console.log('=== WEBHOOK PROCESSING COMPLETE ===\n');
  } catch (error) {
    console.error('❌ Error processing webhook:', error);
    res.status(500).json({ error: 'Failed to process webhook', details: error.message });
  }
});

app.use('/api/ocr', ocrRouter);

app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(err.status || 500).json({
    success: false,
    error: err.message || 'Internal server error'
  });
});

app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: 'Endpoint not found'
  });
});

db.initializeDatabase(dbPath);

app.listen(PORT, () => {
  console.log('\n🚀 QiYoga Backend is running!');
  console.log(`📍 Port: ${PORT}`);
  console.log(`🔗 Health check: http://localhost:${PORT}/health`);
  console.log(`🪝 Webhook endpoint: http://localhost:${PORT}/webhook/paddle`);
  console.log(`📄 OCR endpoint: http://localhost:${PORT}/api/ocr`);
  console.log(`📊 Database: ${dbPath}`);
  console.log(`✅ Allowed origins: ${ALLOWED_ORIGINS.join(', ')}`);
  console.log(`🔐 PADDLE_WEBHOOK_SECRET configured: ${!!process.env.PADDLE_WEBHOOK_SECRET}\n`);
});

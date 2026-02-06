import express from 'express';
import dotenv from 'dotenv';
import crypto from 'crypto';
import axios from 'axios';
import db from './database/transactions.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

const PADDLE_API_KEY = process.env.PADDLE_API_KEY;
const PADDLE_API_URL = process.env.PADDLE_API_URL || 'https://api.paddle.com';
const PADDLE_PRODUCT_ID = process.env.PADDLE_PRODUCT_ID;
const PADDLE_PRICE_ID = process.env.PADDLE_PRICE_ID;
const PADDLE_WEBHOOK_SECRET = process.env.PADDLE_WEBHOOK_SECRET;
const FRONTEND_URL = process.env.FRONTEND_URL || 'https://qiyoga.xyz';

const paddleApi = axios.create({
  baseURL: PADDLE_API_URL,
  headers: {
    'Authorization': `Bearer ${PADDLE_API_KEY}`,
    'Content-Type': 'application/json'
  }
});

function extractPaddleSignature(header) {
  const parts = header.split(',');
  const result = {};
  
  for (const part of parts) {
    const [key, value] = part.split('=').map(s => s.trim());
    if (key && value) {
      result[key] = value.replace(/"/g, '');
    }
  }
  
  return result;
}

function verifyPaddleSignature(payload, signature, timestamp, secret) {
  if (!secret) {
    console.warn('PADDLE_WEBHOOK_SECRET not set, skipping signature verification');
    return true;
  }

  try {
    const payloadString = typeof payload === 'string' ? payload : JSON.stringify(payload);
    const timestampString = timestamp.toString();
    const secretString = secret;

    const signedPayload = `${timestampString}:${payloadString}`;
    const expectedSignature = crypto
      .createHmac('sha256', secretString)
      .update(signedPayload)
      .digest('hex');

    return crypto.timingSafeEqual(
      Buffer.from(signature),
      Buffer.from(expectedSignature)
    );
  } catch (error) {
    console.error('Signature verification error:', error);
    return false;
  }
}

app.post('/api/checkout', async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email is required' });
    }

    if (!PADDLE_PRICE_ID) {
      return res.status(500).json({ error: 'Paddle Price ID not configured' });
    }

    const checkoutData = {
      items: [
        {
          price_id: PADDLE_PRICE_ID,
          quantity: 1
        }
      ],
      customer_email: email,
      settings: {
        success_url: `${FRONTEND_URL}/payment/success`,
        cancel_url: `${FRONTEND_URL}/payment/cancel`,
        display_mode: 'overlay'
      },
      custom_data: {
        product: 'TenantLease',
        user_email: email
      }
    };

    const response = await paddleApi.post('/checkout', checkoutData);

    res.json({
      checkout_url: response.data.data.checkout_url,
      checkout_id: response.data.data.id
    });

  } catch (error) {
    console.error('Checkout creation error:', error.response?.data || error.message);
    res.status(500).json({
      error: 'Failed to create checkout',
      details: error.response?.data || error.message
    });
  }
});

app.post('/webhook/paddle', async (req, res) => {
  try {
    const signatureHeader = req.headers['paddle-signature'];
    
    if (!signatureHeader) {
      console.warn('Missing Paddle signature header');
    }

    const ts = req.headers['paddle-ts'];
    const rawBody = req.rawBody || JSON.stringify(req.body);

    if (PADDLE_WEBHOOK_SECRET && signatureHeader) {
      const signatureData = extractPaddleSignature(signatureHeader);
      const signature = signatureData.h1;
      
      const isValid = verifyPaddleSignature(rawBody, signature, ts, PADDLE_WEBHOOK_SECRET);
      if (!isValid) {
        console.error('Invalid Paddle signature');
        return res.status(401).json({ error: 'Invalid signature' });
      }
      console.log('✓ Signature verified');
    }

    const eventData = req.body;

    console.log('Received webhook event:', eventData.event_type);

    if (eventData.event_type === 'transaction.completed') {
      const transaction = eventData.data;
      
      const paymentData = {
        transaction_id: transaction.id,
        customer_email: transaction.customer?.email,
        amount: transaction.details?.totals?.total / 100,
        currency: transaction.currency,
        status: transaction.status,
        created_at: transaction.created_at,
        product: transaction.custom_data?.product || 'TenantLease'
      };

      console.log('Transaction completed:', paymentData);
      
      await saveTransactionToDatabase(paymentData);
    }

    res.status(200).json({ received: true });

  } catch (error) {
    console.error('Webhook error:', error);
    res.status(500).json({ error: 'Webhook processing failed' });
  }
});

async function saveTransactionToDatabase(transactionData) {
  try {
    const stmt = db.prepare(`
      INSERT OR REPLACE INTO transactions 
      (transaction_id, customer_email, amount, currency, status, product, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);

    return new Promise((resolve, reject) => {
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
            console.log(`✓ Transaction saved: ${transactionData.transaction_id}`);
            resolve({ id: this.lastID, ...transactionData });
          }
        }
      );
      stmt.finalize();
    });
  } catch (error) {
    console.error('Database save error:', error);
    throw error;
  }
}

app.get('/api/transactions/:email', async (req, res) => {
  try {
    const { email } = req.params;
    
    const transactions = await new Promise((resolve, reject) => {
      db.all(
        'SELECT * FROM transactions WHERE customer_email = ? ORDER BY created_at DESC',
        [email],
        (err, rows) => {
          if (err) reject(err);
          else resolve(rows);
        }
      );
    });

    res.json({ transactions });
  } catch (error) {
    console.error('Get transactions error:', error);
    res.status(500).json({ error: 'Failed to retrieve transactions' });
  }
});

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', service: 'paddle-payment' });
});

app.listen(PORT, () => {
  console.log(`🚀 Paddle payment server running on port ${PORT}`);
  console.log(`📧 Checkout endpoint: http://localhost:${PORT}/api/checkout`);
  console.log(`🪝 Webhook endpoint: http://localhost:${PORT}/webhook/paddle`);
  console.log(`💰 Price ID: ${PADDLE_PRICE_ID}`);
});

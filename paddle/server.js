require('dotenv').config();
const express = require('express');
const cors = require('cors');
const fetch = require('node-fetch');
const crypto = require('crypto');

const app = express();
app.use(cors());
app.use(express.json());

app.post('/api/checkout', async (req, res) => {
  const { email, user_id } = req.body;
  
  console.log('\n=== CHECKOUT REQUEST ===');
  console.log('Email:', email);
  console.log('User ID:', user_id);
  console.log('Price ID:', process.env.PRICE_ID);
  console.log('API Key (first 20 chars):', process.env.PADDLE_API_KEY?.substring(0, 20) + '...');
  
  try {
    const requestBody = {
      items: [{ 
        price_id: process.env.PRICE_ID, 
        quantity: 1 
      }],
      customer: { 
        email: email 
      },
      custom_data: { 
        user_id: user_id || 'guest' 
      }
    };
    
    console.log('\n=== PADDLE API REQUEST ===');
    console.log('URL: https://api.paddle.com/v1/checkout');
    console.log('Method: POST');
    console.log('Request Body:', JSON.stringify(requestBody, null, 2));

    const response = await fetch('https://api.paddle.com/transactions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.PADDLE_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        items: [{ price_id: process.env.PRICE_ID, quantity: 1 }],
        customer: { email },
        custom_data: { user_id: user_id || 'guest' }
      })
    });

    const responseText = await response.text();
    console.log('Paddle Response Status:', response.status);
    console.log('Paddle Response Body:', responseText);

    if (!response.ok) {
      return res.status(response.status).json({
        success: false,
        error: `Paddle API error: ${response.statusText}`,
        details: responseText
      });
    }

    const data = JSON.parse(responseText);

    if (data.data) {
      console.log('\n=== SUCCESS ===');
      console.log('Checkout URL:', data.data.checkout_url);
      res.json({
        success: true,
        checkout_url: data.data.checkout_url,
        transaction_id: data.data.id
      });
    } else {
      console.log('\n=== ERROR ===');
      console.log('Error Detail:', data.error?.detail || data);
      res.status(400).json({
        success: false,
        error: data.error?.detail || data.errors?.[0]?.detail || 'Unknown error',
        paddle_response: data
      });
    }
  } catch (error) {
    console.error('Error:', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});

function verifyPaddleWebhook(signature, rawBody, secret) {
  if (!secret) {
    console.warn('⚠️  PADDLE_WEBHOOK_SECRET not configured, skipping signature verification');
    return true;
  }

  try {
    const parts = signature.split(',');
    const timestampPart = parts.find(p => p.startsWith('ts='));
    const hmacPart = parts.find(p => p.startsWith('hmac='));

    if (!timestampPart || !hmacPart) {
      console.error('Invalid signature format');
      return false;
    }

    const timestamp = timestampPart.split('=')[1];
    const receivedHmac = hmacPart.split('=')[1];

    const payload = timestamp + '.' + rawBody;
    const expectedHmac = crypto
      .createHmac('sha256', secret)
      .update(payload)
      .digest('hex');

    if (receivedHmac !== expectedHmac) {
      console.error('HMAC verification failed');
      return false;
    }

    const now = Math.floor(Date.now() / 1000);
    if (Math.abs(now - parseInt(timestamp)) > 300) {
      console.error('Timestamp is too old');
      return false;
    }

    return true;
  } catch (error) {
    console.error('Signature verification error:', error);
    return false;
  }
}

app.post('/webhook/paddle', async (req, res) => {
  console.log('\n=== WEBHOOK RECEIVED ===');
  const signature = req.headers['paddle-signature'];
  const rawBody = JSON.stringify(req.body);
  const secret = process.env.PADDLE_WEBHOOK_SECRET;

  if (!verifyPaddleWebhook(signature, rawBody, secret)) {
    console.error('❌ Webhook signature verification failed');
    return res.status(401).json({ error: 'Invalid signature' });
  }

  console.log('✅ Signature verified');

  const event = req.body;
  console.log('Event ID:', event.event_id);
  console.log('Event Type:', event.event_type);

  if (event.event_type === 'payment.succeeded') {
    const data = event.data;
    console.log('💰 Payment succeeded!');
    console.log('Transaction ID:', data.id);
    console.log('Customer ID:', data.customer_id);
    console.log('Amount:', data.amount);
    console.log('Currency:', data.currency);
    console.log('Customer Email:', data.customer?.email);
    console.log('Custom Data:', data.custom_data);

    try {
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

      res.status(200).json({ received: true });
    } catch (error) {
      console.error('❌ Error processing payment.succeeded:', error);
      res.status(500).json({ error: 'Failed to process webhook' });
    }
  } else {
    console.log('ℹ️  Received event:', event.event_type);
    res.status(200).json({ received: true });
  }

  console.log('=== WEBHOOK PROCESSING COMPLETE ===\n');
});

app.listen(process.env.PORT, () => {
  console.log(`\n🚀 Server running on http://localhost:${process.env.PORT}`);
  console.log(`📡 Checkout endpoint: http://localhost:${process.env.PORT}/api/checkout`);
  console.log(`🪝 Webhook endpoint: http://localhost:${process.env.PORT}/webhook/paddle`);
  console.log(`💚 Health check: http://localhost:${process.env.PORT}/health\n`);
  console.log(`🔐 PADDLE_WEBHOOK_SECRET configured: ${!!process.env.PADDLE_WEBHOOK_SECRET}`);
});

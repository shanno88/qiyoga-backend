#!/usr/bin/env node

/**
 * Test script for Paddle webhook endpoint
 * Usage: node test-webhook.js <webhook-url>
 * Example: node test-webhook.js http://localhost:3001/webhook/paddle
 */

const crypto = require('crypto');

// Test webhook payload (payment.succeeded event)
const testPayload = {
  event_id: 'evt_01kgrhp2wrthebpgwmn8eh5ssy',
  event_type: 'payment.succeeded',
  occurred_at: new Date().toISOString(),
  data: {
    id: 'txn_test_123456',
    customer_id: 'ctm_test_789012',
    amount: '9.90',
    currency: 'USD',
    status: 'completed',
    customer: {
      id: 'ctm_test_789012',
      email: 'test@example.com',
      name: 'Test User'
    },
    custom_data: {
      user_id: 'test_user_123'
    },
    items: [
      {
        price_id: 'pri_01kgrhp2wrthebpgwmn8eh5ssy',
        quantity: 1
      }
    ]
  }
};

// Generate Paddle signature
function generateSignature(payload, secret) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const rawBody = JSON.stringify(payload);
  const payloadString = timestamp + '.' + rawBody;
  
  const hmac = crypto
    .createHmac('sha256', secret)
    .update(payloadString)
    .digest('hex');
  
  return `ts=${timestamp},hmac=${hmac}`;
}

// Main test function
async function testWebhook(webhookUrl) {
  const secret = process.env.PADDLE_WEBHOOK_SECRET || 'test_secret';
  
  console.log('🧪 Testing Paddle Webhook Endpoint');
  console.log('📍 Target URL:', webhookUrl);
  console.log('🔑 Using secret:', secret === 'test_secret' ? 'test_secret (default)' : 'configured secret\n');
  
  // Generate signature
  const signature = generateSignature(testPayload, secret);
  console.log('🔐 Generated signature:', signature.substring(0, 50) + '...');
  
  try {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Paddle-Signature': signature
      },
      body: JSON.stringify(testPayload)
    });
    
    console.log('\n📤 Response Status:', response.status, response.statusText);
    
    const responseText = await response.text();
    console.log('📥 Response Body:', responseText);
    
    if (response.ok) {
      console.log('\n✅ Webhook test PASSED');
    } else {
      console.log('\n❌ Webhook test FAILED');
      process.exit(1);
    }
  } catch (error) {
    console.error('\n❌ Error testing webhook:', error.message);
    process.exit(1);
  }
}

// Parse command line arguments
const webhookUrl = process.argv[2] || 'http://localhost:3001/webhook/paddle';

if (!webhookUrl) {
  console.error('❌ Please provide webhook URL');
  console.log('Usage: node test-webhook.js <webhook-url>');
  console.log('Example: node test-webhook.js http://localhost:3001/webhook/paddle');
  process.exit(1);
}

// Run test
testWebhook(webhookUrl);

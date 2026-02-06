const crypto = require('crypto');

async function testSignatureVerification() {
  const secret = 'test_secret_123';
  const timestamp = Date.now().toString();
  const payload = {
    event_type: 'transaction.completed',
    data: {
      id: 'txn_test_123',
      amount: 990
    }
  };

  console.log('Testing Paddle signature verification...\n');

  const signature = getPaddleSignature(payload, timestamp, secret);
  console.log('Generated signature:', signature);

  const header = `ts=${timestamp};h1="${signature}"`;
  console.log('Header:', header);

  const extracted = extractPaddleSignature(header);
  console.log('Extracted:', extracted);

  const isValid = verifyPaddleSignature(payload, signature, timestamp, secret);
  console.log('\nVerification result:', isValid ? '✓ Valid' : '✗ Invalid');

  const invalidSecret = 'wrong_secret';
  const isInvalid = verifyPaddleSignature(payload, signature, timestamp, invalidSecret);
  console.log('With wrong secret:', isInvalid ? '✗ Should be invalid' : '✓ Correctly invalid');
}

function getPaddleSignature(payload, timestamp, secret) {
  const payloadString = typeof payload === 'string' ? payload : JSON.stringify(payload);
  const signedPayload = `${timestamp}:${payloadString}`;
  
  return crypto
    .createHmac('sha256', secret)
    .update(signedPayload)
    .digest('hex');
}

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

testSignatureVerification();

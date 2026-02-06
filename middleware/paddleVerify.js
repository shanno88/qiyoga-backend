const crypto = require('crypto');

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

module.exports = (req, res, next) => {
  const signature = req.headers['paddle-signature'];
  const rawBody = JSON.stringify(req.body);
  const secret = process.env.PADDLE_WEBHOOK_SECRET;

  if (!verifyPaddleWebhook(signature, rawBody, secret)) {
    console.error('❌ Webhook signature verification failed');
    return res.status(401).json({ error: 'Invalid signature' });
  }

  console.log('✅ Signature verified');
  next();
};

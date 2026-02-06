import crypto from 'crypto';

export function verifyPaddleSignature(payload, signature, timestamp, secret) {
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

export function getPaddleSignature(payload, timestamp, secret) {
  const payloadString = typeof payload === 'string' ? payload : JSON.stringify(payload);
  const signedPayload = `${timestamp}:${payloadString}`;
  
  return crypto
    .createHmac('sha256', secret)
    .update(signedPayload)
    .digest('hex');
}

export function extractPaddleSignature(header) {
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

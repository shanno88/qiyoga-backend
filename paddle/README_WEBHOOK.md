# Paddle Webhook Setup Guide

## Overview

This Express server handles Paddle Billing webhooks for payment notifications.

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required variables:
- `PADDLE_API_KEY` - Your Paddle Billing API key
- `PRODUCT_ID` - Your Paddle product ID
- `PRICE_ID` - Your Paddle price ID
- `PADDLE_WEBHOOK_SECRET` - Your Paddle webhook signing secret
- `PORT` - Server port (default: 3001)

## Getting Webhook Secret

1. Go to [Paddle Developer Portal](https://developers.paddle.com)
2. Navigate to Settings → Notifications
3. Create a new webhook or view existing webhook
4. Copy the "Signing Secret" value

## Webhook URL

Once deployed, your webhook URL will be:

```
https://your-railway-domain.railway.app/webhook/paddle
```

## Running Locally

```bash
# Install dependencies
npm install

# Set environment variables (or use .env file)
export PADDLE_API_KEY=your_api_key
export PRODUCT_ID=your_product_id
export PRICE_ID=your_price_id
export PADDLE_WEBHOOK_SECRET=your_webhook_secret
export PORT=3001

# Start server
npm run dev
```

Or with .env file:

```bash
npm run dev
```

## API Endpoints

### POST /api/checkout
Create a Paddle checkout session.

Request:
```json
{
  "email": "customer@example.com",
  "user_id": "optional_user_id"
}
```

Response:
```json
{
  "success": true,
  "checkout_url": "https://checkout.paddle.com/...",
  "transaction_id": "txn_..."
}
```

### POST /webhook/paddle
Receive Paddle webhook notifications.

This endpoint:
- Verifies webhook signature using HMAC-SHA256
- Handles `payment.succeeded` events
- Logs transaction details
- Returns 200 to acknowledge receipt

### GET /health
Health check endpoint.

Response:
```json
{
  "status": "ok",
  "message": "Server is running"
}
```

## Webhook Events Handled

- `payment.succeeded` - Payment completed successfully
  - Logs transaction ID
  - Logs customer email
  - Logs custom data

## Signature Verification

The webhook endpoint verifies Paddle signatures using HMAC-SHA256:

1. Extracts `Paddle-Signature` header
2. Parses timestamp and HMAC values
3. Verifies HMAC using the webhook secret
4. Checks timestamp is within 5 minutes
5. Rejects invalid signatures with 401 status

## Logging

All webhook events are logged with detailed information:

- Event ID
- Event type
- Transaction details
- Customer information
- Custom data

## Testing Webhooks Locally

Use ngrok to expose your local server:

```bash
# Install ngrok
npm install -g ngrok

# Start your server
npm run dev

# In another terminal, expose port 3001
ngrok http 3001
```

Use the ngrok URL (e.g., `https://abc123.ngrok.io/webhook/paddle`) in Paddle webhook settings.

## Deployment

Deploy to Railway, Render, or any Node.js hosting service:

1. Push code to Git repository
2. Connect repository to hosting platform
3. Configure environment variables
4. Deploy
5. Update Paddle webhook URL with your deployed URL

## Security Notes

- Always use HTTPS in production
- Keep `PADDLE_WEBHOOK_SECRET` secure
- Never commit `.env` files to version control
- Verify webhook signatures on all endpoints
- Use environment-specific secrets (sandbox vs production)

## Troubleshooting

### Webhook not firing
- Check webhook URL is correct
- Verify webhook is active in Paddle dashboard
- Check server logs for incoming requests

### Signature verification failing
- Verify `PADDLE_WEBHOOK_SECRET` is correct
- Check timestamp is not too old
- Ensure request body is not modified

### 404 errors
- Verify webhook URL path: `/webhook/paddle`
- Check server is running and accessible

## Support

For issues:
1. Check server logs
2. Verify Paddle dashboard webhook settings
3. Test with Paddle webhook testing tools

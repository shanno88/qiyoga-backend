# QiYoga Backend Service

Backend service for qiyoga.xyz, handling Paddle webhooks and PDF OCR.

## Features

- **Paddle Webhook Handler**: Receives and processes payment notifications
- **PDF OCR**: Extracts text from PDF lease documents
- **Secure Signature Verification**: Validates Paddle webhook signatures
- **CORS Support**: Configured for qiyoga.xyz

## Project Structure

```
backend/
├── server.js              # Express main server
├── routes/
│   ├── webhooks.js        # Paddle webhook handling
│   └── ocr.js             # PDF text extraction endpoint
├── middleware/
│   └── paddleVerify.js    # Paddle signature verification
├── utils/
│   └── pdfParser.js       # PDF parsing utilities
├── package.json
├── railway.json
├── Procfile
├── .env.example
├── .gitignore
└── README.md
```

## API Endpoints

### Health Check
```
GET /health
```
Returns server health status.

### Paddle Webhook
```
POST /webhook/paddle
```
Receives Paddle webhook notifications. Automatically verifies signature.

### PDF OCR
```
POST /api/lease/analyze
Content-Type: multipart/form-data
```
Upload a PDF file to extract text.

**Request:**
- Form field: `file` (PDF, max 5MB)

**Response:**
```json
{
  "success": true,
  "text": "Extracted PDF text",
  "info": {
    "pages": 10,
    "info": {...}
  }
}
```

## Environment Variables

Create a `.env` file from `.env.example`:

```bash
PORT=3001
PADDLE_WEBHOOK_SECRET=your_webhook_secret_here
ALLOWED_ORIGINS=https://qiyoga.xyz,http://localhost:5173
```

### Getting PADDLE_WEBHOOK_SECRET

1. Go to [Paddle Developer Portal](https://developers.paddle.com)
2. Navigate to Settings → Notifications
3. Create a webhook or edit existing
4. Copy the "Signing Secret"

## Installation

```bash
cd backend
npm install
```

## Local Development

```bash
# Copy environment variables
cp .env.example .env

# Edit .env with your values
# vim .env

# Start server
npm run dev
# Or
npm start
```

## Testing

### Test Health Endpoint
```bash
curl http://localhost:3001/health
```

### Test OCR Endpoint
```bash
curl -X POST http://localhost:3001/api/lease/analyze \
  -F "file=@lease.pdf"
```

### Test Webhook
```bash
curl -X POST http://localhost:3001/webhook/paddle \
  -H "Content-Type: application/json" \
  -H "Paddle-Signature: ts=1234567890,hmac=..." \
  -d '{
    "event_id": "evt_test",
    "event_type": "transaction.completed",
    "data": {
      "id": "txn_test",
      "customer_id": "ctm_test",
      "amount": "9.90"
    }
  }'
```

## Railway Deployment

### Prerequisites
- Railway CLI installed: `npm install -g @railway/cli`
- Git repository with this code

### Deploy Steps

1. **Login to Railway**
   ```bash
   railway login
   ```

2. **Initialize Project**
   ```bash
   cd backend
   railway init
   ```

3. **Deploy**
   ```bash
   railway up
   ```

4. **Set Environment Variables**

   Go to your Railway project → Variables tab and add:
   ```
   PORT=3001
   PADDLE_WEBHOOK_SECRET=<your-webhook-secret>
   ALLOWED_ORIGINS=https://qiyoga.xyz
   ```

5. **Get Your Railway Domain**

   Railway will provide a domain like:
   ```
   https://qiyoga-backend-production.up.railway.app
   ```

6. **Update Paddle Webhook URL**

   In Paddle Developer Portal, set webhook URL to:
   ```
   https://qiyoga-backend-production.up.railway.app/webhook/paddle
   ```

### Railway Configuration

The project includes:
- `railway.json` - Railway configuration
- `Procfile` - Process file for deployment
- `package.json` - Dependencies and scripts

## Paddle Configuration

Configure your Paddle credentials in the `.env` file:

- **Seller ID**: Your Paddle seller ID
- **Client-side Token**: Your Paddle client-side token (from Paddle Dashboard)
- **Price ID**: Your price ID
- **Product ID**: Your product ID

### Webhook Events

Configure these events in Paddle:
- `transaction.completed`
- `payment.succeeded`

## Security

- ✅ Webhook signature verification (HMAC-SHA256)
- ✅ Timestamp validation (5-minute window)
- ✅ CORS configured for allowed origins
- ✅ Environment variables for sensitive data
- ✅ .env in .gitignore

## Monitoring

- Check Railway logs for real-time monitoring
- Monitor webhook deliveries in Paddle Dashboard
- Set up error tracking (e.g., Sentry) for production

## Troubleshooting

### Webhook not firing
- Check webhook URL in Paddle Dashboard
- Verify Railway service is running
- Check Railway logs for errors

### Signature verification failing
- Verify `PADDLE_WEBHOOK_SECRET` is correct
- Check webhook secret matches Paddle Dashboard
- Ensure request body is not modified

### OCR not working
- Ensure file is PDF format
- Check file size is under 5MB
- Verify multer configuration

### 404 errors
- Verify endpoint paths are correct:
  - `/webhook/paddle`
  - `/api/lease/analyze`
  - `/health`
- Check server is running on correct port

## Production Checklist

- [ ] Deployed to Railway
- [ ] All environment variables configured
- [ ] `PADDLE_WEBHOOK_SECRET` set
- [ ] Paddle webhook URL updated
- [ ] Custom domain configured (optional)
- [ ] CORS origins set correctly
- [ ] Health endpoint working
- [ ] Tested payment webhook
- [ ] Tested OCR functionality
- [ ] Error monitoring setup
- [ ] Logs configured and monitored

## Support

- Paddle Documentation: https://developer.paddle.com
- Railway Documentation: https://docs.railway.app
- Check Railway logs for detailed error messages

## License

MIT

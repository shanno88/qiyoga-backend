# Paddle Payment Integration for QiYoga

## Installation

1. Navigate to the paddle directory:
```bash
cd backend/paddle
```

2. Install dependencies:
```bash
npm install
```

3. Configure environment variables in `.env`:
```
PADDLE_API_KEY=your_api_key_here
PADDLE_API_URL=https://api.paddle.com
PADDLE_PRODUCT_ID=pro_01kgrhkyabt3244vn6hqgj3ype
PADDLE_PRICE_ID=pri_01kgrhp2wrthebpgwmn8eh5ssy
PADDLE_WEBHOOK_SECRET=your_webhook_secret_from_paddle
PORT=3001
FRONTEND_URL=https://qiyoga.xyz
```

## Running the Server

Development mode:
```bash
npm run dev
```

Production mode:
```bash
npm start
```

The server will start on `http://localhost:3001`

## API Endpoints

### POST /api/checkout
Create a Paddle checkout session.

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "checkout_url": "https://checkout.paddle.com/checkout/...",
  "checkout_id": "chk_xxxx"
}
```

### POST /webhook/paddle
Handle Paddle webhook events.

**Headers:**
- `paddle-signature`: Paddle signature for verification
- `paddle-ts`: Timestamp for signature verification

**Supported Events:**
- `transaction.completed`: Saves transaction data to database

## Frontend Integration

Import and use the `PaddleCheckoutButton` component:

```tsx
import PaddleCheckoutButton from './components/PaddleCheckoutButton';

function PurchasePage() {
  const [email, setEmail] = useState('');

  return (
    <div>
      <input 
        type="email" 
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Enter your email"
      />
      <PaddleCheckoutButton 
        email={email}
        onPaymentStart={() => console.log('Payment started')}
        onPaymentComplete={(data) => console.log('Payment complete:', data)}
        onPaymentError={(error) => console.error('Payment error:', error)}
      />
    </div>
  );
}
```

## Webhook Setup

1. In your Paddle dashboard, navigate to Developer Tools > Webhooks
2. Create a new webhook with URL: `https://qiyoga.xyz/webhook/paddle`
3. Subscribe to events: `transaction.completed`
4. Copy the webhook secret and set it in `.env` as `PADDLE_WEBHOOK_SECRET`

## Database Integration

To save transactions to a real database, modify the `saveTransactionToDatabase` function in `server.js`:

```javascript
async function saveTransactionToDatabase(transactionData) {
  const db = await getDatabaseConnection();
  await db.query(
    'INSERT INTO transactions (transaction_id, email, amount, status) VALUES (?, ?, ?, ?)',
    [transactionData.transaction_id, transactionData.customer_email, transactionData.amount, transactionData.status]
  );
}
```

## Production Deployment

1. Set `PADDLE_ENV=production` in your environment
2. Use a process manager like PM2:
```bash
npm install -g pm2
pm2 start server.js --name paddle-payment
pm2 save
pm2 startup
```

3. Configure your reverse proxy (nginx) to forward requests to port 3001

## Testing

Use Paddle's sandbox environment for testing:
- Set `PADDLE_API_URL=https://sandbox-api.paddle.com`
- Use your sandbox API key
- Test cards available at: https://developer.paddle.com/testing/test-cards

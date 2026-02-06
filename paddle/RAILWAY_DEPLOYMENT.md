# Railway Deployment Guide

## Quick Start

1. **Prepare Your Git Repository**
   ```bash
   cd backend/paddle
   git init
   git add .
   git commit -m "Add Paddle webhook backend"
   ```

2. **Push to GitHub/GitLab**
   ```bash
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

3. **Deploy to Railway**
   - Go to [railway.app](https://railway.app)
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway will auto-detect it's a Node.js project

## Configuration

After deployment, add environment variables in Railway:

1. Open your Railway project
2. Go to "Variables" tab
3. Add these variables:

   ```
   PADDLE_API_KEY=your_live_api_key_here
   PRODUCT_ID=pro_01kgrhkyabt3244vn6hqgj3ype
   PRICE_ID=pri_01kgrhp2wrthebpgwmn8eh5ssy
   PADDLE_WEBHOOK_SECRET=<get-from-paddle>
   PORT=3001
   ```

4. Redeploy to apply changes

## Get Webhook Secret

1. Go to [Paddle Developer Portal](https://developers.paddle.com)
2. Navigate to Settings → Notifications
3. Click "Create webhook" or edit existing
4. Copy "Signing Secret"
5. Add to Railway environment variables

## Configure Paddle Webhook

1. In Paddle Developer Portal, set webhook URL:
   ```
   https://your-railway-domain.railway.app/webhook/paddle
   ```

2. Select events to receive:
   - `payment.succeeded`
   - `subscription.created` (if you add subscriptions)
   - `transaction.completed`

3. Save webhook settings

## Your Railway Domain

After deployment, Railway assigns a domain like:
```
https://qiyoga-paddle.up.railway.app
```

Your full webhook URL:
```
https://qiyoga-paddle.up.railway.app/webhook/paddle
```

## Verifying Deployment

```bash
# Check health
curl https://your-railway-domain.railway.app/health

# Should return:
# {"status":"ok","message":"Server is running"}
```

## Custom Domain (Optional)

1. Go to Railway project → Settings → Domains
2. Add custom domain (e.g., `api.qiyoga.xyz`)
3. Update DNS records as instructed
4. Update Paddle webhook URL to use custom domain

## Monitoring

- Railway provides logs for your deployed service
- Check logs in Railway dashboard
- Monitor webhook events in Paddle dashboard

## Troubleshooting

### Webhook not working
- Check webhook URL is correct
- Verify webhook is active in Paddle
- Check Railway logs for errors
- Test webhook with Paddle's test tool

### Environment variables missing
- Go to Railway project → Variables
- Ensure all required variables are set
- Redeploy after adding variables

### 404 on webhook endpoint
- Verify path is `/webhook/paddle`
- Check server logs
- Ensure no trailing slash in URL

## Production Checklist

- [ ] Railway deployment successful
- [ ] All environment variables configured
- [ ] PADDLE_WEBHOOK_SECRET set
- [ ] Custom domain configured (optional)
- [ ] Webhook URL configured in Paddle
- [ ] Health check endpoint working
- [ ] Test payment in production mode
- [ ] Logs monitored
- [ ] Error handling tested

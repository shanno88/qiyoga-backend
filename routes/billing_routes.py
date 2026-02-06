from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
import logging
from typing import Optional
import os
from datetime import datetime, timedelta

from services.paddle import (
    create_checkout,
    verify_webhook_signature,
    parse_webhook_event,
    PAYMENT_SUCCESS_EVENTS,
)
from routes.lease_routes import USER_ACCESS_STORE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


class CreateCheckoutRequest(BaseModel):
    user_id: str


class CheckoutResponse(BaseModel):
    success: bool
    checkout_url: Optional[str] = None
    transaction_id: Optional[str] = None
    error: Optional[str] = None


@router.post("/create-checkout", response_model=CheckoutResponse)
async def create_checkout_session(request: CreateCheckoutRequest):
    try:
        logger.info(f"Creating checkout for user_id: {request.user_id}")

        # Check if user already has valid access
        now = datetime.now()
        if request.user_id in USER_ACCESS_STORE:
            access = USER_ACCESS_STORE[request.user_id]
            if "expires_at" in access:
                expires_at = datetime.fromisoformat(access["expires_at"])
                if now < expires_at:
                    logger.info(
                        f"User {request.user_id} already has valid access until {expires_at}"
                    )
                    return CheckoutResponse(
                        success=True,
                        checkout_url=None,
                        transaction_id=None,
                        error=None,
                    )

        # Create Paddle checkout with user_id in metadata
        result = await create_checkout_for_user(request.user_id)

        logger.info(f"Checkout created successfully: {result['transaction_id']}")

        return CheckoutResponse(
            success=True,
            checkout_url=result["checkout_url"],
            transaction_id=result["transaction_id"],
        )

    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        return CheckoutResponse(
            success=False, error=f"Payment system configuration error: {str(e)}"
        )

    except Exception as e:
        logger.exception(f"Error creating checkout: {str(e)}")
        return CheckoutResponse(
            success=False, error=f"Failed to create checkout: {str(e)}"
        )


async def create_checkout_for_user(user_id: str) -> dict:
    """Create a Paddle checkout session for the given user"""
    import httpx

    config = {
        "vendor_id": os.getenv("PADDLE_VENDOR_ID"),
        "api_key": os.getenv("PADDLE_API_KEY"),
        "client_token": os.getenv("PADDLE_CLIENT_TOKEN"),
        "environment": os.getenv("PADDLE_ENV", "sandbox"),
        "price_id": os.getenv("PADDLE_PRICE_ID"),
    }

    if not all([config["price_id"], config["vendor_id"], config["api_key"]]):
        raise ValueError(
            "Paddle configuration is incomplete. Please set PADDLE_VENDOR_ID, PADDLE_API_KEY, and PADDLE_PRICE_ID in environment variables."
        )

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "items": [
            {
                "price_id": config["price_id"],
                "quantity": 1,
            }
        ],
        "customer_email": None,
        "custom_data": {
            "user_id": user_id,
        },
        "settings": {
            "display_name": "30-Day Unlimited Lease Analysis Access",
            "success_url": f"{os.getenv('FRONTEND_URL', 'https://qiyoga.xyz')}/#/billing/success?user_id={user_id}",
            "cancel_url": f"{os.getenv('FRONTEND_URL', 'https://qiyoga.xyz')}/#/pricing",
        },
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.paddle.com/transactions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(
                f"Created checkout for user_id: {user_id}, transaction_id: {data.get('data', {}).get('id')}"
            )

            return {
                "checkout_url": data["data"]["checkout_url"],
                "transaction_id": data["data"]["id"],
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Paddle API error: {e.response.status_code} - {e.response.text}"
            )
            raise Exception(f"Failed to create checkout: {e.response.text}")
        except Exception as e:
            logger.error(f"Unexpected error creating checkout: {str(e)}")
            raise Exception(f"Failed to create checkout: {str(e)}")


@router.post("/webhook")
async def paddle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Get signature from headers
        signature = request.headers.get("paddle_signature", "")
        if not signature:
            logger.warning("Webhook received without signature")
            raise HTTPException(status_code=401, detail="Missing signature")

        # Get API key for signature verification
        api_key = os.getenv("PADDLE_API_KEY")

        # Verify webhook signature
        if not await verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse event data
        event_data = await request.json()
        event_type, analysis_id, transaction_id, user_id = parse_webhook_event(
            event_data
        )

        logger.info(
            f"Received webhook: event_type={event_type}, analysis_id={analysis_id}, user_id={user_id}, transaction_id={transaction_id}"
        )

        # Process payment success events
        if event_type in PAYMENT_SUCCESS_EVENTS and user_id:
            now = datetime.now()
            expires_at = (now + timedelta(days=30)).isoformat()

            USER_ACCESS_STORE[user_id] = {
                "paid_at": now.isoformat(),
                "expires_at": expires_at,
                "analysis_ids": USER_ACCESS_STORE.get(user_id, {}).get(
                    "analysis_ids", []
                ),
            }

            logger.info(
                f"Activated 30-day access for user {user_id} until {expires_at}"
            )
        else:
            logger.warning(f"Invalid or missing user_id in webhook: {user_id}")

        # Acknowledge webhook
        return {"status": "success"}

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Webhook processing failed: {str(e)}"
        )


@router.get("/check-access")
async def check_user_access(
    user_id: str = Query(..., description="User ID from frontend session"),
):
    try:
        if user_id not in USER_ACCESS_STORE:
            return {
                "success": True,
                "has_access": False,
                "expires_at": None,
                "days_remaining": 0,
                "analyses_count": 0,
            }

        access = USER_ACCESS_STORE[user_id]
        now = datetime.now()

        if "expires_at" not in access:
            return {
                "success": True,
                "has_access": False,
                "expires_at": None,
                "days_remaining": 0,
                "analyses_count": len(access.get("analysis_ids", [])),
            }

        expires_at = datetime.fromisoformat(access["expires_at"])

        if now < expires_at:
            days_remaining = (expires_at - now).days
            return {
                "success": True,
                "has_access": True,
                "expires_at": access["expires_at"],
                "days_remaining": days_remaining,
                "analyses_count": len(access.get("analysis_ids", [])),
            }
        else:
            return {
                "success": True,
                "has_access": False,
                "expires_at": access["expires_at"],
                "days_remaining": 0,
                "analyses_count": len(access.get("analysis_ids", [])),
            }

    except Exception as e:
        logger.exception(f"Error checking access: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to check access: {str(e)}")


@router.get("/check-payment-status/{analysis_id}")
async def check_payment_status(analysis_id: str):
    """Legacy endpoint for backward compatibility"""
    try:
        from routes.lease_routes import ANALYSIS_STORE

        if analysis_id not in ANALYSIS_STORE:
            raise HTTPException(status_code=404, detail="Analysis not found")

        user_id = ANALYSIS_STORE[analysis_id].get("user_id")
        if not user_id:
            return {
                "success": True,
                "analysis_id": analysis_id,
                "paid": False,
            }

        if user_id not in USER_ACCESS_STORE:
            return {
                "success": True,
                "analysis_id": analysis_id,
                "paid": False,
            }

        access = USER_ACCESS_STORE[user_id]
        now = datetime.now()

        if "expires_at" in access:
            expires_at = datetime.fromisoformat(access["expires_at"])
            is_paid = now < expires_at
        else:
            is_paid = False

        return {
            "success": True,
            "analysis_id": analysis_id,
            "paid": is_paid,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error checking payment status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check payment status: {str(e)}"
        )

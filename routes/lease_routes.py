from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request
from pathlib import Path
import time
import logging
import uuid
from typing import List, Dict, Any
from datetime import datetime, timedelta
import random

from utils.file_handler import save_upload_file, cleanup_file
from utils.text_parser import extract_key_info
from services.ocr_service import get_ocr_service
from services.pdf_service import get_pdf_service

logger = logging.getLogger(__name__)

# In-memory storage for analysis results
ANALYSIS_STORE: Dict[str, Dict[str, Any]] = {}
USER_ACCESS_STORE: Dict[str, Dict[str, Any]] = {}

router = APIRouter(tags=["lease"])


def generate_sample_clauses(full_text: str) -> List[Dict[str, Any]]:
    """Generate sample clause analyses from the lease text (placeholder implementation)"""
    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

    # If we don't have enough paragraphs, split by sentences
    if len(paragraphs) < 5:
        sentences = [s.strip() for s in full_text.split(".") if s.strip()]
        paragraphs = sentences

    num_clauses = min(len(paragraphs), random.randint(15, 20))
    clauses = []

    risk_levels = ["safe", "caution", "danger"]
    risk_weights = [0.5, 0.35, 0.15]

    for i in range(num_clauses):
        paragraph_idx = i % len(paragraphs)
        clause_text = paragraphs[paragraph_idx][:200]  # Limit to 200 chars

        risk_level = random.choices(risk_levels, weights=risk_weights)[0]

        if risk_level == "safe":
            analysis = "This is a standard clause that follows typical rental agreement practices."
            suggestion = "No action needed. This protects both parties fairly."
        elif risk_level == "caution":
            analysis = "This clause contains some language that could be interpreted in multiple ways."
            suggestion = (
                "Consider clarifying the terms with your landlord before signing."
            )
        else:
            analysis = "This clause potentially shifts legal responsibilities away from the landlord."
            suggestion = "Negotiate to limit your liability or seek legal counsel before signing."

        clauses.append(
            {
                "clause_number": i + 1,
                "clause_text": clause_text,
                "risk_level": risk_level,
                "analysis": analysis,
                "suggestion": suggestion,
            }
        )

    return clauses


def check_user_access(user_id: str) -> Dict[str, Any]:
    """Check if user has valid 30-day access"""
    if user_id not in USER_ACCESS_STORE:
        return {"has_access": False}

    access = USER_ACCESS_STORE[user_id]
    now = datetime.now()
    expires_at = datetime.fromisoformat(access["expires_at"])

    if now < expires_at:
        days_remaining = (expires_at - now).days
        return {
            "has_access": True,
            "expires_at": access["expires_at"],
            "days_remaining": days_remaining,
            "analyses_count": len(access.get("analysis_ids", [])),
        }
    else:
        return {"has_access": False}


@router.post("/analyze")
async def analyze_lease(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID from frontend session"),
):
    start_time = time.time()
    uploaded_file_path = None
    temp_image_paths = []

    try:
        logger.info(
            f"Starting lease analysis for file: {file.filename}, user_id: {user_id}"
        )

        uploaded_file_path = await save_upload_file(file)
        uploaded_path = Path(uploaded_file_path)

        pdf_service = get_pdf_service()
        ocr_service = get_ocr_service()

        image_paths = []

        if pdf_service.is_pdf(uploaded_path):
            logger.info("Processing PDF file")
            image_paths = pdf_service.pdf_to_images(uploaded_path)
            temp_image_paths = image_paths
        elif pdf_service.is_image(uploaded_path):
            logger.info("Processing image file")
            image_paths = [uploaded_path]
        else:
            logger.error(f"Unsupported file format: {uploaded_path.suffix}")
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload PDF or image files.",
            )

        if not image_paths:
            logger.error("No pages found in the document")
            raise HTTPException(
                status_code=400, detail="No pages found in the document"
            )

        logger.info(f"Found {len(image_paths)} image(s) to process")
        ocr_result = ocr_service.recognize_images(image_paths)

        if not ocr_result or not ocr_result.get("full_text"):
            logger.error("OCR returned empty or invalid result")
            return {
                "success": False,
                "error": "No text extracted from document. The document may be empty, contain only images, or have formatting issues.",
            }

        full_text = ocr_result.get("full_text", "")

        if not full_text or not full_text.strip():
            logger.error("OCR returned empty text")
            return {
                "success": False,
                "error": "No text extracted from document. The document may be empty or contain only images.",
            }

        logger.info(f"Extracted {len(full_text)} characters from document")
        key_info = extract_key_info(full_text)

        # Generate all clause analyses
        all_clauses = generate_sample_clauses(full_text)

        # Check if user has valid access
        access_info = check_user_access(user_id)
        has_full_access = access_info["has_access"]

        # Determine how many clauses to show
        if has_full_access:
            shown_clauses = all_clauses
        else:
            shown_clauses = all_clauses[:5]

        processing_time = time.time() - start_time

        logger.info(f"Lease analysis completed successfully in {processing_time:.2f}s")

        # Generate unique analysis_id and store the result
        analysis_id = str(uuid.uuid4())
        ANALYSIS_STORE[analysis_id] = {
            "full_text": full_text,
            "key_info": key_info,
            "all_clauses": all_clauses,
            "lines": [
                {"text": line["text"], "confidence": line["confidence"]}
                for line in ocr_result.get("lines", [])
            ],
            "processing_time": round(processing_time, 2),
            "page_count": ocr_result.get("page_count", 0),
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
        }

        # Track this analysis for the user
        if user_id not in USER_ACCESS_STORE:
            USER_ACCESS_STORE[user_id] = {"analysis_ids": []}
        if analysis_id not in USER_ACCESS_STORE[user_id]["analysis_ids"]:
            USER_ACCESS_STORE[user_id]["analysis_ids"].append(analysis_id)

        logger.info(f"Stored analysis with ID: {analysis_id} for user: {user_id}")

        return {
            "success": True,
            "data": {
                "analysis_id": analysis_id,
                "full_text": full_text,
                "key_info": key_info,
                "clauses": shown_clauses,
                "total_clauses": len(all_clauses),
                "shown_clauses": len(shown_clauses),
                "has_full_access": has_full_access,
                "user_id": user_id,
                "lines": [
                    {"text": line["text"], "confidence": line["confidence"]}
                    for line in ocr_result.get("lines", [])
                ],
                "processing_time": round(processing_time, 2),
                "page_count": ocr_result.get("page_count", 0),
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Unexpected error during lease analysis: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to analyze lease: {str(e)}",
        }

    finally:
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)

        for temp_path in temp_image_paths:
            cleanup_file(temp_path)


@router.get("/health")
async def health_check():
    try:
        return {
            "status": "healthy",
            "service": "lease-ocr-api",
            "message": "API is running correctly",
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


@router.get("/full-report")
async def get_full_report(
    analysis_id: str = Query(..., description="Analysis ID from OCR"),
    user_id: str = Query(..., description="User ID from frontend session"),
):
    try:
        logger.info(
            f"Requesting full report for analysis_id: {analysis_id}, user_id: {user_id}"
        )

        if analysis_id not in ANALYSIS_STORE:
            logger.warning(f"Analysis ID not found: {analysis_id}")
            raise HTTPException(
                status_code=404,
                detail="Analysis not found. Please analyze a lease first.",
            )

        analysis = ANALYSIS_STORE[analysis_id]

        # Check if the analysis belongs to this user
        if analysis.get("user_id") != user_id:
            # Or check if the user has valid access
            access_info = check_user_access(user_id)
            if not access_info["has_access"]:
                logger.warning(
                    f"User {user_id} does not have access to analysis {analysis_id}"
                )
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. This analysis belongs to another user or your access has expired.",
                )

        logger.info(f"Returning full report for analysis: {analysis_id}")

        return {
            "success": True,
            "data": {
                "analysis_id": analysis_id,
                "full_text": analysis["full_text"],
                "key_info": analysis["key_info"],
                "clauses": analysis["all_clauses"],
                "total_clauses": len(analysis["all_clauses"]),
                "shown_clauses": len(analysis["all_clauses"]),
                "has_full_access": check_user_access(user_id)["has_access"],
                "user_id": user_id,
                "lines": analysis["lines"],
                "processing_time": analysis["processing_time"],
                "page_count": analysis["page_count"],
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error retrieving full report: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve full report: {str(e)}"
        )


def analyze_single_clause(clause_text: str) -> "tuple[str, str, str]":
    """
    Based on keyword rules to analyze a single clause
    Returns: (risk_level, analysis, suggestion)
    """
    text_lower = clause_text.lower()

    # High risk keywords
    high_risk_keywords = [
        "tenant responsible for all",
        "regardless of fault",
        "waive any right",
        "landlord may enter at any time",
        "no refund",
        "tenant liable for",
        "cannot terminate",
        "automatic renewal",
    ]

    # Medium risk keywords
    medium_risk_keywords = [
        "late fee",
        "additional charges",
        "landlord discretion",
        "may be charged",
        "tenant must pay",
        "non-refundable",
    ]

    # Check for high risk
    for keyword in high_risk_keywords:
        if keyword in text_lower:
            if "all" in text_lower and (
                "repair" in text_lower or "maintenance" in text_lower
            ):
                return (
                    "danger",
                    "This clause shifts all maintenance responsibility to you, regardless of fault. This is unusual and potentially unfair.",
                    "Request to limit your responsibility to damages caused by tenant negligence only. Standard leases don't make tenants responsible for normal wear and tear or structural issues.",
                )
            elif "enter" in text_lower and "any time" in text_lower:
                return (
                    "danger",
                    "This allows landlord unrestricted access to your apartment. Most jurisdictions require 24-48 hours notice except for emergencies.",
                    "Request specific language: 'Landlord may enter with 24-48 hours written notice, except in emergencies.'",
                )
            elif "waive" in text_lower:
                return (
                    "danger",
                    "Waiving rights can leave you without legal protection. This type of clause may not be enforceable in many states.",
                    "Consult a local tenant rights organization before signing. You may not be able to legally waive certain rights.",
                )
            else:
                return (
                    "danger",
                    "This clause contains language that may heavily favor landlord and limit your rights as a tenant.",
                    "Have a lawyer review this specific clause before signing, or request it be removed or modified.",
                )

    # Check for medium risk
    for keyword in medium_risk_keywords:
        if keyword in text_lower:
            if "late fee" in text_lower:
                return (
                    "caution",
                    "Late fees are common, but amounts should be reasonable. Check your state's laws on maximum late fee amounts.",
                    "Ensure there's a grace period (typically 3-5 days) and that fee doesn't exceed state limits (often $50 or 5% of rent).",
                )
            elif "non-refundable" in text_lower:
                return (
                    "caution",
                    "Non-refundable fees or deposits may not be legal in your state. Security deposits are typically refundable if you leave property in good condition.",
                    "Clarify what this fee covers and check local laws. Consider negotiating to make it refundable.",
                )
            else:
                return (
                    "caution",
                    "This clause may result in additional costs or give landlord significant discretion. Review carefully.",
                    "Ask for specific dollar amounts instead of vague terms like 'additional charges' or 'as determined by landlord.'",
                )

    # Default: appears safe
    return (
        "safe",
        "This clause appears standard and doesn't contain obvious red flags. However, it's always good to read the full context.",
        "Continue reviewing the complete lease for a comprehensive understanding. Our full analysis can check all clauses together.",
    )


@router.post("/clause/quick-analyze")
async def quick_analyze_clause(request: Request):
    """
    Quick analysis of a single clause (no file upload needed, no user_id required)
    Used for the homepage 'Try the AI Engine' feature
    """
    try:
        data = await request.json()
        clause_text = data.get("clause_text", "").strip()

        if not clause_text:
            raise HTTPException(status_code=400, detail="Clause text is required")

        if len(clause_text) > 300:
            raise HTTPException(
                status_code=400, detail="Clause text too long (max 300 characters)"
            )

        # Simple rule-based analysis (based on keywords)
        risk_level, analysis, suggestion = analyze_single_clause(clause_text)

        return {
            "success": True,
            "data": {
                "clause_text": clause_text,
                "risk_level": risk_level,
                "analysis": analysis,
                "suggestion": suggestion,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

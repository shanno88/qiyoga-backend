from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pathlib import Path
import time
import logging
import uuid
import json
import random
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from openai import OpenAI

from config import settings
from utils.file_handler import save_upload_file, cleanup_file
from utils.text_parser import extract_key_info
from services.ocr_service import get_ocr_service
from services.pdf_service import get_pdf_service

logger = logging.getLogger(__name__)

if not settings.DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY environment variable is not set")

deepseek_client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1"
)

BILINGUAL_EXPLAINER_SYSTEM_PROMPT = """You are a rental agreement explainer for Chinese international students in the US.

YOUR TASK
Convert any English lease-related text into a bilingual two-line format.

IMPORTANT
The English text you receive may be:
- an original lease clause, OR
- an English analysis, suggestion, or recommendation (e.g. "Negotiate pet fee waiver or one-time $200 instead of monthly", "Save ~$100/year").

In ALL cases, you must treat each English line as content to be bilingualized.

OUTPUT FORMAT (STRICT – NO DEVIATIONS)

For each English line you receive in the user message, output exactly two lines:

- Line 1: Copy the English text EXACTLY as provided in the input.
- Line 2: Start with "中文解释：" and then write 1–3 sentences of natural Chinese explaining:
  - what that English line means,
  - what the tenant should do or understand,
  - and, if relevant, the money impact or risk.

Put ONE blank line between different English lines.

RULES
1. Line 1 = always copy the English input line exactly. Never modify it.
2. Line 2 = always start with "中文解释：" and be written mainly in Chinese.
3. Do not add extra titles, emojis, or bullet points.
4. For multiple lines in one message, output repeated blocks:

[original English line]
中文解释：[Chinese explanation]

separated by one blank line.

RESPONSE BEHAVIOR
- As soon as you receive English text, immediately output the two-line blocks.
- Do not reply with "Understood" or "Ready"."""

BILINGUAL_ANALYSIS_SYSTEM_PROMPT = """You are a rental agreement analyst for Chinese international students in the US.

YOUR TASK
For each lease clause provided, generate bilingual analysis and suggestion.

INPUT FORMAT
You will receive clauses in this format:
---CLAUSE---
[clause text]
---RISK---
[risk level: safe/caution/danger]
---END---

OUTPUT FORMAT (STRICT JSON)
For each clause, output a JSON object with these exact fields:
{
  "analysis_en": "1-2 sentences in English explaining what this clause means and any concerns",
  "analysis_zh": "1-2 sentences in Chinese (中文解释) summarizing the analysis for a student",
  "suggestion_en": "1 sentence in English with practical advice for the tenant",
  "suggestion_zh": "1 sentence in Chinese (中文建议) with the same advice"
}

RULES
1. analysis_en and analysis_zh must be related (same content, different languages)
2. suggestion_en and suggestion_zh must be related (same content, different languages)
3. Chinese text should be natural and student-friendly, not formal legal language
4. Keep each field concise (1-2 sentences max)
5. Output ONLY valid JSON, no markdown or extra text
6. For multiple clauses, output a JSON array: [{...}, {...}]"""


def parse_bilingual_response(response_text: str) -> List[Dict[str, str]]:
    clauses = []
    blocks = [b.strip() for b in response_text.split("\n\n") if b.strip()]

    for block in blocks:
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) >= 2:
            english_line = lines[0].strip()
            chinese_line = next((l for l in lines if l.startswith("中文解释：")), None)

            if chinese_line:
                clauses.append(
                    {
                        "clause_text": english_line,
                        "chinese_explanation": chinese_line.replace(
                            "中文解释：", ""
                        ).strip(),
                    }
                )

    return clauses


async def get_chinese_explanation(english_text: str) -> Optional[str]:
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BILINGUAL_EXPLAINER_SYSTEM_PROMPT},
                {"role": "user", "content": english_text},
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        result = response.choices[0].message.content or ""
        parsed = parse_bilingual_response(result)

        if parsed:
            return parsed[0]["chinese_explanation"]
        return None
    except Exception as e:
        logger.error(f"DeepSeek error in get_chinese_explanation: {e}")
        return None


# In-memory storage for analysis results
ANALYSIS_STORE: Dict[str, Dict[str, Any]] = {}
USER_ACCESS_STORE: Dict[str, Dict[str, Any]] = {}

# Rate limiting storage for quick-analyze endpoint
QUICK_ANALYZE_RATE_LIMITS: Dict[str, List[datetime]] = {}
IP_RATE_LIMITS: Dict[str, List[datetime]] = {}

# Quick clause history storage (user_id -> list of results)
QUICK_CLAUSE_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
QUICK_CLAUSE_HISTORY_LIMIT = 3

# Rate limiting constants
QUICK_ANALYZE_USER_LIMIT = 3
QUICK_ANALYZE_IP_LIMIT = 20
QUICK_ANALYZE_WINDOW = timedelta(hours=24)

# Full lease analysis pass constants
FULL_ANALYSIS_LEASE_LIMIT = 5  # Max 5 leases per 30-day pass
FULL_ANALYSIS_ACCESS_DURATION = timedelta(days=30)  # 30-day access window


async def get_chinese_explanation_batch(texts: List[str]) -> List[str]:
    """
    Get Chinese explanations for multiple texts in a single AI call.
    Returns a list of Chinese explanations in the same order as input texts.
    """
    if not texts:
        return []

    combined_input = "\n\n".join(texts)

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BILINGUAL_EXPLAINER_SYSTEM_PROMPT},
                {"role": "user", "content": combined_input},
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        result = response.choices[0].message.content or ""
        parsed = parse_bilingual_response(result)

        explanations = []
        for i, text in enumerate(texts):
            if i < len(parsed):
                explanations.append(parsed[i].get("chinese_explanation", ""))
            else:
                explanations.append("")

        return explanations
    except Exception as e:
        logger.error(f"DeepSeek error in get_chinese_explanation_batch: {e}")
        return [""] * len(texts)


async def get_bilingual_analysis_batch(
    clause_data: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    Get bilingual analysis and suggestion for multiple clauses in a single AI call.
    Input: list of dicts with 'clause_text' and 'risk_level' keys
    Returns: list of dicts with analysis_en, analysis_zh, suggestion_en, suggestion_zh
    """
    if not clause_data:
        return []

    combined_input = ""
    for i, clause in enumerate(clause_data):
        combined_input += f"""---CLAUSE---
{clause.get("clause_text", "")}
---RISK---
{clause.get("risk_level", "safe")}
---END---

"""

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BILINGUAL_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": combined_input},
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        result = response.choices[0].message.content or ""

        # Try to parse JSON response
        try:
            # Remove potential markdown code blocks
            clean_result = result.strip()
            if clean_result.startswith("```"):
                clean_result = (
                    clean_result.split("\n", 1)[1]
                    if "\n" in clean_result
                    else clean_result
                )
            if clean_result.endswith("```"):
                clean_result = clean_result.rsplit("```", 1)[0]
            clean_result = clean_result.strip()

            parsed = json.loads(clean_result)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            logger.error(f"Failed to parse AI response as JSON: {result[:200]}")

        # Fallback: return empty dicts
        return [{}] * len(clause_data)
    except Exception as e:
        logger.error(f"DeepSeek error in get_bilingual_analysis_batch: {e}")
        return [{}] * len(clause_data)


router = APIRouter(tags=["lease"])


def classify_clause(clause_text: str) -> str:
    """
    Classify a clause into 'meta', 'core_term', or 'other'.
    """
    text_lower = clause_text.lower()

    # Meta: titles, headers, page markers, party names, dates
    meta_patterns = [
        "--- page",
        "sample rental agreement",
        "residential lease agreement",
        "this agreement made this",
        "this lease agreement",
        "between the parties",
        "landlord:",
        "tenant:",
        "lessee:",
        "lessor:",
        "date:",
        "property address:",
        "page ",
        "section",
    ]

    for pattern in meta_patterns:
        if pattern in text_lower:
            # Additional check: if very short and looks like a header
            if len(clause_text) < 50 and (
                clause_text.strip().startswith("---")
                or "page" in text_lower
                or clause_text.strip().endswith(":")
            ):
                return "meta"
            # Check if it's primarily a title/header
            if (
                any(p in text_lower for p in ["agreement", "lease", "contract"])
                and len(clause_text) < 100
            ):
                return "meta"

    # Core terms: important economic/legal terms
    core_term_keywords = [
        "rent",
        "deposit",
        "security deposit",
        "late fee",
        "term",
        "lease term",
        "utilities",
        "maintenance",
        "repair",
        "termination",
        "eviction",
        "sublet",
        "sublease",
        "pet",
        "guest",
        "occupant",
        "parking",
        "insurance",
        "entry",
        "access",
        "notice",
        "renewal",
        "break lease",
        "early termination",
        "grace period",
        "payment",
        "monthly",
        "annual",
        "yearly",
        "prorate",
        "pro-rate",
    ]

    for keyword in core_term_keywords:
        if keyword in text_lower:
            return "core_term"

    return "other"


async def generate_sample_clauses(
    full_text: str, fast_mode: bool = False
) -> Tuple[List[Dict[str, Any]], float]:
    """Generate sample clause analyses from the lease text with bilingual analysis and Chinese explanations

    Args:
        full_text: The lease text to analyze
        fast_mode: If True, generates only 3 clauses with simplified analysis (for preview mode)

    Returns:
        Tuple of (clauses list, ai_duration in seconds)
    """
    ai_start_time = time.time()
    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

    if len(paragraphs) < 5:
        sentences = [s.strip() for s in full_text.split(".") if s.strip()]
        paragraphs = sentences

    if fast_mode:
        num_clauses = min(len(paragraphs), 3)
    else:
        num_clauses = min(len(paragraphs), random.randint(15, 20))

    risk_levels = ["safe", "caution", "danger"]
    risk_weights = [0.5, 0.35, 0.15]

    clause_data_for_analysis = []
    clause_texts_for_explanation = []

    for i in range(num_clauses):
        paragraph_idx = i % len(paragraphs)
        clause_text = paragraphs[paragraph_idx][:200]
        risk_level = random.choices(risk_levels, weights=risk_weights)[0]
        category = classify_clause(clause_text)

        clause_data_for_analysis.append(
            {
                "clause_text": clause_text,
                "risk_level": risk_level,
                "category": category,
                "clause_number": i + 1,
            }
        )
        clause_texts_for_explanation.append(clause_text)

    # Get bilingual analysis/suggestion from AI
    bilingual_analyses = await get_bilingual_analysis_batch(clause_data_for_analysis)

    # Get Chinese explanations for clause text
    chinese_explanations = await get_chinese_explanation_batch(
        clause_texts_for_explanation
    )

    # Build final clause objects
    clauses = []
    for i, data in enumerate(clause_data_for_analysis):
        bilingual = bilingual_analyses[i] if i < len(bilingual_analyses) else {}

        analysis_en = bilingual.get(
            "analysis_en", "This clause has been analyzed for potential concerns."
        )
        analysis_zh = bilingual.get("analysis_zh", "该条款已分析潜在问题。")
        suggestion_en = bilingual.get(
            "suggestion_en", "Review this clause carefully before signing."
        )
        suggestion_zh = bilingual.get("suggestion_zh", "签署前请仔细阅读此条款。")

        clause = {
            "clause_number": data["clause_number"],
            "clause_text": data["clause_text"],
            "category": data["category"],
            "risk_level": data["risk_level"],
            "chinese_explanation": chinese_explanations[i]
            if i < len(chinese_explanations)
            else "",
            "analysis_en": analysis_en,
            "analysis_zh": analysis_zh,
            "suggestion_en": suggestion_en,
            "suggestion_zh": suggestion_zh,
            "analysis": analysis_en,
            "suggestion": suggestion_en,
        }
        clauses.append(clause)

    ai_duration = time.time() - ai_start_time
    return clauses, ai_duration


def check_user_access(user_id: str) -> Dict[str, Any]:
    """
    Check if user has valid 30-day access
    Returns: (has_access, expires_at, days_remaining, analyses_count, remaining_analyses)
    """
    if user_id not in USER_ACCESS_STORE:
        return {"has_access": False}

    access = USER_ACCESS_STORE[user_id]
    now = datetime.now()
    expires_at = datetime.fromisoformat(access["expires_at"])

    # Check if within 30-day window
    if now >= expires_at:
        return {"has_access": False}

    # Check analysis count (5-lease cap)
    analyses_count = len(access.get("analysis_ids", []))
    if analyses_count >= FULL_ANALYSIS_LEASE_LIMIT:
        return {
            "has_access": False,
            "reason": "lease_limit_reached",
            "message": f"You've used all {FULL_ANALYSIS_LEASE_LIMIT} analyses included in your 30-day pass. Please purchase another pass for more reviews.",
        }

    days_remaining = (expires_at - now).days
    remaining_analyses = FULL_ANALYSIS_LEASE_LIMIT - analyses_count

    return {
        "has_access": True,
        "expires_at": access["expires_at"],
        "days_remaining": days_remaining,
        "analyses_count": analyses_count,
        "remaining_analyses": remaining_analyses,
    }


@router.post("/analyze")
async def analyze_lease(
    files: List[UploadFile] = File(...),
    user_id: str = Query(..., description="User ID from frontend session"),
):
    start_time = time.time()
    temp_image_paths = []
    MAX_PAGES = 40

    try:
        logger.info(
            f"Starting lease analysis for {len(files)} file(s), user_id: {user_id}"
        )

        pdf_service = get_pdf_service()
        ocr_service = get_ocr_service()
        all_image_paths = []

        sorted_files = sorted(files, key=lambda f: f.filename or "")

        for file in sorted_files:
            uploaded_file_path = await save_upload_file(file)
            uploaded_path = Path(uploaded_file_path)
            temp_image_paths.append(uploaded_file_path)

            if pdf_service.is_pdf(uploaded_path):
                logger.info(f"Processing PDF file: {file.filename}")
                image_paths = pdf_service.pdf_to_images(uploaded_path)
                all_image_paths.extend(image_paths)
                temp_image_paths.extend(image_paths)
            elif pdf_service.is_image(uploaded_path):
                logger.info(f"Processing image file: {file.filename}")
                all_image_paths.append(uploaded_path)
            else:
                logger.error(f"Unsupported file format: {uploaded_path.suffix}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file format: {uploaded_path.suffix}. Please upload PDF or image files.",
                )

        if not all_image_paths:
            logger.error("No pages found in the document(s)")
            raise HTTPException(
                status_code=400, detail="No pages found in the document(s)"
            )

        total_pages = len(all_image_paths)
        if total_pages > MAX_PAGES:
            logger.error(f"Too many pages: {total_pages}")
            raise HTTPException(
                status_code=400,
                detail=f"Your document has {total_pages} pages, which exceeds our limit of {MAX_PAGES} pages. Please upload a shorter lease or contact support.",
            )

        logger.info(f"Found {total_pages} page(s) to process from {len(files)} file(s)")
        ocr_result = ocr_service.recognize_images(all_image_paths)

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

        all_clauses, ai_duration = await generate_sample_clauses(
            full_text, fast_mode=False
        )

        if settings.should_bypass_test_user(user_id):
            logger.info(f"Test user bypass enabled for: {user_id}")
            has_full_access = True
        else:
            access_info = check_user_access(user_id)
            has_full_access = access_info["has_access"]

            if not has_full_access:
                reason = access_info.get("reason", "expired")
                if reason == "lease_limit_reached":
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "ACCESS_DENIED",
                            "message": f"您已使用完30天通行证中的全部{FULL_ANALYSIS_LEASE_LIMIT}次分析次数。如需继续使用，请购买新的通行证。",
                        },
                    )
                else:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "ACCESS_DENIED",
                            "message": "您当前没有有效的分析权限，请登录或完成支付后再试。",
                        },
                    )

        processing_time = time.time() - start_time

        logger.info(f"Lease analysis completed successfully in {processing_time:.2f}s")

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

        if user_id not in USER_ACCESS_STORE:
            USER_ACCESS_STORE[user_id] = {"analysis_ids": []}
        if analysis_id not in USER_ACCESS_STORE[user_id]["analysis_ids"]:
            USER_ACCESS_STORE[user_id]["analysis_ids"].append(analysis_id)

        logger.info(f"Stored analysis with ID: {analysis_id} for user: {user_id}")
        logger.info(
            f"User {user_id} has used {len(USER_ACCESS_STORE[user_id]['analysis_ids'])} of {FULL_ANALYSIS_LEASE_LIMIT} analyses"
        )

        timing_info = {
            "backendDuration": round(processing_time * 1000),
            "deepseekDuration": round(ai_duration * 1000),
            "businessDuration": round(processing_time * 1000),
            "totalDuration": round(processing_time, 2),
        }

        return {
            "success": True,
            "data": {
                "analysis_id": analysis_id,
                "full_text": full_text,
                "key_info": key_info,
                "clauses": all_clauses,
                "total_clauses": len(all_clauses),
                "shown_clauses": len(all_clauses),
                "max_clauses": len(all_clauses),
                "has_full_access": has_full_access,
                "user_id": user_id,
                "lines": [
                    {"text": line["text"], "confidence": line["confidence"]}
                    for line in ocr_result.get("lines", [])
                ],
                "processing_time": round(processing_time, 2),
                "page_count": ocr_result.get("page_count", 0),
                "timing": timing_info,
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


def get_user_identifier(request: Request) -> str:
    """Get user identifier from header or fallback to IP-based ID"""
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return user_id
    # Fallback to IP-based ID (combine IP with a hash for some stability)
    client_host = request.client.host if request.client else "unknown"
    return f"ip_{client_host}"


def check_rate_limit(user_id: str, ip_address: str) -> Tuple[bool, int]:
    """
    Check if user/IP is within rate limits
    Returns: (allowed, remaining_attempts)
    """
    now = datetime.now()
    window_start = now - QUICK_ANALYZE_WINDOW

    # Clean up old entries
    if user_id in QUICK_ANALYZE_RATE_LIMITS:
        QUICK_ANALYZE_RATE_LIMITS[user_id] = [
            ts for ts in QUICK_ANALYZE_RATE_LIMITS[user_id] if ts > window_start
        ]
    if ip_address in IP_RATE_LIMITS:
        IP_RATE_LIMITS[ip_address] = [
            ts for ts in IP_RATE_LIMITS[ip_address] if ts > window_start
        ]

    # Check user limit
    user_requests = QUICK_ANALYZE_RATE_LIMITS.get(user_id, [])
    if len(user_requests) >= QUICK_ANALYZE_USER_LIMIT:
        remaining = 0
        logger.info(
            f"Rate limit exceeded for user {user_id}: {len(user_requests)} requests"
        )
        return (False, remaining)

    # Check IP limit
    ip_requests = IP_RATE_LIMITS.get(ip_address, [])
    if len(ip_requests) >= QUICK_ANALYZE_IP_LIMIT:
        remaining = max(0, QUICK_ANALYZE_USER_LIMIT - len(user_requests))
        logger.info(
            f"IP rate limit exceeded for {ip_address}: {len(ip_requests)} requests"
        )
        return (False, remaining)

    # Record this request
    if user_id not in QUICK_ANALYZE_RATE_LIMITS:
        QUICK_ANALYZE_RATE_LIMITS[user_id] = []
    QUICK_ANALYZE_RATE_LIMITS[user_id].append(now)

    if ip_address not in IP_RATE_LIMITS:
        IP_RATE_LIMITS[ip_address] = []
    IP_RATE_LIMITS[ip_address].append(now)

    remaining = QUICK_ANALYZE_USER_LIMIT - len(QUICK_ANALYZE_RATE_LIMITS[user_id])
    return (True, remaining)


def get_short_explanation(clause_text: str, risk_level: str) -> str:
    """
    Generate a brief 1-2 sentence explanation (simplified output)
    """
    text_lower = clause_text.lower()

    # High risk
    if risk_level == "danger":
        if "all" in text_lower and (
            "repair" in text_lower or "maintenance" in text_lower
        ):
            return "This clause shifts most repair costs to the tenant, regardless of fault."
        elif "enter" in text_lower and "any time" in text_lower:
            return "This allows landlord to enter your unit at any time without notice."
        elif "waive" in text_lower:
            return "This asks you to give up important legal rights as a tenant."
        return "This clause heavily favors the landlord and may limit your rights significantly."

    # Medium risk
    elif risk_level == "caution":
        if "late fee" in text_lower:
            return "Late fees are included—check amounts against your state's legal limits."
        elif "non-refundable" in text_lower:
            return "This fee may not be refundable—clarify what it covers."
        return (
            "This clause could lead to additional costs. Review the details carefully."
        )

    # Low risk
    return "This clause appears standard and doesn't raise obvious concerns."


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


# NOTE: /clause/quick-analyze is currently used only for internal testing.
# The public UI no longer exposes this feature.
@router.post("/clause/quick-analyze")
async def quick_analyze_clause(request: Request):
    """
    Quick analysis of a single clause (simplified preview, rate limited)
    Returns only risk_level and a brief explanation
    """
    try:
        data = await request.json()
        clause_text = data.get("clause_text", "").strip()

        if not clause_text:
            raise HTTPException(
                status_code=400,
                detail="Please paste only one short clause (max 250 characters) for the free preview.",
            )

        if len(clause_text) > 250:
            raise HTTPException(
                status_code=400,
                detail="This quick check is only for short clauses. Please paste a shorter sentence (up to 250 characters).",
            )

        user_id = get_user_identifier(request)
        ip_address = request.client.host if request.client else "unknown"

        allowed, remaining = check_rate_limit(user_id, ip_address)
        if not allowed:
            logger.warning(f"Rate limit exceeded for user {user_id}, IP {ip_address}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "limit_reached",
                    "message": "You've used your 3 free clause previews for today. For a full lease review, please upgrade to a paid report.",
                },
            )

        risk_level, full_analysis, suggestion = analyze_single_clause(clause_text)

        short_explanation = get_short_explanation(clause_text, risk_level)

        chinese_explanation = await get_chinese_explanation(short_explanation)

        risk_map = {"danger": "High", "caution": "Medium", "safe": "Low"}
        mapped_risk = risk_map.get(risk_level, "Medium")

        result = {
            "clause_text": clause_text,
            "risk_level": mapped_risk,
            "explanation_en": short_explanation,
            "explanation_zh": chinese_explanation or "",
            "created_at": datetime.now().isoformat(),
        }

        if user_id not in QUICK_CLAUSE_HISTORY:
            QUICK_CLAUSE_HISTORY[user_id] = []
        QUICK_CLAUSE_HISTORY[user_id].insert(0, result)
        QUICK_CLAUSE_HISTORY[user_id] = QUICK_CLAUSE_HISTORY[user_id][
            :QUICK_CLAUSE_HISTORY_LIMIT
        ]

        logger.info(
            f"Quick analyze - User: {user_id}, IP: {ip_address}, "
            f"Risk: {risk_level}, Remaining: {remaining}"
        )

        return {
            "success": True,
            "remaining_quota_today": remaining,
            "result": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in quick analyze: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clause/quick-analyze/history")
async def get_quick_clause_history(request: Request):
    """
    Get the last 3 quick clause analysis results for the user
    """
    try:
        user_id = get_user_identifier(request)
        history = QUICK_CLAUSE_HISTORY.get(user_id, [])

        return {
            "success": True,
            "history": history,
        }
    except Exception as e:
        logger.exception(f"Error fetching quick clause history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

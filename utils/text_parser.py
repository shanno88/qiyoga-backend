import re
from typing import Optional, Dict, Any


def extract_rent_amount(text: str) -> Optional[str]:
    rent_patterns = [
        # Labeled forms with explicit labels (highest priority)
        r"Base\s+Rent:\s*\$?\s*[\d,]+\.?\d*\s*(?:USD)?(?:\s*(?:per\s+)?(?:month|mo|monthly))?",
        r"Monthly\s+Base\s+Rent:\s*[\d,]+\.?\d*\s*(?:USD)?\s*(?:per\s+)?(?:month|mo|monthly)?",
        r"Monthly\s+Rent:\s*\$?\s*[\d,]+\.?\d*\s*(?:per\s+)?(?:month|mo|monthly)?",
        r"Rent:\s*\$?\s*[\d,]+\.?\d*\s*(?:per\s+)?(?:month|mo|monthly)?",
        r"Rent\s+Amount:\s*\$?\s*[\d,]+\.?\d*\s*(?:per\s+)?(?:month|mo|monthly)?",
        r"\$\s*[\d,]+\.?\d*\s*(?:per\s+)?(?:month|mo|monthly)",
        r"[\d,]+\.?\d*\s*(?:per\s+)?(?:month|mo|monthly)",
        r"\$\s*[\d,]+\.?\d*\s*/\s*(?:month|mo)",
        # Descriptive sentences
        r"(?:The\s+)?(?:monthly|Monthly)\s+rent\s+(?:shall\s+be|is|will\s+be)\s*\$?\s*[\d,]+\.?\d*",
        r"(?:Rent|rent)\s+(?:shall\s+be|is|will\s+be)\s*\$?\s*[\d,]+\.?\d*\s*(?:per\s+)?(?:month|mo)",
    ]
    for pattern in rent_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            return match.group().strip()
    return None


def extract_lease_term(text: str) -> Optional[str]:
    term_patterns = [
        # Labeled forms with explicit labels (highest priority)
        r"Lease\s+Term:\s*(?:a\s+)?(?:term\s+of\s+)?(\d+)\s*(?:-|\s+to\s+-)\s*(\d+)\s*(?:month|months)",
        r"Lease\s+Term:\s*(?:a\s+)?(?:term\s+of\s+)?(\d+)\s*(?:month|months|year|years)",
        r"Term:\s*(?:a\s+)?(?:term\s+of\s+)?(\d+)\s*(?:month|months|year|years)",
        r"Lease\s+Period:\s*(?:a\s+)?(?:period\s+of\s+)?(\d+)\s*(?:month|months|year|years)",
        # Descriptive sentences
        r"(?:This\s+)?(?:lease|Lease)\s+is\s+(?:for\s+a\s+)?(?:term\s+of\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s*\(\s*\d+\s*\)\s*(?:month|months|year|years)",
        r"for\s+(?:a\s+)?(?:period\s+of\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s*\(\s*\d+\s*\)\s*(?:month|months)",
        r"for\s+(?:a\s+)?(?:period\s+of\s+)?(\d+)\s*(?:month|months|year|years)",
        r"(?:for|during|during\s+the\s+term\s+of)\s+(\d+)\s*(?:month|months|year|years)",
        # Numeric forms
        r"(\d+)\s*(?:-|\s+to\s+-)\s*(\d+)\s*(?:month|months)",
        r"(\d+)\s*(?:month|months|year|years)\s+(?:term|lease)",
    ]
    for pattern in term_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group().strip()
    return None


def extract_date(text: str) -> Optional[str]:
    date_patterns = [
        # Labeled forms with explicit labels (highest priority)
        r"Commencement\s+Date:\s*((?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/\d{4})",
        r"Commencement\s+Date:\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:\d{1,2})(?:st|nd|rd|th)?,?\s+\d{4})",
        r"Start\s+Date:\s*((?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/\d{4})",
        r"Start\s+Date:\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:\d{1,2})(?:st|nd|rd|th)?,?\s+\d{4})",
        r"Effective\s+Date:\s*((?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/\d{4})",
        r"Effective\s+Date:\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:\d{1,2})(?:st|nd|rd|th)?,?\s+\d{4})",
        r"Lease\s+Start\s+(?:Date|):\s*((?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/\d{4})",
        # Descriptive sentences
        r"(?:This\s+)?(?:lease|Lease)\s+(?:begins|starts?|commences?|is\s+effective)\s+(?:on|:)\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:\d{1,2})(?:st|nd|rd|th)?,?\s+\d{4})",
        r"(?:This\s+)?(?:lease|Lease)\s+(?:begins|starts?|commences?|is\s+effective)\s+(?:on|:)\s*((?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/\d{4})",
        # Generic date formats
        r"\b(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/\d{4}\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+\d{4}\b",
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group().strip()
    return None


def extract_landlord_name(text: str) -> Optional[str]:
    patterns = [
        # Labeled forms with explicit labels (highest priority)
        r"(?:Landlord|Owner|Lessor|Property Manager):\s*([A-Z][a-z]+(?:\s+[A-Z](?:\.\s+)?[a-z]+)*(?:\s+[A-Z][a-z]+)*)",
        r"(?:Landlord|Owner|Lessor|Property Manager)\s+([A-Z][a-z]+(?:\s+[A-Z](?:\.\s+)?[a-z]+)*(?:\s+[A-Z][a-z]+)*)",
        r"Landlord\s+Name:?\s*([A-Z][a-z]+(?:\s+[A-Z](?:\.\s+)?[a-z]+)*(?:\s+[A-Z][a-z]+)*)",
        # Company names (all caps with LLC/INC)
        r"(?:Landlord|Owner|Lessor|Property Manager):\s*([A-Z]{2,}(?:\s+[A-Z]{2,})+(?:\s+(?:LLC|INC|LTD|CORP|CO|COMPANY))?)",
        r"(?:Landlord|Owner|Lessor|Property Manager)\s+([A-Z]{2,}(?:\s+[A-Z]{2,})+(?:\s+(?:LLC|INC|LTD|CORP|CO|COMPANY))?)",
        r"LANDLORD,\s*([A-Z\s]+(?:LLC|INC|LTD|CORP|CO|COMPANY)?)",
        # Mixed case with suffixes
        r"(?:Landlord|Owner|Lessor):\s*([A-Z][a-zA-Z\s&]+(?:LLC|Inc\.|Ltd\.|Corp\.|Co\.|Company)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_tenant_name(text: str) -> Optional[str]:
    patterns = [
        # Labeled forms with explicit labels (highest priority)
        r"(?:Tenant|Lessee|Renter):\s*([A-Z][a-z]+(?:\s+[A-Z](?:\.\s+)?[a-z]+)*(?:\s+[A-Z][a-z]+)*)",
        r"(?:Tenant|Lessee|Renter)\s+([A-Z][a-z]+(?:\s+[A-Z](?:\.\s+)?[a-z]+)*(?:\s+[A-Z][a-z]+)*)",
        r"Tenant\s+Name:?\s*([A-Z][a-z]+(?:\s+[A-Z](?:\.\s+)?[a-z]+)*(?:\s+[A-Z][a-z]+)*)",
        # Company names (all caps with LLC/INC)
        r"(?:Tenant|Lessee|Renter):\s*([A-Z]{2,}(?:\s+[A-Z]{2,})+(?:\s+(?:LLC|INC|LTD|CORP|CO|COMPANY))?)",
        r"(?:Tenant|Lessee|Renter)\s+([A-Z]{2,}(?:\s+[A-Z]{2,})+(?:\s+(?:LLC|INC|LTD|CORP|CO|COMPANY))?)",
        r"TENANT,\s*([A-Z\s]+(?:LLC|INC|LTD|CORP|CO|COMPANY)?)",
        # Mixed case with suffixes
        r"(?:Tenant|Lessee|Renter):\s*([A-Z][a-zA-Z\s&]+(?:LLC|Inc\.|Ltd\.|Corp\.|Co\.|Company)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_key_info(text: str) -> Dict[str, Any]:
    rent_amount = extract_rent_amount(text)
    lease_term = extract_lease_term(text)
    start_date = extract_date(text)
    landlord = extract_landlord_name(text)
    tenant = extract_tenant_name(text)
    return {
        "rent_amount": rent_amount or "Not found",
        "lease_term": lease_term or "Not found",
        "start_date": start_date or "Not found",
        "landlord": landlord or "Not found",
        "tenant": tenant or "Not found",
    }

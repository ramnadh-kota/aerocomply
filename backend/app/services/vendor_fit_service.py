import uuid

from sqlalchemy.orm import Session

from app.models.vendor_part_availability import PartAvailabilityStatus, PartCertificationStatus
from app.schemas.vendor_part_availability import VendorFitResult, VendorPartAvailabilityResponse
from app.services import vendor_part_availability_service, vendor_service

# Ported from the canonical frontend algorithm
# (frontend/lib/mock/procurement.ts: scoreVendorOptionsForPart) rather than
# reimplemented, per the "one scoring function" rule that file itself
# documents. Weights and the missing-factor-never-defaults-to-zero honesty
# rule are unchanged; only the field names/types differ (cents instead of
# float price, matching this backend's VendorPartAvailability.unit_price_cents).
_WEIGHTS = {
    "availability": 0.30,
    "certification": 0.25,
    "lead_time": 0.20,
    "price": 0.15,
    "reliability": 0.10,
}

_AVAILABILITY_SCORE = {
    PartAvailabilityStatus.IN_STOCK: 100,
    PartAvailabilityStatus.LIMITED: 55,
    PartAvailabilityStatus.ON_ORDER: 30,
    PartAvailabilityStatus.OUT_OF_STOCK: 0,
}

_CERT_SCORE = {
    PartCertificationStatus.VERIFIED: 100,
    PartCertificationStatus.NOT_VERIFIED: 40,
    PartCertificationStatus.REFERENCE_UNKNOWN: 20,
}


def _lead_time_score(days: int) -> int:
    if days <= 2:
        return 100
    if days <= 5:
        return 70
    if days <= 10:
        return 40
    return 20


def score_vendor_options_for_part(
    db: Session, *, organization_id: uuid.UUID, part_id: uuid.UUID
) -> list[VendorFitResult]:
    lines = vendor_part_availability_service.list_availability_for_part(
        db, organization_id=organization_id, part_id=part_id
    )
    prices = [line.unit_price_cents for line in lines if line.unit_price_cents is not None]
    min_price = min(prices) if prices else None

    results: list[VendorFitResult] = []
    for line in lines:
        vendor = vendor_service.get_vendor(
            db, organization_id=organization_id, vendor_id=line.vendor_id
        )
        missing_factors: list[str] = []
        factors: list[str] = []
        weighted_sum = 0.0
        weight_total = 0.0

        if line.availability_status != PartAvailabilityStatus.UNKNOWN:
            weighted_sum += _WEIGHTS["availability"] * _AVAILABILITY_SCORE[line.availability_status]
            weight_total += _WEIGHTS["availability"]
            factors.append(f"Availability: {line.availability_status.replace('_', ' ')}")
        else:
            missing_factors.append("live availability not confirmed")

        if line.certification_status != PartCertificationStatus.UNKNOWN:
            weighted_sum += _WEIGHTS["certification"] * _CERT_SCORE[line.certification_status]
            weight_total += _WEIGHTS["certification"]
            factors.append(f"Certification: {line.certification_status.replace('_', ' ')}")
        else:
            missing_factors.append("certification status unknown")

        if line.lead_time_days is not None:
            weighted_sum += _WEIGHTS["lead_time"] * _lead_time_score(line.lead_time_days)
            weight_total += _WEIGHTS["lead_time"]
            factors.append(f"{line.lead_time_days}-day lead time")
        else:
            missing_factors.append("lead time not on file")

        if line.unit_price_cents is not None and min_price is not None:
            price_score = (
                100.0
                if min_price == 0
                else max(0.0, 100.0 - ((line.unit_price_cents - min_price) / min_price) * 100.0)
            )
            weighted_sum += _WEIGHTS["price"] * price_score
            weight_total += _WEIGHTS["price"]
            factors.append(f"Price: {line.currency or ''} {line.unit_price_cents / 100:.2f}")
        else:
            missing_factors.append("price not on file")

        if vendor.reliability_score is not None:
            weighted_sum += _WEIGHTS["reliability"] * vendor.reliability_score
            weight_total += _WEIGHTS["reliability"]
            factors.append(f"Reliability score {vendor.reliability_score}")
        else:
            missing_factors.append("vendor reliability history unavailable")

        score = round(weighted_sum / weight_total) if weight_total > 0 else None
        if score is None:
            confidence = "UNKNOWN"
        elif weight_total >= 0.85:
            confidence = "HIGH"
        elif weight_total >= 0.5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        results.append(
            VendorFitResult(
                vendor_id=vendor.id,
                vendor_name=vendor.name,
                availability=VendorPartAvailabilityResponse.model_validate(line),
                score=score,
                confidence=confidence,
                factors=factors,
                missing_factors=missing_factors,
            )
        )

    results.sort(key=lambda r: r.score if r.score is not None else -1, reverse=True)
    return results

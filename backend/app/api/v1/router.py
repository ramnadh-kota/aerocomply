from fastapi import APIRouter

from app.api.v1 import (
    aircraft,
    aog,
    auth,
    evidence,
    health,
    inspections,
    inventory,
    lisa,
    maintenance,
    part_requirements,
    parts,
    procurement,
    purchase_orders,
    receiving,
    release_readiness,
    tat,
    vendor_part_availability,
    vendors,
    work_orders,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(aircraft.router)
api_router.include_router(aog.router)
api_router.include_router(work_orders.router)
api_router.include_router(evidence.router)
api_router.include_router(inspections.router)
api_router.include_router(tat.router)
api_router.include_router(release_readiness.router)
api_router.include_router(parts.router)
api_router.include_router(vendors.router)
api_router.include_router(part_requirements.router)
api_router.include_router(inventory.router)
api_router.include_router(vendor_part_availability.router)
api_router.include_router(procurement.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(receiving.router)
api_router.include_router(maintenance.router)
api_router.include_router(lisa.router)

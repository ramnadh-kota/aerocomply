"""scripts/seed_initial_plans.py must work against the suite-specific plan schema
(plans.suite_id NOT NULL, unique (suite_id, code)) and be safe to rerun."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_initial_plans.py"


def _load():
    spec = importlib.util.spec_from_file_location("seed_initial_plans", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EXPECTED = {
    "DRONE_001": "DRONE_UAV",
    "AIRCRAFT_001": "AIRCRAFT",
    "HELICOPTER_001": "HELICOPTER",
    "EVTOL_001": "EVTOL_AAM",
}


def _rows(db):
    return db.execute(
        select(Plan.code, ProductSuite.code, func.count(PlanFeature.id))
        .join(ProductSuite, ProductSuite.id == Plan.suite_id)
        .outerjoin(PlanFeature, PlanFeature.plan_id == Plan.id)
        .where(Plan.code.in_(EXPECTED))
        .group_by(Plan.code, ProductSuite.code)
    ).all()


def test_seed_creates_suite_specific_plans_and_is_idempotent(db_session):
    seed = _load()
    seed.seed_plans(db_session)
    first = sorted(_rows(db_session))
    assert {code: suite for code, suite, _ in first} == EXPECTED

    seed.seed_plans(db_session)
    second = sorted(_rows(db_session))
    assert second == first  # same plans, same feature counts: no duplicates
    assert db_session.scalar(select(func.count(Plan.id)).where(Plan.code.in_(EXPECTED))) == 4


def test_seed_features_respect_suite_boundaries(db_session):
    seed = _load()
    seed.seed_plans(db_session)
    feats = {
        (p.code, f.feature_key)
        for p, f in db_session.execute(
            select(Plan, PlanFeature).join(PlanFeature, PlanFeature.plan_id == Plan.id).where(Plan.code.in_(EXPECTED))
        )
    }
    assert ("EVTOL_001", "evtol_fleet_management") in feats
    assert ("EVTOL_001", "drone_fleet_management") not in feats
    assert ("HELICOPTER_001", "helicopter_fleet_management") in feats


def test_seed_aborts_cleanly_when_a_suite_is_missing(db_session):
    seed = _load()
    db_session.query(ProductSuite).filter(ProductSuite.code == "EVTOL_AAM").delete()
    db_session.flush()
    with pytest.raises(RuntimeError, match="EVTOL_AAM"):
        seed.seed_plans(db_session)
    assert db_session.scalar(select(func.count(Plan.id)).where(Plan.code.in_(EXPECTED))) == 0

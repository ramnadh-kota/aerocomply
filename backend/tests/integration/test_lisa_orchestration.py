import uuid
from datetime import UTC, datetime

from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.auth import CurrentUser
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestCreateRequest,
)
from app.schemas.purchase_order import PurchaseOrderCreateRequest, PurchaseOrderLineCreateRequest
from app.schemas.receiving import ReceiveLineRequest, ReceivePurchaseOrderRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.technician import TechnicianQualificationCreateRequest
from app.schemas.vendor import VendorCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    aog_service,
    part_requirement_service,
    part_service,
    procurement_service,
    purchase_order_service,
    receiving_service,
    technician_service,
    vendor_service,
    work_order_service,
)
from app.services.lisa.intent_service import Intent, classify_intent
from app.services.lisa.message_resolution_service import resolve_message
from app.services.lisa.orchestration_service import MAX_TOOL_CALLS, _CallBudget, investigate


def _create_user(db_session, org_id, roles=None):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Orchestration Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return CurrentUser(
        id=user.id,
        organization_id=org_id,
        email=user.email,
        full_name=user.full_name,
        roles=["ORG_ADMIN"] if roles is None else roles,
    )


def _resolve(db_session, current_user, question):
    return resolve_message(
        db_session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        question=question,
    )


class _Scenario:
    """Builds the full real AOG -> material -> technician chain used by
    most tests below, mirroring what the earlier AOG-critical-path and
    technician-authorization milestones already verified — reused here,
    not re-derived.
    """

    def __init__(self, db_session, org_id):
        self.db = db_session
        self.org_id = org_id
        self.requester = _create_user(db_session, org_id)
        self.approver = _create_user(db_session, org_id)

        self.aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_id,
            payload=AircraftCreateRequest(
                registration="VT-ORC", msn="MSN-ORC", aircraft_type="A320"
            ),
        )
        self.work_order = work_order_service.create_work_order(
            db_session,
            organization_id=org_id,
            created_by_user_id=None,
            payload=WorkOrderCreateRequest(
                aircraft_id=self.aircraft.id, work_order_number="WO-ORC-1"
            ),
        )
        self.aog_event = aog_service.declare_aog(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=AogEventCreateRequest(
                aircraft_id=self.aircraft.id, work_order_id=self.work_order.id, severity="CRITICAL"
            ),
        )
        self.part = part_service.create_part(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=PartCreateRequest(
                part_number="PN-ORC-1", description="Widget", quantity_on_hand=0
            ),
        )
        self.requirement = part_requirement_service.create_part_requirement(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=PartRequirementCreateRequest(
                work_order_id=self.work_order.id, part_id=self.part.id, required_quantity=1
            ),
        )
        self.task = work_order_service.create_task(
            db_session,
            organization_id=org_id,
            payload=TaskCreateRequest(
                work_order_id=self.work_order.id, description="Install widget"
            ),
        )
        self.technician = _create_user(db_session, org_id)
        technician_service.assign_technician(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            task_id=self.task.id,
            technician_user_id=self.technician.id,
        )

    def question(self, current_user, text):
        return _resolve(self.db, current_user, text)


def test_classify_intent_families():
    assert classify_intent("Why is VT-XYZ still AOG?") == Intent.AOG
    assert classify_intent("Why can't we release WO-1042?") == Intent.RELEASE_READINESS
    assert classify_intent("Who is assigned to this task?") == Intent.TECHNICIAN_AUTHORIZATION
    assert classify_intent("Is the technician authorized?") == Intent.TECHNICIAN_AUTHORIZATION
    assert classify_intent("What's delaying PO-1042?") == Intent.PROCUREMENT_CHAIN
    assert classify_intent("Has the part been received?") == Intent.PROCUREMENT_CHAIN
    assert classify_intent("Is this aircraft compliant?") == Intent.COMPLIANCE
    assert classify_intent("What's the weather like?") == Intent.UNKNOWN


def test_aog_investigation_full_chain_resolves_material_blocker(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)

    question_text = f"Why is {scenario.aircraft.registration} AOG?"
    resolution = scenario.question(scenario.approver, question_text)
    result = investigate(
        db_session, scenario.approver, question=question_text, resolution=resolution
    )
    assert result is not None
    assert result.status == "ANSWERED"
    assert result.intent == Intent.AOG.value
    assert result.result_graph["aircraft_id"] == str(scenario.aircraft.id)
    assert result.result_graph["aog_event_id"] == str(scenario.aog_event.id)
    # Shortage not yet requested -> PartRequirement is the real blocker.
    assert result.result_graph.get("part_requirement_id") == str(scenario.requirement.id)
    assert "get_aog_recovery_status" in result.tools_invoked


def test_aog_investigation_carries_task_id_when_blocker_is_task_execution(db_session):
    """A work order with no part shortage but an incomplete task means the
    real AOG blocker is TASK_EXECUTION — the orchestrator must carry the
    real task id into context so a follow-up ("who is assigned?") can
    resolve the technician without the user re-specifying the task.
    """
    org_id = uuid.uuid4()
    approver = _create_user(db_session, org_id)
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-TEX", msn="MSN-TEX", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-TEX-1"),
    )
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(
            aircraft_id=aircraft.id, work_order_id=work_order.id, severity="CRITICAL"
        ),
    )
    task = work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Torque check"),
    )

    resolution = _resolve(db_session, approver, "Why is VT-TEX AOG?")
    result = investigate(db_session, approver, question="Why is VT-TEX AOG?", resolution=resolution)
    assert result is not None
    assert result.status == "ANSWERED"
    assert result.result_graph.get("task_id") == str(task.id)


def test_aog_investigation_needs_entity_when_no_aircraft_in_context(db_session):
    org_id = uuid.uuid4()
    user = _create_user(db_session, org_id)
    resolution = _resolve(db_session, user, "Why is it AOG?")
    result = investigate(db_session, user, question="Why is it AOG?", resolution=resolution)
    assert result is not None
    assert result.status == "NEEDS_ENTITY"


def test_procurement_chain_follows_po_through_states(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)
    vendor = vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="Orc Vendor"),
    )
    request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=scenario.requester.id,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=scenario.aircraft.id,
            work_order_id=scenario.work_order.id,
            part_id=scenario.part.id,
            part_number="PN-ORC-1",
            description="Widget",
            quantity=1,
            reason="AOG",
        ),
    )
    approved = procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=scenario.approver.id,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(selected_vendor_id=vendor.id),
    )
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=scenario.approver.id,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-ORC-1",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    procurement_request_id=approved.id,
                    part_number="PN-ORC-1",
                    description="Widget",
                    quantity=1,
                )
            ],
        ),
    )

    # Explicit "PO-ORC-1" reference resolves current_purchase_order_id via
    # the existing (28e9129) entity resolution — reused here, not redone.
    resolution = scenario.question(scenario.approver, "What is delaying PO-ORC-1?")
    result = investigate(
        db_session, scenario.approver, question="What is delaying PO-ORC-1?", resolution=resolution
    )
    assert result is not None
    assert result.status == "ANSWERED"
    assert "DRAFT" in result.headline

    purchase_order_service.submit_for_approval(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    purchase_order_service.approve_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    purchase_order_service.send_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )

    resolution = scenario.question(scenario.approver, "Has PO-ORC-1 been sent?")
    result = investigate(
        db_session, scenario.approver, question="Has PO-ORC-1 been sent?", resolution=resolution
    )
    assert result is not None
    assert "SENT" in result.headline
    assert result.next_step == "Record receipt of the outstanding quantity."

    receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=po.lines[0].id, quantity=1)]
        ),
    )
    resolution = scenario.question(scenario.approver, "Has PO-ORC-1 been received?")
    result = investigate(
        db_session, scenario.approver, question="Has PO-ORC-1 been received?", resolution=resolution
    )
    assert result is not None
    assert "RECEIVED" in result.headline
    assert "fully RECEIVED" in result.what_i_found[0]


def test_technician_authorization_via_task_context(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)

    # Explicit task reference isn't resolvable by number (Task has none) —
    # simulate a prior investigation having already placed task_id in
    # context, exactly like _investigate_release_readiness would.
    resolution = scenario.question(scenario.approver, "Open the work order.")
    from app.services.lisa import context_service

    context_service.update_context(
        db_session, resolution.context, updates={"current_task_id": str(scenario.task.id)}
    )
    resolution = scenario.question(scenario.approver, "Who is assigned to this task?")

    result = investigate(
        db_session,
        scenario.approver,
        question="Who is assigned to this task?",
        resolution=resolution,
    )
    assert result is not None
    assert result.status == "ANSWERED"
    assert result.result_graph["technician_user_id"] == str(scenario.technician.id)
    # No qualification granted yet -> MISSING.
    assert "MISSING" in result.headline
    assert "No qualification record exists" in result.what_i_found[0]

    technician_service.grant_qualification(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=scenario.technician.id,
            aircraft_type="A320",
            qualification_type="AIRFRAME_POWERPLANT",
            granted_at=datetime.now(UTC),
        ),
    )
    resolution = scenario.question(scenario.approver, "Are they authorized?")
    result = investigate(
        db_session, scenario.approver, question="Are they authorized?", resolution=resolution
    )
    assert result is not None
    assert "is active" in result.what_i_found[0]
    assert "AUTHORIZED" in result.headline


def test_release_readiness_investigation_identifies_task_blocker(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)
    resolution = scenario.question(scenario.approver, "Open the work order.")
    from app.services.lisa import context_service

    context_service.update_context(
        db_session,
        resolution.context,
        updates={"current_work_order_id": str(scenario.work_order.id)},
    )
    resolution = scenario.question(scenario.approver, "Why can't we release this work order?")
    result = investigate(
        db_session,
        scenario.approver,
        question="Why can't we release this work order?",
        resolution=resolution,
    )
    assert result is not None
    assert result.status == "ANSWERED"
    assert "BLOCKED" in result.headline
    # The task (execution_state=PENDING) is the real blocker here.
    assert result.result_graph.get("task_id") == str(scenario.task.id)


def test_orchestration_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    scenario = _Scenario(db_session, org_a)
    user_b = _create_user(db_session, org_b)

    resolution = _resolve(db_session, user_b, f"Why is {scenario.aircraft.registration} AOG?")
    result = investigate(
        db_session,
        user_b,
        question=f"Why is {scenario.aircraft.registration} AOG?",
        resolution=resolution,
    )
    # org_b has no aircraft with that registration -> never resolved. The
    # explicit reference in this message is NOT_FOUND for org_b, not just
    # "no entity in context" — the orchestrator must not fall back to
    # NEEDS_ENTITY generically, and must never leak that the registration
    # exists for a different tenant.
    assert result is not None
    assert result.status == "NOT_FOUND"


def test_orchestration_permission_denied_does_not_leak_via_fallback(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)
    # VIEWER role in this codebase has AIRCRAFT_READ (get_aog_recovery_status
    # requires AIRCRAFT_READ too) but not TECHNICIAN_READ — use a role
    # lacking AIRCRAFT_READ entirely to force a genuine ForbiddenError from
    # execute_tool's own permission check, never bypassed by another tool.
    unauthorized = _create_user(db_session, org_id, roles=[])
    resolution = _resolve(
        db_session, unauthorized, f"Why is {scenario.aircraft.registration} AOG?"
    )
    result = investigate(
        db_session,
        unauthorized,
        question=f"Why is {scenario.aircraft.registration} AOG?",
        resolution=resolution,
    )
    assert result is not None
    assert result.status == "PERMISSION_DENIED"


def test_call_budget_prevents_duplicate_calls(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)
    budget = _CallBudget(db_session, scenario.approver)
    first = budget.call("get_aircraft", {"aircraft_id": str(scenario.aircraft.id)})
    second = budget.call("get_aircraft", {"aircraft_id": str(scenario.aircraft.id)})
    assert first is not None
    assert second is None  # duplicate (tool, args) pair — never called twice
    assert budget.tools_invoked.count("get_aircraft") == 1


def test_call_budget_enforces_max_calls(db_session):
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)
    budget = _CallBudget(db_session, scenario.approver)
    for i in range(MAX_TOOL_CALLS):
        aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_id,
            payload=AircraftCreateRequest(
                registration=f"N{i}BDG", msn=f"MSN-B{i}", aircraft_type="A320"
            ),
        )
        result = budget.call("get_aircraft", {"aircraft_id": str(aircraft.id)})
        assert result is not None
    # One more distinct call must be refused — budget exhausted.
    extra_aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N-OVER", msn="MSN-OVER", aircraft_type="A320"),
    )
    over_budget = budget.call("get_aircraft", {"aircraft_id": str(extra_aircraft.id)})
    assert over_budget is None
    assert len(budget.tools_invoked) == MAX_TOOL_CALLS


def test_unknown_intent_returns_none_for_llm_fallthrough(db_session):
    org_id = uuid.uuid4()
    user = _create_user(db_session, org_id)
    resolution = _resolve(db_session, user, "What is the weather forecast?")
    result = investigate(
        db_session, user, question="What is the weather forecast?", resolution=resolution
    )
    assert result is None


def test_unresolvable_explicit_reference_never_falls_back_to_stale_context(db_session):
    """Regression test for a real defect found during the 5b9c2bf QA pass:
    asking about a nonexistent aircraft registration ("Why is ZZ-NOPE still
    AOG?") after a real aircraft was already in context answered about the
    OLD aircraft instead of reporting NOT_FOUND — because the investigator
    read context.current_aircraft_id directly without checking whether
    this turn's own explicit reference had actually resolved. A registration
    that looks real but matches nothing must never silently fall back to
    whatever aircraft happened to be in context from an earlier turn.
    """
    org_id = uuid.uuid4()
    scenario = _Scenario(db_session, org_id)

    # Turn 1: real aircraft — the AOG investigation itself is already
    # covered elsewhere; only the context side effect matters here.
    resolution = scenario.question(
        scenario.approver, f"Why is {scenario.aircraft.registration} AOG?"
    )
    assert str(resolution.context.current_aircraft_id) == str(scenario.aircraft.id)

    # Turn 2: a syntactically valid but nonexistent registration.
    resolution = scenario.question(scenario.approver, "Why is ZZ-NOPE still AOG?")
    result = investigate(
        db_session,
        scenario.approver,
        question="Why is ZZ-NOPE still AOG?",
        resolution=resolution,
    )
    assert result is not None
    assert result.status == "NOT_FOUND"
    assert "ZZ-NOPE" in result.headline
    # Must NOT answer about the previous aircraft.
    assert scenario.aircraft.registration not in result.headline
    # Context's stale aircraft id is untouched by the failed reference, but
    # the investigator still correctly refused to use it for this turn.
    assert str(resolution.context.current_aircraft_id) == str(scenario.aircraft.id)

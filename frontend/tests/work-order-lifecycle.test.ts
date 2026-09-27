import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { workOrdersApi } from "../lib/api/workOrders";
import { tasksApi } from "../lib/api/tasks";
import { workOrderStatusBadge, tatStatusBadge } from "../components/status/StatusBadge";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Work Order Lifecycle & API Client", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe("workOrdersApi endpoints", () => {
    it("serializes rich query parameters properly on list()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
      await workOrdersApi.list("token-1", {
        status: "IN_PROGRESS",
        priority: "HIGH",
        work_order_type: "CORRECTIVE",
        search: "landing gear",
        overdue_only: true,
        limit: 25,
        offset: 50,
      });

      const [url] = fetchMock.mock.calls[0];
      const urlStr = String(url);
      expect(urlStr).toContain("/work-orders?");
      expect(urlStr).toContain("status=IN_PROGRESS");
      expect(urlStr).toContain("priority=HIGH");
      expect(urlStr).toContain("work_order_type=CORRECTIVE");
      expect(urlStr).toContain("search=landing%20gear");
      expect(urlStr).toContain("overdue_only=true");
      expect(urlStr).toContain("limit=25");
      expect(urlStr).toContain("offset=50");
    });

    it("sends POST /work-orders on create()", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(201, { id: "wo-1", work_order_number: "WO-001", status: "DRAFT" })
      );
      const res = await workOrdersApi.create("token-1", {
        work_order_number: "WO-001",
        title: "Test Order",
        priority: "HIGH",
        work_order_type: "SCHEDULED",
      });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders$/);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(init?.body as string)).toEqual({
        work_order_number: "WO-001",
        title: "Test Order",
        priority: "HIGH",
        work_order_type: "SCHEDULED",
      });
      expect(res.id).toBe("wo-1");
    });

    it("sends PATCH /work-orders/:id on update()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", title: "Updated" }));
      await workOrdersApi.update("token-1", "wo-1", { title: "Updated" });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1$/);
      expect(init?.method).toBe("PATCH");
    });

    it("sends POST /work-orders/:id/assign on assign()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", status: "ASSIGNED" }));
      await workOrdersApi.assign("token-1", "wo-1", { assigned_to_user_id: "user-tech-1" });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/assign$/);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(init?.body as string)).toEqual({ assigned_to_user_id: "user-tech-1" });
    });

    it("sends POST /work-orders/:id/transition on transition()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", status: "IN_PROGRESS" }));
      await workOrdersApi.transition("token-1", "wo-1", { target_status: "IN_PROGRESS" });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/transition$/);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(init?.body as string)).toEqual({ target_status: "IN_PROGRESS" });
    });

    it("sends POST /work-orders/:id/complete on complete()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", status: "COMPLETED" }));
      await workOrdersApi.complete("token-1", "wo-1");

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/complete$/);
      expect(init?.method).toBe("POST");
    });

    it("sends POST /work-orders/:id/close on close()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", status: "CLOSED" }));
      await workOrdersApi.close("token-1", "wo-1");

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/close$/);
      expect(init?.method).toBe("POST");
    });

    it("sends POST /work-orders/:id/cancel with reason on cancel()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", status: "CANCELLED" }));
      await workOrdersApi.cancel("token-1", "wo-1", {
        cancellation_reason: "Mission cancelled",
      });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/cancel$/);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(init?.body as string)).toEqual({
        cancellation_reason: "Mission cancelled",
      });
    });

    it("sends DELETE /work-orders/:id on delete()", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "wo-1", status: "DELETED" }));
      await workOrdersApi.delete("token-1", "wo-1");

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1$/);
      expect(init?.method).toBe("DELETE");
    });

    it("fetches work order TAT on getTat()", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(200, {
          work_order_id: "wo-1",
          status: "ON_TRACK",
          days_remaining: 5,
          reason: "Within schedule",
        })
      );
      const tat = await workOrdersApi.getTat("token-1", "wo-1");

      const [url] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/tat$/);
      expect(tat.status).toBe("ON_TRACK");
    });
  });

  describe("tasksApi endpoints", () => {
    it("creates a task on POST /work-orders/:id/tasks", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(201, { id: "task-1", description: "Torque bolts" })
      );
      await tasksApi.create("token-1", "wo-1", {
        description: "Torque bolts",
        task_number: "T-01",
        estimated_hours: 1.5,
      });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/tasks$/);
      expect(init?.method).toBe("POST");
    });

    it("updates a task on PATCH /work-orders/:id/tasks/:taskId", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(200, { id: "task-1", actual_hours: 2.0 })
      );
      await tasksApi.update("token-1", "wo-1", "task-1", { actual_hours: 2.0 });

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/tasks\/task-1$/);
      expect(init?.method).toBe("PATCH");
    });

    it("completes a task on POST /work-orders/:id/tasks/:taskId/complete", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(200, { id: "task-1", execution_state: "COMPLETED" })
      );
      await tasksApi.complete("token-1", "wo-1", "task-1");

      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toMatch(/\/work-orders\/wo-1\/tasks\/task-1\/complete$/);
      expect(init?.method).toBe("POST");
    });
  });

  describe("Status badge mappings", () => {
    it("maps all lifecycle states to appropriate semantics", () => {
      expect(workOrderStatusBadge("DRAFT").status).toBe("PENDING");
      expect(workOrderStatusBadge("OPEN").status).toBe("PENDING");
      expect(workOrderStatusBadge("PLANNED").status).toBe("PENDING");
      expect(workOrderStatusBadge("ASSIGNED").status).toBe("PENDING");
      expect(workOrderStatusBadge("IN_PROGRESS").status).toBe("REVIEW_REQUIRED");
      expect(workOrderStatusBadge("ON_HOLD").status).toBe("REVIEW_REQUIRED");
      expect(workOrderStatusBadge("INSPECTION").status).toBe("INSUFFICIENT_DATA");
      expect(workOrderStatusBadge("COMPLETED").status).toBe("COMPLIANT");
      expect(workOrderStatusBadge("CLOSED").status).toBe("COMPLIANT");
      expect(workOrderStatusBadge("CANCELLED").status).toBe("UNKNOWN");
    });

    it("maps TAT statuses properly", () => {
      expect(tatStatusBadge("ON_TRACK").status).toBe("COMPLIANT");
      expect(tatStatusBadge("AT_RISK").status).toBe("REVIEW_REQUIRED");
      expect(tatStatusBadge("DELAYED").status).toBe("NON_COMPLIANT");
      expect(tatStatusBadge("UNKNOWN").status).toBe("INSUFFICIENT_DATA");
    });
  });
});

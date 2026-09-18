// M17.2C — unified battery+component lifecycle timeline for one asset.
// Wraps the existing generic Timeline component (components/timeline) --
// no new timeline primitive. Asset-generic (works for any asset_id the
// backend's GET /drones/{asset_id}/lifecycle-history-shaped endpoint
// returns events for), not Drone-specific.

import { Timeline, type TimelineEntry } from "@/components/timeline/Timeline";
import { StatusBadge, lifecycleEventBadge } from "@/components/status/StatusBadge";
import type { AssetLifecycleEventResponse } from "@/lib/api/drones";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function subjectId(event: AssetLifecycleEventResponse): string | null {
  return event.battery_id ?? event.component_id;
}

export function assetLifecycleEventsToTimelineEntries(
  events: AssetLifecycleEventResponse[]
): TimelineEntry[] {
  return events.map((event) => {
    const badge = lifecycleEventBadge(event.event_type);
    const id = subjectId(event);
    return {
      id: event.installation_id + ":" + event.event_type,
      date: formatTimestamp(event.occurred_at),
      title: <StatusBadge status={badge.status} label={badge.label} />,
      detail: id ? (
        <span className="ac-mono" style={{ wordBreak: "break-all" }}>
          {id}
        </span>
      ) : undefined,
      accent: event.event_type.endsWith("REMOVAL") ? "default" : "highlight",
    };
  });
}

export function AssetLifecycleTimeline({
  events,
  emptyMessage = "No lifecycle history recorded yet.",
}: {
  events: AssetLifecycleEventResponse[];
  emptyMessage?: string;
}) {
  if (events.length === 0) {
    return (
      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
        {emptyMessage}
      </p>
    );
  }

  return <Timeline entries={assetLifecycleEventsToTimelineEntries(events)} />;
}

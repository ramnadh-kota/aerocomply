"""Phase 1B: the one canonical place that derives an asset_id compatibility
value for a newly-created MRO record from its already-fetched Aircraft row.

Deliberately trivial today (Aircraft is the only asset-detail type that
exists) -- the point is having ONE function every create_* path calls
instead of seven copies of `aircraft.asset_id`, so a future asset type
(Drone) only needs a change here, not in every MRO service. This does not
change any function signature, schema, or API contract -- it only
populates the new asset_id compatibility column (migration 0031) at
creation time, mirroring what migration 0031's backfill did for existing
rows.
"""

import uuid

from app.models.aircraft import Aircraft


def resolve_asset_id(aircraft: Aircraft) -> uuid.UUID | None:
    return aircraft.asset_id

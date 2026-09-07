import type { ComponentType, SVGProps } from "react";
import { NarrowbodySilhouette } from "./NarrowbodySilhouette";
import { WidebodySilhouette } from "./WidebodySilhouette";
import { RegionalTurbopropSilhouette } from "./RegionalTurbopropSilhouette";
import { HelicopterSilhouette } from "./HelicopterSilhouette";
import { GenericAircraftSilhouette } from "./GenericAircraftSilhouette";

export {
  NarrowbodySilhouette,
  WidebodySilhouette,
  RegionalTurbopropSilhouette,
  HelicopterSilhouette,
  GenericAircraftSilhouette,
};

export type SilhouetteComponent = ComponentType<SVGProps<SVGSVGElement>>;

/** Registry keyed by AircraftVisualConfig.silhouetteId. */
export const SILHOUETTE_REGISTRY: Record<string, SilhouetteComponent> = {
  narrowbody: NarrowbodySilhouette,
  widebody: WidebodySilhouette,
  "regional-turboprop": RegionalTurbopropSilhouette,
  helicopter: HelicopterSilhouette,
  generic: GenericAircraftSilhouette,
};

export function getSilhouetteComponent(silhouetteId: string): SilhouetteComponent {
  return SILHOUETTE_REGISTRY[silhouetteId] ?? GenericAircraftSilhouette;
}

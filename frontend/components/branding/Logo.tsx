import Image from "next/image";
import { COMPANY_NAME } from "@/lib/brand";

// Official KOTA'S AEROSPACE brand mark. This is the ONE reusable logo
// component — every visual brand-header location (sidebar, splash/home,
// login) renders through this rather than duplicating <Image> markup or
// re-hardcoding the asset path. The mark is the visible brand identity by
// itself: callers must NOT render COMPANY_NAME/PLATFORM_NAME text beside
// or beneath it. The company name is still carried as the `alt` text for
// screen readers, per standard accessible-logo practice, without adding a
// second visible text label.
export function Logo({ height = 28 }: { height?: number }) {
  // Source image is a fixed 677x369 px asset (public/images/kotas-aerospace-logo.png);
  // width is derived to preserve its aspect ratio at any requested height.
  const width = Math.round((677 / 369) * height);
  return (
    <Image
      src="/images/kotas-aerospace-logo.png"
      alt={COMPANY_NAME}
      width={width}
      height={height}
      style={{ height, width: "auto", objectFit: "contain" }}
      priority
    />
  );
}

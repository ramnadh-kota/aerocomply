"use client";

/**
 * Purely decorative background layer for the application shell. Never
 * conveys information — aria-hidden and pointer-events: none, sits behind
 * all real content (see .ac-shell's z-index in globals.css).
 *
 * NO AIRCRAFT ASSET OF ANY KIND — this used to render
 * /images/aerocomply-mro-background.svg (a drawn aircraft fuselage/engine
 * cowling) on a subset of routes. That asset is no longer referenced here
 * at all, on any route: the global background must never contain an
 * aircraft, full stop, per explicit product direction. This is a plain
 * dark gradient plus a faint technical grid — no external image, no
 * silhouette, no watermark.
 *
 * Aircraft imagery (the real, licensed 737/A320 hero photos) exists ONLY
 * inside the explicitly-scoped aircraft-detail hero
 * (components/aircraft-visual/AircraftContextLayer.tsx, mounted only on
 * the single-aircraft detail page) — never here, and never on a
 * fleet-wide/dashboard/list page (see that component's own docs for why
 * its fleet-wide silhouette rendering was removed for the same reason).
 */
export function AviationBackground() {
  return (
    <div className="ac-aviation-bg" aria-hidden="true" role="presentation">
      <div className="ac-aviation-bg-overlay ac-aviation-bg-overlay--plain" />
      <div className="ac-aviation-bg-grid" />
    </div>
  );
}

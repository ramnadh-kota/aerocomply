"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { COMPANY_NAME } from "@/lib/brand";
import { ShowcaseScene } from "./Scenes";
import { SHOWCASE_SLIDES, easeToward, wrapOffset, type ShowcaseSlide } from "./slides";
import styles from "./showcase.module.css";

const CRUISE_PX_PER_SEC = 26; // slow and cinematic, not a ticker
const SETTLE_RATE = 3.2; // pause/resume easing
const GLIDE_RATE = 6; // manual prev/next easing
const DRAG_THRESHOLD_PX = 6;

const TINTS: Record<string, [string, string]> = {
  drone: ["#1c3c6b", "#0b1a2e"],
  aircraft: ["#23405f", "#0c1a2b"],
  helicopter: ["#27414f", "#0b1a26"],
  evtol: ["#1a4a58", "#0a1c27"],
  intelligence: ["#2a3566", "#0c1730"],
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return reduced;
}

function Chevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === "left" ? "M10 3 5 8l5 5" : "M6 3l5 5-5 5"} />
    </svg>
  );
}

function PlayPause({ playing }: { playing: boolean }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      {playing ? <path d="M4.5 3h2.6v10H4.5zM8.9 3h2.6v10H8.9z" /> : <path d="M5 3l8 5-8 5z" />}
    </svg>
  );
}

function Backdrop() {
  const stars: Array<[number, number, number]> = [
    [180, 150, 0],
    [820, 210, 1.2],
    [940, 520, 2.4],
    [90, 560, 3.1],
    [520, 90, 4],
    [700, 760, 0.7],
    [260, 820, 1.9],
  ];
  return (
    <svg className={styles.orbits} viewBox="0 0 1000 1000" fill="none" stroke="currentColor" strokeWidth="1" aria-hidden="true" focusable="false">
      <g className={styles.orbitsSpin}>
        <circle cx="500" cy="500" r="470" />
        <ellipse cx="500" cy="500" r="360" rx="360" ry="220" transform="rotate(-24 500 500)" />
        <ellipse cx="500" cy="500" rx="300" ry="470" transform="rotate(38 500 500)" opacity="0.7" />
        <circle cx="500" cy="500" r="250" opacity="0.6" />
      </g>
      {stars.map(([x, y, delay]) => (
        <circle key={`${x}-${y}`} className={styles.star} cx={x} cy={y} r="2.2" stroke="none" style={{ animationDelay: `${delay}s` }} />
      ))}
      <path className={styles.trail} d="M60 900 C 280 880, 420 900, 560 840 S 820 760, 960 750" strokeLinecap="round" opacity="0.4" />
      <circle className={styles.trailDot} r="3" fill="currentColor" stroke="none" style={{ color: "#e8edf7" }}>
        <animateMotion dur="14s" repeatCount="indefinite" path="M60 900 C 280 880, 420 900, 560 840 S 820 760, 960 750" />
      </circle>
    </svg>
  );
}

export function AerospaceShowcase() {
  const reduced = usePrefersReducedMotion();
  const [userPaused, setUserPaused] = useState(false);
  const [active, setActive] = useState<ShowcaseSlide | null>(null);
  const [dragging, setDragging] = useState(false);

  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const openedViaKeyboard = useRef(false);

  // Mutable animation state lives in refs so the rAF loop never re-renders.
  const offset = useRef(0);
  const velocity = useRef(0);
  const glide = useRef(0);
  const hovering = useRef(false);
  const focused = useRef(false);
  const holding = useRef(false); // drag in progress
  const holdFlags = useRef({ userPaused: false, panel: false, reduced: false });
  const drag = useRef<{ x: number; start: number; moved: boolean; id: number } | null>(null);
  const suppressClick = useRef(false);

  useEffect(() => {
    holdFlags.current = { userPaused, panel: active !== null, reduced };
  }, [userPaused, active, reduced]);

  const apply = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const loop = track.scrollWidth / 2;
    offset.current = wrapOffset(offset.current, loop);
    track.style.transform = `translate3d(${-offset.current}px,0,0)`;
  }, []);

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const f = holdFlags.current;
      const held =
        f.userPaused || f.reduced || f.panel || hovering.current || focused.current || holding.current || document.hidden;
      velocity.current = easeToward(velocity.current, held ? 0 : CRUISE_PX_PER_SEC, dt, SETTLE_RATE);
      if (Math.abs(velocity.current) < 0.01) velocity.current = 0;
      let delta = velocity.current * dt;
      if (glide.current !== 0) {
        const step = f.reduced ? glide.current : glide.current * Math.min(1, dt * GLIDE_RATE);
        delta += step;
        glide.current -= step;
        if (Math.abs(glide.current) < 0.5) {
          delta += glide.current;
          glide.current = 0;
        }
      }
      if (delta !== 0) {
        offset.current += delta;
        apply();
      }
      raf = requestAnimationFrame(tick);
    };
    apply();
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [apply]);

  const step = useCallback((dir: 1 | -1) => {
    const card = trackRef.current?.querySelector<HTMLElement>("[data-slide]");
    if (!card) return;
    const style = getComputedStyle(card);
    glide.current += dir * (card.offsetWidth + parseFloat(style.marginRight || "0"));
  }, []);

  // Panel focus management: move focus in on open, restore on close.
  useEffect(() => {
    if (active) closeRef.current?.focus();
  }, [active]);

  const closePanel = useCallback(() => {
    setActive(null);
    // Pointer users get the carousel back in motion; keyboard users keep their place.
    if (openedViaKeyboard.current) openerRef.current?.focus();
    else {
      focused.current = false;
      (document.activeElement as HTMLElement | null)?.blur();
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, closePanel]);

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    drag.current = { x: e.clientX, start: offset.current, moved: false, id: e.pointerId };
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x;
    if (!d.moved && Math.abs(dx) < DRAG_THRESHOLD_PX) return;
    if (!d.moved) {
      d.moved = true;
      holding.current = true;
      setDragging(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    }
    glide.current = 0;
    offset.current = d.start - dx;
    apply();
  }

  function endDrag(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    if (d.moved) {
      suppressClick.current = true;
      // Swallow the click that follows a drag; clear on the next tick.
      window.setTimeout(() => {
        suppressClick.current = false;
      }, 0);
    }
    drag.current = null;
    holding.current = false;
    setDragging(false);
  }

  function onFocusCapture(e: React.FocusEvent<HTMLDivElement>) {
    focused.current = true;
    const viewport = viewportRef.current;
    if (!viewport) return;
    // Browsers scroll overflow:hidden boxes to reveal a focused child, which
    // would desync our transform. Undo that and glide the card into view.
    viewport.scrollLeft = 0;
    const card = (e.target as HTMLElement).closest<HTMLElement>("[data-slide]");
    if (!card) return;
    const left = card.offsetLeft - offset.current;
    const right = left + card.offsetWidth;
    if (left < 0) glide.current += left - 24;
    else if (right > viewport.clientWidth) glide.current += right - viewport.clientWidth + 24;
  }

  function openSlide(slide: ShowcaseSlide, el: HTMLElement) {
    if (suppressClick.current) return;
    openerRef.current = el;
    openedViaKeyboard.current = el.matches(":focus-visible");
    setActive(slide);
  }

  const renderCards = (copy: 0 | 1) =>
    SHOWCASE_SLIDES.map((slide) => {
      const [a, b] = TINTS[slide.id];
      const hidden = copy === 1;
      return (
        <button
          key={`${copy}-${slide.id}`}
          type="button"
          data-slide={slide.id}
          className={styles.card}
          style={{ "--tint-a": a, "--tint-b": b } as CSSProperties}
          tabIndex={hidden ? -1 : 0}
          aria-hidden={hidden || undefined}
          aria-haspopup="dialog"
          aria-label={hidden ? undefined : `${slide.category}: ${slide.headline} ${slide.cta}`}
          onClick={(e) => openSlide(slide, e.currentTarget)}
          draggable={false}
        >
          <span className={styles.cardGrid} aria-hidden="true" />
          {slide.photo ? (
            // eslint-disable-next-line @next/next/no-img-element -- optional licensed photo; falls back to the vector scene on error
            <img
              className={styles.photo}
              src={slide.photo}
              alt=""
              draggable={false}
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          ) : null}
          <span className={styles.sceneWrap} aria-hidden="true">
            <ShowcaseScene id={slide.id} className={styles.scene} />
          </span>
          <span className={styles.scrim} aria-hidden="true" />
          <span className={styles.copy}>
            <span className={styles.cat}>{slide.category}</span>
            <span className={styles.headline}>{slide.headline}</span>
            <span className={styles.reveal}>
              <span className={styles.revealInner}>
                <span className={styles.desc}>{slide.description}</span>
                <span className={styles.cta}>{slide.cta}</span>
              </span>
            </span>
          </span>
        </button>
      );
    });

  return (
    <aside className={styles.pane} aria-label="Kota Aerospace platform overview">
      <div className={styles.grid} aria-hidden="true" />
      <Backdrop />

      <div className={styles.hero}>
        <p className={styles.eyebrow}>Aerospace intelligence platform</p>
        <p className={styles.lead}>one intelligence layer for</p>
        <h2 className={styles.title}>Every asset.</h2>
        <p className={styles.sub}>
          Drones, aircraft, helicopters and eVTOL: monitored, maintained and compliant in one place.
        </p>
      </div>

      <div className={styles.stage}>
        <div
          ref={viewportRef}
          className={`${styles.viewport} ${dragging ? styles.dragging : ""}`}
          role="group"
          aria-roledescription="carousel"
          aria-label="Aerospace categories"
          onPointerEnter={(e) => {
            if (e.pointerType === "mouse") hovering.current = true;
          }}
          onPointerLeave={() => {
            hovering.current = false;
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onFocusCapture={onFocusCapture}
          onBlurCapture={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) focused.current = false;
          }}
          onDragStart={(e) => e.preventDefault()}
        >
          <div ref={trackRef} className={styles.track}>
            {renderCards(0)}
            {renderCards(1)}
          </div>
        </div>

        <div className={styles.controls}>
          <button type="button" className={styles.ctl} aria-label="Previous category" onClick={() => step(-1)}>
            <Chevron dir="left" />
          </button>
          <button
            type="button"
            className={styles.ctl}
            aria-label={userPaused || reduced ? "Resume automatic scrolling" : "Pause automatic scrolling"}
            aria-pressed={userPaused}
            onClick={() => setUserPaused((v) => !v)}
            disabled={reduced}
          >
            <PlayPause playing={!(userPaused || reduced)} />
          </button>
          <button type="button" className={styles.ctl} aria-label="Next category" onClick={() => step(1)}>
            <Chevron dir="right" />
          </button>
        </div>

        {active ? (
          <div
            className={styles.panelScrim}
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) closePanel();
            }}
          >
            <section className={styles.panel} role="dialog" aria-modal="false" aria-labelledby="showcase-panel-title">
              <h3 id="showcase-panel-title" className={styles.panelTitle}>
                {active.headline}
              </h3>
              <p className={styles.panelDesc}>{active.description}</p>
              <ul className={styles.caps}>
                {active.capabilities.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              <p className={styles.fine}>
                Illustration. Modules available in your workspace depend on your organization&apos;s plan and
                permissions. Sign in to continue.
              </p>
              <button ref={closeRef} type="button" className={`${styles.ctl} ${styles.close}`} aria-label="Close details" onClick={closePanel}>
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
                  <path d="M4 4l8 8M12 4l-8 8" />
                </svg>
              </button>
            </section>
          </div>
        ) : null}
      </div>

      <div className={styles.foot}>
        <p className={styles.note}>Drag, swipe or use the arrows to browse</p>
        <p className={styles.note}>&copy; {new Date().getFullYear()} {COMPANY_NAME}</p>
      </div>
    </aside>
  );
}

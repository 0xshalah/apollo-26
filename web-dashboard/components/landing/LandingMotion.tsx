'use client';

import { useRef, type ReactNode } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP, ScrollTrigger);

const MOTION_OK = '(prefers-reduced-motion: no-preference)';
const WIDE = '(min-width: 80rem)';

/** Splits an element's text into per-character spans for the flip-in; returns an undo. */
function splitChars(el: HTMLElement) {
  const text = el.textContent ?? '';
  el.setAttribute('aria-label', text);
  const frag = document.createDocumentFragment();
  const chars: HTMLElement[] = [];
  for (const word of text.split(/(\s+)/)) {
    if (/^\s+$/.test(word)) {
      frag.append(word);
      continue;
    }
    const w = document.createElement('span');
    w.className = 'flap-word';
    w.setAttribute('aria-hidden', 'true');
    for (const c of word) {
      const s = document.createElement('span');
      s.className = 'flap-char';
      s.textContent = c;
      w.append(s);
      chars.push(s);
    }
    frag.append(w);
  }
  el.replaceChildren(frag);
  return {
    chars,
    undo: () => {
      el.textContent = text;
      el.removeAttribute('aria-label');
    },
  };
}

/**
 * Landing-only motion layer.
 *
 * - Content is visible by default, including without JavaScript.
 * - Every selector is scoped to this component.
 * - Only transform and opacity are animated.
 * - Reduced-motion users receive no movement or scroll-linked effects.
 */
export function LandingMotion({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const progress = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const node = root.current;
      const progressNode = progress.current;
      if (!node || !progressNode) return;

      const mm = gsap.matchMedia();

      // Pointer spotlight on cards: a CSS variable feeds a radial gradient in globals.css.
      // It runs for everyone with a fine pointer because it follows the user and never moves on its own.
      const onPointer = (e: PointerEvent) => {
        const card = (e.target as Element | null)?.closest<HTMLElement>('[data-spotlight]');
        if (!card || !node.contains(card)) return;
        const r = card.getBoundingClientRect();
        card.style.setProperty('--spot-x', `${e.clientX - r.left}px`);
        card.style.setProperty('--spot-y', `${e.clientY - r.top}px`);
      };
      node.addEventListener('pointermove', onPointer, { passive: true });

      mm.add(MOTION_OK, () => {
        const heroItems = gsap.utils.toArray<HTMLElement>('[data-hero-item]', node);
        gsap.fromTo(
          heroItems,
          { autoAlpha: 0, y: 18 },
          { autoAlpha: 1, y: 0, duration: 0.72, stagger: 0.07, ease: 'power3.out', clearProps: 'opacity,visibility,transform' },
        );

        // Flip-in headings: each character turns down into place, like a split-flap board.
        // Only the final characters are ever shown.
        const undos: Array<() => void> = [];
        for (const el of gsap.utils.toArray<HTMLElement>('[data-flap]', node)) {
          const { chars, undo } = splitChars(el);
          undos.push(undo);
          gsap.fromTo(
            chars,
            { rotateX: -90, autoAlpha: 0, transformOrigin: '50% 0%' },
            {
              rotateX: 0,
              autoAlpha: 1,
              duration: 0.5,
              ease: 'power2.out',
              stagger: { each: 0.018, from: 'start' },
              delay: el.closest('[data-hero-item]') ? 0.15 : 0,
              scrollTrigger: el.closest('[data-hero-item]') ? undefined : { trigger: el, start: 'top 88%', once: true },
            },
          );
        }

        for (const element of gsap.utils.toArray<HTMLElement>('[data-reveal]', node)) {
          gsap.fromTo(
            element,
            { autoAlpha: 0, y: 26 },
            {
              autoAlpha: 1,
              y: 0,
              duration: 0.68,
              ease: 'power3.out',
              clearProps: 'opacity,visibility,transform',
              scrollTrigger: { trigger: element, start: 'top 92%', once: true },
            },
          );
        }

        // Manifesto: words brighten as the paragraph scrolls through the viewport.
        for (const block of gsap.utils.toArray<HTMLElement>('[data-manifesto]', node)) {
          gsap.fromTo(
            block.querySelectorAll('[data-word]'),
            { opacity: 0.16 },
            {
              opacity: 1,
              ease: 'none',
              stagger: 0.05,
              scrollTrigger: { trigger: block, start: 'top 78%', end: 'bottom 45%', scrub: 0.6 },
            },
          );
        }

        const orbits = gsap.utils.toArray<SVGElement>('[data-orbit]', node);
        for (const orbit of orbits) {
          gsap.to(orbit, {
            y: () => -0.035 * document.documentElement.scrollHeight,
            ease: 'none',
            scrollTrigger: { start: 0, end: 'max', scrub: true },
          });
        }

        gsap.set(progressNode, { scaleX: 0, transformOrigin: 'left center' });
        gsap.to(progressNode, { scaleX: 1, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: true } });

        return () => undos.forEach((u) => u());
      });

      // Pipeline scene: on wide screens the section pins while one frame travels
      // from the ground station to the DSKY and each stage lights as it passes.
      mm.add(`${MOTION_OK} and ${WIDE}`, () => {
        const scene = node.querySelector<HTMLElement>('[data-scene]');
        const packet = scene?.querySelector<HTMLElement>('[data-scene-packet]');
        const track = scene?.querySelector<HTMLElement>('[data-scene-track]');
        if (!scene || !packet || !track) return;
        const steps = gsap.utils.toArray<HTMLElement>('[data-scene-step]', scene);
        const glows = steps.map((s) => s.querySelector<HTMLElement>('[data-scene-glow]'));
        const fill = scene.querySelector<HTMLElement>('[data-scene-fill]');

        const tl = gsap.timeline({
          defaults: { ease: 'none' },
          scrollTrigger: {
            trigger: scene,
            start: 'center center',
            end: () => `+=${Math.round(window.innerHeight * 1.4)}`,
            pin: true,
            scrub: 0.5,
            invalidateOnRefresh: true,
          },
        });
        gsap.set(steps, { opacity: 0.38 });
        gsap.set(glows, { opacity: 0 });
        tl.set(packet, { autoAlpha: 1 });
        if (fill) tl.fromTo(fill, { scaleX: 0 }, { scaleX: 1, duration: steps.length, transformOrigin: 'left center' }, 0);
        tl.fromTo(
          packet,
          { x: 0 },
          { x: () => track.clientWidth - packet.offsetWidth, duration: steps.length },
          0,
        );
        const captionBox = scene.querySelector<HTMLElement>('[data-scene-captions]');
        const captions = gsap.utils.toArray<HTMLElement>('[data-scene-caption]', scene);
        if (captionBox) gsap.set(captionBox, { display: 'block' });
        steps.forEach((step, i) => {
          const at = (i / Math.max(1, steps.length - 1)) * (steps.length - 0.4);
          tl.to(step, { opacity: 1, duration: 0.4 }, at);
          const glow = glows[i];
          if (glow) tl.to(glow, { opacity: 1, duration: 0.4 }, at);
          const caption = captions[i];
          if (!caption) return;
          tl.fromTo(caption, { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: 0.35, ease: 'power2.out' }, at);
          if (i < captions.length - 1) tl.to(caption, { autoAlpha: 0, y: -24, duration: 0.3, ease: 'power2.in' }, at + 0.75);
        });
      });

      return () => {
        node.removeEventListener('pointermove', onPointer);
        mm.revert();
      };
    },
    { scope: root },
  );

  return (
    <div ref={root} className="landing-grain">
      <div ref={progress} aria-hidden="true" className="landing-scroll-progress" />
      {children}
    </div>
  );
}

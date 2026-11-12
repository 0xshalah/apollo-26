'use client';

import { useRef, type ReactNode } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

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

      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (reduceMotion) return;

      const heroItems = gsap.utils.toArray<HTMLElement>('[data-hero-item]', node);
      gsap.fromTo(
        heroItems,
        { autoAlpha: 0, y: 18 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.72,
          stagger: 0.07,
          ease: 'power3.out',
          clearProps: 'opacity,visibility,transform',
        },
      );

      const revealItems = gsap.utils.toArray<HTMLElement>('[data-reveal]', node);
      const revealTweens = new Map<Element, gsap.core.Tween>();
      for (const element of revealItems) {
        revealTweens.set(
          element,
          gsap.fromTo(
            element,
            { autoAlpha: 0, y: 26 },
            {
              autoAlpha: 1,
              y: 0,
              duration: 0.68,
              ease: 'power3.out',
              paused: true,
              clearProps: 'opacity,visibility,transform',
            },
          ),
        );
      }

      const observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            revealTweens.get(entry.target)?.play();
            observer.unobserve(entry.target);
          }
        },
        { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
      );
      revealItems.forEach((element) => observer.observe(element));

      const orbits = gsap.utils.toArray<SVGElement>('[data-orbit]', node);
      const setProgress = gsap.quickSetter(progressNode, 'scaleX');
      const setOrbitY = orbits.map((orbit) => gsap.quickSetter(orbit, 'y', 'px'));
      let frame = 0;

      const renderScroll = () => {
        frame = 0;
        const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
        const ratio = Math.min(1, Math.max(0, window.scrollY / max));
        setProgress(ratio);
        const offset = window.scrollY * -0.035;
        setOrbitY.forEach((setY) => setY(offset));
      };
      const requestScrollRender = () => {
        if (frame !== 0) return;
        frame = window.requestAnimationFrame(renderScroll);
      };

      gsap.set(progressNode, { scaleX: 0, transformOrigin: 'left center' });
      renderScroll();
      window.addEventListener('scroll', requestScrollRender, { passive: true });
      window.addEventListener('resize', requestScrollRender);

      return () => {
        observer.disconnect();
        window.removeEventListener('scroll', requestScrollRender);
        window.removeEventListener('resize', requestScrollRender);
        if (frame !== 0) window.cancelAnimationFrame(frame);
      };
    },
    { scope: root },
  );

  return (
    <div ref={root}>
      <div ref={progress} aria-hidden="true" className="landing-scroll-progress" />
      {children}
    </div>
  );
}

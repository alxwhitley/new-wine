"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { getMannaHeroTransforms } from "@/lib/manna-hero-motion";

import styles from "./manna-dawn-hero.module.css";

type MannaDawnHeroProps = {
  onPrimaryAction: () => void;
};

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function writeMotionVariables(root: HTMLElement, reducedMotion: boolean): void {
  const range = Math.max(1, root.offsetHeight - window.innerHeight);
  const progress = -root.getBoundingClientRect().top / range;
  const values = getMannaHeroTransforms(progress, reducedMotion);

  root.style.setProperty("--manna-background-scale", String(values.backgroundScale));
  root.style.setProperty("--manna-background-y", `${values.backgroundY}%`);
  root.style.setProperty("--manna-copy-opacity", String(values.copyOpacity));
  root.style.setProperty("--manna-copy-y", `${values.copyY}px`);
  root.style.setProperty("--manna-product-scale", String(values.productScale));
  root.style.setProperty("--manna-product-y", `${values.productY}vh`);
  root.style.setProperty("--manna-foreground-scale", String(values.foregroundScale));
  root.style.setProperty("--manna-foreground-y", `${values.foregroundY}%`);
}

export function MannaDawnHero({ onPrimaryAction }: MannaDawnHeroProps) {
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const motion = window.matchMedia(MOTION_QUERY);
    let frame = 0;

    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => writeMotionVariables(root, motion.matches));
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    motion.addEventListener("change", update);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      motion.removeEventListener("change", update);
    };
  }, []);

  return (
    <section ref={rootRef} className={styles.root} aria-labelledby="manna-hero-title">
      <div className={styles.stickyFrame}>
        <Image
          className={styles.background}
          src="/images/hero/manna-dawn-master.png"
          alt=""
          fill
          priority
          sizes="100vw"
        />

        <div className={styles.copy}>
          <div className={styles.eyebrow}><span />Now in beta</div>
          <h1 id="manna-hero-title">Faithful answers from sources you can trust.</h1>
          <p>Rhemata is an AI-assisted Bible study tool that answers from trusted sources rooted in the charismatic tradition — now in early beta, and looking for testers.</p>
          <div className={styles.actions}>
            <Button size="lg" onClick={onPrimaryAction}>Become a test user</Button>
            <Button variant="outline" size="lg" asChild>
              <Link href="/">Try it free — no account needed</Link>
            </Button>
          </div>
        </div>

        <div
          className={styles.productPlaceholder}
          role="img"
          aria-label="Manna application preview placeholder"
        />

        <Image
          className={styles.foreground}
          src="/images/hero/manna-dawn-foreground.png"
          alt=""
          fill
          sizes="100vw"
        />
      </div>
    </section>
  );
}

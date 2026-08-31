"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ProductImagePlaceholder } from "@/components/marketing/product-image-placeholder";
import { getNewWineHeroTransforms } from "@/lib/newwine-hero-motion";

import styles from "./newwine-dawn-hero.module.css";

type NewWineDawnHeroProps = {
  onPrimaryAction: () => void;
};

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function writeMotionVariables(root: HTMLElement, reducedMotion: boolean): void {
  const range = Math.max(1, root.offsetHeight - window.innerHeight);
  const progress = -root.getBoundingClientRect().top / range;
  const values = getNewWineHeroTransforms(progress, reducedMotion);

  root.style.setProperty("--newwine-background-scale", String(values.backgroundScale));
  root.style.setProperty("--newwine-background-y", `${values.backgroundY}%`);
  root.style.setProperty("--newwine-copy-opacity", String(values.copyOpacity));
  root.style.setProperty("--newwine-copy-y", `${values.copyY}px`);
  root.style.setProperty("--newwine-product-scale", String(values.productScale));
  root.style.setProperty("--newwine-product-y", `${values.productY}vh`);
}

export function NewWineDawnHero({ onPrimaryAction }: NewWineDawnHeroProps) {
  const rootRef = useRef<HTMLElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const motion = window.matchMedia(MOTION_QUERY);
    let frame = 0;

    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        writeMotionVariables(root, motion.matches);
        if (motion.matches) {
          videoRef.current?.pause();
        } else {
          void videoRef.current?.play().catch(() => undefined);
        }
      });
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
    <section ref={rootRef} className={styles.root} aria-labelledby="newwine-hero-title">
      <div className={styles.stickyFrame}>
        <video
          ref={videoRef}
          className={styles.background}
          src="/videos/upper-room-hero.mp4"
          autoPlay
          muted
          loop
          playsInline
          aria-hidden="true"
        />

        <div className={styles.copy}>
          <div className={styles.eyebrow}>Spirit-filled Bible study</div>
          <h1 id="newwine-hero-title">Go deeper with voices you can trust.</h1>
          <p>New Wine brings Scripture and trusted Spirit-filled teachers into one grounded study experience—with every answer connected to its sources.</p>
          <div className={styles.actions}>
            <Button className={styles.primaryAction} size="lg" onClick={onPrimaryAction}>Try New Wine</Button>
            <Button className={styles.secondaryAction} variant="outline" size="lg" asChild>
              <Link href="/sources">Explore the sources</Link>
            </Button>
          </div>
        </div>

        <ProductImagePlaceholder
          className={styles.productPlaceholder}
          ratio="hero"
        />

      </div>
    </section>
  );
}

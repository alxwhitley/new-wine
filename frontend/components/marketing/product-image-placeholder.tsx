import { cn } from "@/lib/utils";

import styles from "./product-image-placeholder.module.css";

type ProductImagePlaceholderProps = {
  className?: string;
  ratio?: "landscape" | "portrait" | "hero";
  label?: string;
};

export function ProductImagePlaceholder({
  className,
  ratio = "landscape",
  label = "Product image coming soon",
}: ProductImagePlaceholderProps) {
  return (
    <div
      className={cn(styles.frame, styles[ratio], className)}
      aria-hidden="true"
    >
      <span>{label}</span>
    </div>
  );
}

import Image from "next/image";
import { cx } from "@/utils/cx";

type Props = {
  size?: number;
  className?: string;
  priority?: boolean;
  alt?: string;
};

export function CocomputerMark({ size = 32, className, priority, alt = "CoComputer" }: Props) {
  return (
    <Image
      src="/brand/cocomputer-logo.svg"
      alt={alt}
      width={size}
      height={size}
      priority={priority}
      className={cx("shrink-0 rounded-[10px] object-contain", className)}
    />
  );
}

export function CocomputerLogo({
  size = 32,
  showWordmark = true,
  className,
  wordmarkClassName,
  priority,
}: Props & { showWordmark?: boolean; wordmarkClassName?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <CocomputerMark size={size} priority={priority} />
      {showWordmark ? (
        <span className={cx("font-semibold tracking-tight leading-none", wordmarkClassName)}>CoComputer</span>
      ) : null}
    </span>
  );
}

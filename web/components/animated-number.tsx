"use client";

import { useEffect, useState } from "react";
import { useRef } from "react";

import {
  formatCompact,
  formatCurrency,
  formatMultiplier,
  formatNumber,
  formatPercent,
} from "@/lib/format";

type AnimatedNumberFormat =
  | "currency"
  | "compact"
  | "number"
  | "multiplier"
  | "percent";

interface AnimatedNumberProps {
  value: number;
  format?: AnimatedNumberFormat;
  currency?: string;
  className?: string;
}

export function AnimatedNumber({
  value,
  format = "number",
  currency = "USD",
  className,
}: AnimatedNumberProps) {
  const [displayValue, setDisplayValue] = useState(0);
  const previousValueRef = useRef(0);

  useEffect(() => {
    let frame = 0;
    const startedAt = performance.now();
    const duration = 650;
    const from = previousValueRef.current;
    const to = value;

    const tick = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const nextValue = from + (to - from) * eased;
      setDisplayValue(nextValue);
      if (progress >= 1) {
        previousValueRef.current = to;
      }
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  let formatted = formatNumber(displayValue);
  if (format === "currency") {
    formatted = formatCurrency(displayValue, currency);
  }
  if (format === "compact") {
    formatted = formatCompact(displayValue);
  }
  if (format === "multiplier") {
    formatted = formatMultiplier(displayValue);
  }
  if (format === "percent") {
    formatted = formatPercent(displayValue);
  }

  return <span className={className}>{formatted}</span>;
}

import { Slot } from "@radix-ui/react-slot";
import { clsx } from "clsx";
import type { ButtonHTMLAttributes } from "react";
export function Button({
  variant = "secondary",
  asChild,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  asChild?: boolean;
}) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp className={clsx("btn", `btn-${variant}`, className)} {...props} />
  );
}

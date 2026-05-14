// web/src/components/ui/button-variants.ts
import { cva, type VariantProps } from "class-variance-authority"

export const buttonVariants = cva(
  "alx-press inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors duration-200 ease-out-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-foreground text-background hover:bg-foreground/90",
        outline: "border border-border bg-card hover:bg-muted",
        ghost: "hover:bg-muted",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: { default: "h-9 px-4 py-2", sm: "h-8 px-3", lg: "h-10 px-6" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
)

export type ButtonVariantProps = VariantProps<typeof buttonVariants>

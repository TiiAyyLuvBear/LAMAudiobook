export const COLORS = {
  brand: "#0F766E",
  brandDark: "#134E4A",
  accent: "#F59E0B",
  accentSoft: "#FDE68A",
  ink: "#0B1220",
  muted: "#4B5563",
  surface: "#FFFFFF",
  surfaceSoft: "#F8FAFC",
  stroke: "#D1D5DB",
  success: "#10B981",
  danger: "#EF4444",
  heroStart: "#ECFEFF",
  heroEnd: "#FEFCE8"
} as const;

export type ThemeColor = keyof typeof COLORS;

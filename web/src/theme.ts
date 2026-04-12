import { theme } from "antd";
import type { ThemeConfig } from "antd";

export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: "#6366f1",
    borderRadius: 6,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
};

export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: { colorPrimary: "#818cf8", borderRadius: 6 },
};

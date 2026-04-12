import { theme } from "antd";
import type { ThemeConfig } from "antd";

/**
 * OpenWebUI-inspired tokens: subtle chrome, generous radius, muted
 * surface colour so cards pop against the background without borders.
 */
export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: "#10a37f",
    colorBgLayout: "#fafafa",
    colorBgContainer: "#ffffff",
    colorBorderSecondary: "#efefef",
    borderRadius: 10,
    borderRadiusLG: 14,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    fontSize: 14,
  },
  components: {
    Layout: {
      siderBg: "#171717",
      headerBg: "#ffffff",
      headerHeight: 56,
      bodyBg: "#fafafa",
    },
    Menu: {
      darkItemBg: "#171717",
      darkSubMenuItemBg: "#171717",
      darkItemHoverBg: "#262626",
      darkItemSelectedBg: "#262626",
    },
    Card: {
      boxShadowTertiary: "none",
    },
    Table: {
      headerBg: "#fafafa",
      rowHoverBg: "#fafafa",
    },
  },
};

export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: "#10a37f",
    borderRadius: 10,
    borderRadiusLG: 14,
  },
};

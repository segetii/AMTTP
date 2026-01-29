import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx}",
    "./app/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#6366F1",
        primarySoft: "#8B5CF6",
        background: "#0A0A0F",
        surface: "#12121A",
        borderSubtle: "#1E1E2E",
        text: "#FFFFFF",
        mutedText: "#9CA3AF",
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444",
      },
      borderRadius: {
        sm: "8px",
        lg: "16px",
        full: "9999px",
      },
      spacing: {
        xs: "4px",
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
        xxl: "32px",
      },
      fontSize: {
        "heading-1": "28px",
        "heading-2": "24px",
        "heading-3": "20px",
        "body-lg": "16px",
        "body-md": "14px",
        "body-sm": "12px",
        "label-md": "12px",
        "label-sm": "11px",
      },
    },
  },
  plugins: [],
};

export default config;

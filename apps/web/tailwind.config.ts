import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#f4f2ff",
          100: "#ebe7ff",
          200: "#d9d1ff",
          300: "#bcabff",
          400: "#9c81fb",
          500: "#7c5cf5",
          600: "#6638e6",
          700: "#552bc4",
          800: "#46259d",
          900: "#3a217c",
          950: "#231352",
        },
        ink: {
          900: "#131226",
          950: "#0c0b1a",
        },
      },
      boxShadow: {
        soft: "0 1px 2px rgba(19, 18, 38, 0.04), 0 1px 3px rgba(19, 18, 38, 0.06)",
        glow: "0 8px 24px -8px rgba(102, 56, 230, 0.45)",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./App.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  safelist: [
    {
      pattern:
        /(bg|border)-urgency-(notification|caution|warning|urgentWarning|alert|urgentAlert|extremeUrgency)-(lightBg|lightBorder|darkBg|darkBorder)/,
    },
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#0379d1",
          primaryStrong: "#004ed6",
          secondary: "#0cba75",
          accent: "#05989f",
          surface: "#f7f9fc",
          card: "#ffffff",
          border: "#d7deea",
          muted: "#6b7280",
          ink: "#0e1932"
        },
        status: {
          info: "#0379d1",
          success: "#0cba75",
          warn: "#f5ca0b",
          danger: "#e11d48",
          neutral: "#94a3b8"
        },
        urgency: {
          notification: {
            lightBg: "#81b1b4",
            lightBorder: "#05989f",
            darkBg: "rgb(9, 62, 92)",
            darkBorder: "#05989f"
          },
          caution: {
            lightBg: "#fbedac",
            lightBorder: "#f5ca0b",
            darkBg: "#855b07",
            darkBorder: "#f5ca0b"
          },
          warning: {
            lightBg: "#fed4b1",
            lightBorder: "#fb923c",
            darkBg: "#7c2d12",
            darkBorder: "#fb923c"
          },
          urgentWarning: {
            lightBg: "#fed7aa",
            lightBorder: "#f97316",
            darkBg: "#9a3412",
            darkBorder: "#f97316"
          },
          alert: {
            lightBg: "#fee2e2",
            lightBorder: "#ef4444",
            darkBg: "#7f1d1d",
            darkBorder: "#f87171"
          },
          urgentAlert: {
            lightBg: "#fecaca",
            lightBorder: "#dc2626",
            darkBg: "#991b1b",
            darkBorder: "#f87171"
          },
          extremeUrgency: {
            lightBg: "#fca5a5",
            lightBorder: "#b91c1c",
            darkBg: "#450a0a",
            darkBorder: "#ef4444"
          }
        },
        crisis: {
          bg: "#0b1020",
          panel: "#131b35",
          danger: "#f25f5c",
          warn: "#ffe066",
          ok: "#70c1b3",
          text: "#eaf2ff",
          muted: "#9fb0cc"
        }
      },
      fontFamily: {
        display: ["'Manrope'", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["'Manrope'", "Inter", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "18px",
        xl: "24px",
        pill: "999px"
      },
      boxShadow: {
        soft: "0 8px 24px rgba(0,0,0,0.08)",
        panel: "0 12px 32px rgba(0,0,0,0.14)"
      },
      spacing: {
        13: "3.25rem",
        18: "4.5rem"
      },
      opacity: {
        12: "0.12",
        15: "0.15"
      }
    }
  },
  plugins: []
};

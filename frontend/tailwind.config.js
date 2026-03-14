/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./App.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        crisis: {
          bg: "#0b1020",
          panel: "#131b35",
          danger: "#f25f5c",
          warn: "#ffe066",
          ok: "#70c1b3",
          text: "#eaf2ff",
          muted: "#9fb0cc"
        }
      }
    }
  },
  plugins: []
};


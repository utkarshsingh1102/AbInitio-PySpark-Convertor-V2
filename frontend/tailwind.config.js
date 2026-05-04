/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Anthropic / Claude inspired warm palette.
        cream: {
          50:  "#FBFAF6",
          100: "#FAF9F5",   // base background
          200: "#F5F4ED",
          300: "#EDEBE0",
          400: "#E6E4D9",   // borders
          500: "#D9D7CB",
          600: "#B8B6A8",
        },
        ink: {
          50:  "#FAFAF7",
          100: "#EDECE6",
          200: "#D7D5CD",
          300: "#A6A39A",
          400: "#6F6D65",   // muted secondary text
          500: "#4A4945",   // body text
          600: "#2E2D29",
          700: "#1F1E1B",   // primary text
          800: "#191815",
          900: "#0F0E0C",
        },
        // Coral / burnt-orange — Claude's accent
        coral: {
          50:  "#FDF5F2",
          100: "#FCEBE3",
          200: "#F7D2C2",
          300: "#F0B098",
          400: "#E68A6A",
          500: "#DA7756",   // primary accent
          600: "#C15F3C",
          700: "#A04A2C",
          800: "#7E3A24",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        serif: ['"Tiempos Headline"', "ui-serif", "Georgia", "serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(31, 30, 27, 0.04), 0 4px 16px rgba(31, 30, 27, 0.04)",
        card: "0 1px 3px rgba(31, 30, 27, 0.06)",
      },
    },
  },
  plugins: [],
};

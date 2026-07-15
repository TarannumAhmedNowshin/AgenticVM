import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        avms: {
          ink: "#0f172a",
          accent: "#6366f1",
        },
      },
    },
  },
  plugins: [],
};

export default config;

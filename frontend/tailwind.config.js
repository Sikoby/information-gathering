import sharedPreset from "@ig/ui/tailwind-preset";
import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  presets: [sharedPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../shared/src/**/*.{ts,tsx}",
  ],
  plugins: [typography],
};

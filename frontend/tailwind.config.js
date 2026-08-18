/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#0B0F14',
        surface: '#141A20',
        'surface-2': '#1A222A',
        border: '#2A3340',
        accent: {
          DEFAULT: '#00D4AA',
          hover: '#00E6B8',
          dark: '#0A8F73',
        },
        'text-primary': '#FFFFFF',
        'text-secondary': '#94A3B8',
      },
    },
  },
  plugins: [],
}

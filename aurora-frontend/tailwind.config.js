/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        aurora: {
          bg: '#05070c',
          panel: '#0b1017',
          border: '#1c2734',
          text: '#c9d6e2',
          muted: '#6b7c8f',
          accent: '#35e0c8',
          warn: '#e0b035',
          crit: '#e0475f',
          ok: '#35c97e',
        },
      },
    },
  },
  plugins: [],
};

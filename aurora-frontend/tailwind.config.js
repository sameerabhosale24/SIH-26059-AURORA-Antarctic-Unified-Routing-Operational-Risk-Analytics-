/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /**
         * The console's deep-ocean chrome: background, panels, interactive
         * states and accents, in one scale so the landing page, the app and
         * the map's ocean all read as the same system.
         */
        ocean: {
          950: '#061B2E',
          900: '#0A2A45',
          800: '#0F3A5C',
          700: '#1E6091',
          600: '#2A7CB0',
          500: '#3A96CC',
          400: '#5FB0DD',
          300: '#8ACAE8',
          200: '#B8DEF0',
          100: '#E0F0F8',
        },
        /** Text and highlights. */
        foam: '#FFFFFF',
        /**
         * Operational tones only — health dots, staleness and alarm
         * severity. Deliberately not ocean-themed: a red alarm must stay
         * recognisable as a red alarm.
         */
        aurora: {
          warn: '#e0b035',
          crit: '#e0475f',
          ok: '#35c97e',
        },
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Inter e' incluso nel pacchetto (nessuna richiesta a Google Fonts):
        // l'interfaccia funziona anche in una rete senza accesso a internet.
        sans: ['"Inter Variable"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          dark: '#0f1225',
          darker: '#0a0c16',
          panel: '#1a1f3d',
          border: '#252b4d',
          accent: '#3b82f6',
          accentHover: '#2563eb',
        }
      }
    },
  },
  plugins: [],
}

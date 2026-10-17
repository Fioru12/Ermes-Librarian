/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Instrument Sans e' gia' serrato: -0.025em (il valore standard di `tracking-tight`)
      // faceva toccare le lettere dei titoli grandi.
      letterSpacing: { tight: '-0.012em', tighter: '-0.02em' },
      fontFamily: {
        // Tre voci con tre ruoli, tutte incluse nel pacchetto (nessuna richiesta a
        // Google Fonts: l'interfaccia funziona anche in una rete senza internet).
        //   sans  = la voce del sistema: interfaccia, titoli, pulsanti
        //   serif = la voce del documento: i passaggi citati, cio' che dice il file
        //   mono  = i dati: nomi di file, sezioni, hash, identificatori
        sans: ['"Instrument Sans Variable"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['"Source Serif 4 Variable"', 'Georgia', 'Cambria', 'serif'],
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        // Oltremare: il colore di cio' che e' interattivo e delle citazioni.
        // (Il verde resta "supportato da un documento", l'ambra "nessuna fonte".)
        blue: {
          50: '#eef1ff', 100: '#dfe5ff', 200: '#c3ccff', 300: '#9aa8ff', 400: '#6e82ff',
          500: '#4a61ff', 600: '#3552f5', 700: '#2a40d6', 800: '#2536ab', 900: '#232f87', 950: '#151b50',
        },
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

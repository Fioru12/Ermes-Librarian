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
        // Stile app Windows 11: l'interfaccia usa il carattere di sistema (Segoe UI Variable
        // su Windows, quindi gia' presente: nessun download e aspetto nativo; sugli altri
        // sistemi il carattere di sistema). Resta la voce del documento:
        //   sans  = la voce del sistema: interfaccia, titoli, pulsanti
        //   serif = la voce del documento: i passaggi citati, cio' che dice il file (incluso)
        //   mono  = i dati: nomi di file, sezioni, hash (Cascadia Mono su Windows 11)
        sans: ['"Segoe UI Variable Text"', '"Segoe UI Variable"', '"Segoe UI"', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['"Source Serif 4 Variable"', 'Georgia', 'Cambria', 'serif'],
        mono: ['"Cascadia Mono"', '"Cascadia Code"', '"JetBrains Mono Variable"', 'Consolas', 'ui-monospace', 'monospace'],
      },
      // Angoli Fluent: 4 px per i controlli, 8 px per pannelli e finestre.
      borderRadius: { md: '3px', lg: '4px', xl: '4px', '2xl': '8px', '3xl': '8px' },
      // Ombre leggere: in Windows 11 le superfici sono piatte, solo i flyout hanno ombra.
      boxShadow: {
        lg: '0 2px 8px rgba(0,0,0,0.14)',
        xl: '0 4px 14px rgba(0,0,0,0.14)',
        '2xl': '0 8px 28px rgba(0,0,0,0.22)',
      },
      colors: {
        // Grigi neutri di Windows 11 (al posto dell'ardesia bluastra di Tailwind):
        // 100 = Mica chiaro, 800 = livello sopra il Mica scuro, 900 = Mica scuro.
        slate: {
          50: '#fafafa', 100: '#f3f3f3', 200: '#e5e5e5', 300: '#d1d1d1', 400: '#a0a0a0',
          500: '#949494', 600: '#5a5a5a', 700: '#424242', 800: '#2b2b2b', 900: '#202020', 950: '#181818',
        },
        // Accento: il blu di Windows 11 / Fluent. Verde = "supportato da un documento",
        // ambra = "nessuna fonte", blu = azione o fonte.
        blue: {
          50: '#ebf3fc', 100: '#cfe4fa', 200: '#b4d6fa', 300: '#96c6fa', 400: '#77b7f7',
          500: '#479ef5', 600: '#0f6cbd', 700: '#115ea3', 800: '#0f548c', 900: '#0c3b5e', 950: '#082545',
        },
      },
    },
  },
  plugins: [],
}

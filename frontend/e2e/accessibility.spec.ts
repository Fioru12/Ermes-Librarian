import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

/**
 * Accessibilità automatica: ogni scheda, in tema chiaro e scuro, deve passare
 * axe (WCAG 2.1 A/AA e buone pratiche) senza violazioni.
 *
 * L'audit del 17 ottobre 2026 aveva trovato etichette mancanti su otto menu a
 * tendina, nove interruttori senza nome, due barre laterali con lo stesso nome
 * di landmark, livelli di titolo saltati e contrasti sotto 4.5:1 (grigi su
 * riquadri scuri, pastelli su fondo chiaro). Questo test fa in modo che non
 * tornino senza che qualcuno se ne accorga.
 *
 * Non copre tastiera, lettori di schermo né le interazioni a più passi: axe
 * trova circa un terzo dei problemi di accessibilità, non tutti.
 */

const USERNAME = process.env.ERMES_ADMIN_USERNAME ?? 'admin'
const PASSWORD = process.env.ERMES_ADMIN_PASSWORD ?? ''

const TABS = [
  'Assistente',
  'Studio',
  'Biblioteche e documenti',
  'Collegamenti esterni',
  'Stato del sistema',
  'Impostazioni',
  'Domande senza risposta',
  'Accessi e chiavi API',
  'Registro attività',
]

test.skip(!PASSWORD, 'ERMES_ADMIN_PASSWORD non impostata: E2E saltati')

for (const theme of ['dark', 'light'] as const) {
  test(`nessuna violazione di accessibilità in nessuna scheda (tema ${theme})`, async ({ page }) => {
    await page.addInitScript(value => {
      try {
        window.localStorage.setItem('ermes-theme', value)
      } catch {
        // storage bloccato: si resta sul tema predefinito
      }
    }, theme)

    await page.goto('/')
    const user = page.getByPlaceholder(/nome utente/i)
    const assistant = page.getByRole('button', { name: /assistente/i })
    await expect(user.or(assistant).first()).toBeVisible({ timeout: 30_000 })

    const audit = async () =>
      new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze()
    const describe = (violations: Awaited<ReturnType<typeof audit>>['violations']) =>
      violations.map(v => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target.join(' ')}`)

    if (await user.isVisible()) {
      expect(describe((await audit()).violations), 'schermata di accesso').toEqual([])
      await user.fill(USERNAME)
      await page.getByLabel(/password/i).fill(PASSWORD)
      await page.getByRole('button', { name: /accedi/i }).click()
    }
    await expect(assistant).toBeVisible({ timeout: 30_000 })

    for (const name of TABS) {
      await page.getByRole('button', { name, exact: true }).first().click()
      // Le schede sono caricate a richiesta: aspetta che il contenuto sia arrivato.
      await expect(page.getByText(/Caricamento/)).toHaveCount(0, { timeout: 20_000 })
      await page.waitForTimeout(500)
      expect(describe((await audit()).violations), `scheda "${name}"`).toEqual([])

      // Cio' che axe non dice: un solo titolo di primo livello per schermata e nessun campo
      // senza nome (un lettore di schermo direbbe soltanto "campo di testo").
      const lettura = await page.evaluate(() => {
        const visibile = (el: Element) => {
          const b = el.getBoundingClientRect()
          return b.width > 0 && b.height > 0 && getComputedStyle(el).visibility !== 'hidden'
        }
        const campiSenzaNome = Array.from(document.querySelectorAll('input,select,textarea'))
          .filter(e => visibile(e) && (e as HTMLInputElement).type !== 'hidden')
          .filter(e => !(e as HTMLInputElement).labels?.length && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby'))
          .map(e => e.outerHTML.slice(0, 90))
        const h1 = Array.from(document.querySelectorAll('h1')).filter(visibile).length
        return { campiSenzaNome, h1 }
      })
      expect(lettura.h1, `scheda "${name}": titoli di primo livello`).toBe(1)
      expect(lettura.campiSenzaNome, `scheda "${name}": campi senza nome`).toEqual([])
    }
  })
}

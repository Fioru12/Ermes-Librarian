import { expect, test } from '@playwright/test'

/**
 * Copre il percorso documentale completo nel browser reale:
 *
 *   creazione biblioteca -> upload -> indicizzazione -> ricerca ->
 *   pannello ACL per-documento -> card coerenza indice.
 *
 * A differenza dello spec evidence-and-isolation non richiede i corpora demo:
 * crea tutto quello che gli serve con nomi univoci, quindi puo' girare su
 * qualsiasi istanza vuota appena avviata.
 */

const USERNAME = process.env.ERMES_ADMIN_USERNAME ?? 'admin'
const PASSWORD = process.env.ERMES_ADMIN_PASSWORD ?? ''

test.skip(!PASSWORD, 'ERMES_ADMIN_PASSWORD non impostata: E2E saltati')

async function login(page: import('@playwright/test').Page) {
  await page.goto('/')
  const user = page.getByPlaceholder(/nome utente/i)
  const assistant = page.getByRole('button', { name: /assistente/i })
  await expect(user.or(assistant).first()).toBeVisible({ timeout: 30_000 })
  if (await user.isVisible()) {
    await user.fill(USERNAME)
    await page.getByLabel(/password/i).fill(PASSWORD)
    await page.getByRole('button', { name: /accedi/i }).click()
  }
  await expect(assistant).toBeVisible({ timeout: 30_000 })
}

test('upload, indicizzazione e gestione accessi per-documento', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /biblioteche e documenti/i }).click()

  // ── Biblioteca dedicata, nome univoco per non collidere tra esecuzioni ──
  const libraryName = `ACL E2E ${Date.now()}`
  await page.locator('#new-library-name').fill(libraryName)
  await page.getByRole('button', { name: 'Crea biblioteca' }).click()
  await expect(page.getByText(libraryName).first()).toBeVisible({ timeout: 15_000 })

  // ── Upload di un markdown generato al volo ──
  const content = '# Policy ferie\nLe richieste di ferie vanno presentate dieci giorni prima tramite il portale HR.'
  await page.getByLabel(/carica documento/i).setInputFiles({
    name: 'policy-ferie.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from(content, 'utf-8'),
  })

  // ── Indicizzazione: lo stato passa da In attesa/Indicizzazione a Pronto ──
  const documentCard = page.locator('article', { hasText: 'policy-ferie.md' })
  await expect(documentCard).toBeVisible({ timeout: 15_000 })
  await expect(documentCard.getByText(/^Pronto$/)).toBeVisible({ timeout: 60_000 })

  // ── Ricerca nella biblioteca trova il passaggio ──
  const search = page.getByPlaceholder(/cerca/i)
  await search.fill('ferie portale HR')
  await search.press('Enter')
  await expect(page.getByText(/portale HR/).first()).toBeVisible({ timeout: 15_000 })

  // ── Pannello ACL: solo l'owner/admin lo vede; allow-list modificabile ──
  await documentCard.getByRole('button', { name: /accessi/i }).click()
  const panel = page.locator('section[aria-label="Accessi documento"]')
  await expect(panel).toBeVisible()
  await expect(panel.getByText(/Nessuna restrizione/)).toBeVisible()

  await panel.getByPlaceholder(/autorizzare/i).fill(USERNAME)
  await panel.getByRole('button', { name: /autorizza/i }).click()
  await expect(panel.locator('li', { hasText: USERNAME })).toBeVisible({ timeout: 15_000 })

  // La rimozione riporta lo stato senza restrizioni (PUT con lista vuota).
  await panel.locator('li', { hasText: USERNAME }).getByRole('button', { name: /rimuovi/i }).click()
  await expect(panel.getByText(/Nessuna restrizione/)).toBeVisible({ timeout: 15_000 })

  // ── Health: la nuova card coerenza indice e' presente e senza anomalie ──
  await page.getByRole('button', { name: /stato sistema/i }).click()
  await expect(page.getByText(/coerenza indice/i)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/originali, vettori e righe allineati/i)).toBeVisible()
})
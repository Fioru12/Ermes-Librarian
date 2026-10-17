import { expect, test, type Page } from '@playwright/test'

/**
 * Uso da sola tastiera: ciò che axe non vede.
 *
 * Esplorando l'app con Tab (17 ottobre 2026) si è trovato che: dopo l'accesso
 * servivano 12 pressioni di Tab prima di arrivare al contenuto; aprendo la
 * finestra di una citazione il focus restava sul pulsante sotto lo sfondo
 * scuro. Questi due test li tengono corretti.
 */

const USERNAME = process.env.ERMES_ADMIN_USERNAME ?? 'admin'
const PASSWORD = process.env.ERMES_ADMIN_PASSWORD ?? ''

test.skip(!PASSWORD, 'ERMES_ADMIN_PASSWORD non impostata: E2E saltati')

async function login(page: Page) {
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

test('il primo Tab porta al link "Vai al contenuto", che sposta il focus sul contenuto', async ({ page }) => {
  await login(page)
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await page.keyboard.press('Tab')

  const link = page.getByRole('link', { name: 'Vai al contenuto' })
  await expect(link).toBeFocused()
  await expect(link).toBeVisible()

  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
})

test('la finestra di una citazione prende il focus, lo trattiene, si chiude con Esc e lo restituisce', async ({ page }) => {
  await login(page)
  await page.locator('select').first().selectOption({ label: 'Northstar Works Demo' })
  await page.getByPlaceholder(/domanda/i).fill('What is the annual learning budget per employee?')
  await page.keyboard.press('Enter')
  await expect(page.locator('text=/Basata su \\d+ font[ei]/').first()).toBeVisible({ timeout: 45_000 })

  const citazione = page.getByRole('button', { name: /^Fonte \d/ }).first()
  await citazione.focus()
  await page.keyboard.press('Enter')

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  expect(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'))).toBe(true)

  // Tab non esce dalla finestra, per quante volte lo si prema
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'))).toBe(true)
  }

  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(citazione).toBeFocused()
})

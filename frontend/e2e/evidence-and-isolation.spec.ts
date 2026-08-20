import { expect, test } from '@playwright/test'

/**
 * These tests assert the two claims the product is actually sold on:
 *
 *   1. an answer either cites its sources or abstains — it never invents one;
 *   2. retrieval never crosses a library boundary.
 *
 * Both are checked through the browser against a running instance, because
 * both have already been shown to pass at the unit level while failing in
 * reality (see docs/CODE_REVIEW.md, finding 17).
 *
 * Requires the demo corpora loaded: scripts/run_demo_validation.py.
 */

const USERNAME = process.env.ERMES_ADMIN_USERNAME ?? 'admin'
const PASSWORD = process.env.ERMES_ADMIN_PASSWORD ?? ''

/** Only Northstar documents mention the learning budget. */
const NORTHSTAR_ONLY = 'What is the annual learning budget per employee?'

test.skip(!PASSWORD, 'ERMES_ADMIN_PASSWORD non impostata: E2E saltati')

async function login(page: import('@playwright/test').Page) {
  await page.goto('/')

  const user = page.getByPlaceholder(/nome utente/i)
  const assistant = page.getByRole('button', { name: /assistente/i })

  // The SPA shows either the login form or the workspace, and decides only
  // after its first API call. Testing `count() > 0` right away silently read
  // "no form yet" as "already signed in", skipped the login entirely, and
  // then timed out waiting for a workspace that was never going to appear.
  // Wait for whichever of the two actually renders before acting.
  await expect(user.or(assistant).first()).toBeVisible({ timeout: 30_000 })

  if (await user.isVisible()) {
    await user.fill(USERNAME)
    await page.getByLabel(/password/i).fill(PASSWORD)
    await page.getByRole('button', { name: /accedi/i }).click()
  }

  await expect(assistant).toBeVisible({ timeout: 30_000 })
}

async function ask(page: import('@playwright/test').Page, library: string, question: string) {
  await page.locator('select').first().selectOption({ label: library })

  // The assistant renders either a citation banner or an abstention banner.
  // Waiting for "the last banner to be visible" races: a banner from an
  // earlier turn already satisfies it, so the assertion can read the previous
  // answer. Wait for the count to grow instead, which is unambiguous.
  const banner = page.locator('text=/Basata su \\d+ fonti|Evidenza insufficiente/')
  const before = await banner.count()

  const box = page.getByPlaceholder(/domanda/i)
  await box.fill(question)
  await box.press('Enter')

  await expect(banner).toHaveCount(before + 1, { timeout: 45_000 })
  return banner.last()
}

test('un utente autenticato vede l-assistente', async ({ page }) => {
  await login(page)
  await expect(page).toHaveTitle(/Ermes/i)
})

test('una risposta supportata cita file, versione e sezione', async ({ page }) => {
  await login(page)
  const banner = await ask(page, 'Northstar Works Demo', NORTHSTAR_ONLY)

  await expect(banner).toContainText(/Basata su \d+ fonti/)
  await expect(page.getByText('Fonti').last()).toBeVisible()

  // A citation is only useful if it names a retrievable original.
  const citation = page.locator('text=/\\.md · v\\d+ · Sezione:/').first()
  await expect(citation).toBeVisible()
  await expect(page.getByRole('button', { name: /apri originale/i }).first()).toBeVisible()
})

test('il recupero non attraversa il confine fra biblioteche', async ({ page }) => {
  await login(page)

  // The very question Northstar answers must find nothing in Meridian:
  // the two corpora are unrelated, so a citation here would mean leakage.
  const banner = await ask(page, 'Meridian Precision Works Demo', NORTHSTAR_ONLY)
  await expect(banner).toContainText(/Evidenza insufficiente/)

  // Leakage shows up as citations, not as the words of the question: the
  // question itself is echoed in the transcript, so searching the page for
  // its wording proves nothing (this assertion was wrong on first writing).
  await expect(page.getByRole('button', { name: /apri originale/i })).toHaveCount(0)
  await expect(page.locator('text=/\\.md · v\\d+ · Sezione:/')).toHaveCount(0)
})

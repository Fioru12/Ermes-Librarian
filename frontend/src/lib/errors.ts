/**
 * Message of an unknown thrown value, for user-facing notifications.
 *
 * `catch (err: any)` was the only reason `no-explicit-any` was switched off
 * in eslint.config.js — 23 occurrences, every one of them reading
 * `err.message`. TypeScript types a caught value as `unknown`, which is the
 * truth: fetch rejects with a TypeError, our own code throws Error, and a
 * JSON body can be anything. This narrows once, here.
 */
export function errorMessage(err: unknown, fallback = 'Errore inatteso'): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return fallback
}

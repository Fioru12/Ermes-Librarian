import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // The project does not use the React Compiler yet; these checks produce
      // false positives for ordinary async data loading effects.
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/exhaustive-deps': 'off',
      'react-refresh/only-export-components': 'off',
      // Both were 'off' until 18 September 2026. The only `any` in product
      // code was `catch (err: any)` (23 times) — replaced by lib/errors.ts.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
    },
  },
  {
    // Test doubles are untyped by nature: fetch mocks return whatever the
    // test needs. Keeping `any` legal here is not a loophole for product code.
    files: ['**/*.test.{ts,tsx}', '**/__tests__/**'],
    rules: { '@typescript-eslint/no-explicit-any': 'off' },
  },
])

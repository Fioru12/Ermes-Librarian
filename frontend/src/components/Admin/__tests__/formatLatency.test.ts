import { describe, it, expect } from 'vitest'
import { formatLatency } from '../AnalyticsDashboard'

describe('formatLatency', () => {
  it('mostra i millisecondi interi sotto il secondo', () => {
    expect(formatLatency(0)).toBe('0 ms')
    expect(formatLatency(412.7)).toBe('413 ms')
  })
  it('passa ai secondi con una cifra decimale all\'italiana', () => {
    expect(formatLatency(7061.26)).toBe('7,1 s')
    expect(formatLatency(1000)).toBe('1 s')
  })
  it('non scrive NaN', () => {
    expect(formatLatency(Number.NaN)).toBe('—')
  })
})

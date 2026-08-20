import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { InlineMarkdown, tokenizeInline } from '../InlineMarkdown'

describe('tokenizeInline', () => {
  it('splits bold, italic and code out of surrounding text', () => {
    expect(tokenizeInline('budget of **EUR 750** per year')).toEqual([
      { type: 'text', value: 'budget of ' },
      { type: 'bold', value: 'EUR 750' },
      { type: 'text', value: ' per year' },
    ])
    expect(tokenizeInline('see *policy* and `config.py`')).toEqual([
      { type: 'text', value: 'see ' },
      { type: 'italic', value: 'policy' },
      { type: 'text', value: ' and ' },
      { type: 'code', value: 'config.py' },
    ])
  })

  it('leaves unmatched or stray markers as literal text', () => {
    expect(tokenizeInline('2 * 3 = 6')).toEqual([{ type: 'text', value: '2 * 3 = 6' }])
    expect(tokenizeInline('**unclosed')).toEqual([{ type: 'text', value: '**unclosed' }])
  })

  it('handles empty input without throwing', () => {
    expect(tokenizeInline('')).toEqual([])
  })
})

describe('InlineMarkdown', () => {
  it('renders emphasis instead of showing raw markers', () => {
    render(<InlineMarkdown text="budget of **EUR 750**" />)
    expect(screen.getByText('EUR 750').tagName).toBe('STRONG')
    expect(screen.queryByText(/\*\*/)).toBeNull()
  })

  it('never injects markup from document content', () => {
    // Excerpts come from user-uploaded documents, which are untrusted input.
    // The component must escape them, never interpret them as HTML.
    const hostile = '<img src=x onerror="alert(1)"> and <script>alert(2)</script>'
    const { container } = render(<InlineMarkdown text={hostile} />)

    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.textContent).toContain('<script>alert(2)</script>')
  })
})

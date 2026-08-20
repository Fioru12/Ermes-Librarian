import React from 'react';

/**
 * Renders the inline emphasis found in excerpts quoted from Markdown source
 * documents (**bold**, *italic*, `code`), which would otherwise show their raw
 * markers to the reader.
 *
 * Deliberately hand-rolled and deliberately NOT using dangerouslySetInnerHTML:
 * this text comes from user-uploaded documents, which the product treats as
 * untrusted input. Building React nodes keeps the content escaped by default,
 * so a document can never inject markup into the page.
 *
 * Block-level Markdown is intentionally not handled: an evidence excerpt is a
 * quotation, not a document to re-typeset.
 */

type Token = { type: 'text' | 'bold' | 'italic' | 'code'; value: string };

const PATTERN = /(\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*)|`[^`\n]+`)/g;

export function tokenizeInline(input: string): Token[] {
  const tokens: Token[] = [];
  let last = 0;

  for (const match of input.matchAll(PATTERN)) {
    const index = match.index ?? 0;
    if (index > last) {
      tokens.push({ type: 'text', value: input.slice(last, index) });
    }
    const raw = match[0];
    if (raw.startsWith('**')) {
      tokens.push({ type: 'bold', value: raw.slice(2, -2) });
    } else if (raw.startsWith('`')) {
      tokens.push({ type: 'code', value: raw.slice(1, -1) });
    } else {
      tokens.push({ type: 'italic', value: raw.slice(1, -1) });
    }
    last = index + raw.length;
  }

  if (last < input.length) {
    tokens.push({ type: 'text', value: input.slice(last) });
  }
  return tokens;
}

export function InlineMarkdown({ text, className }: { text: string; className?: string }) {
  const tokens = React.useMemo(() => tokenizeInline(text ?? ''), [text]);

  return (
    <span className={className}>
      {tokens.map((token, index) => {
        switch (token.type) {
          case 'bold':
            return <strong key={index} className="font-semibold">{token.value}</strong>;
          case 'italic':
            return <em key={index}>{token.value}</em>;
          case 'code':
            return (
              <code key={index} className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.9em]">
                {token.value}
              </code>
            );
          default:
            return <React.Fragment key={index}>{token.value}</React.Fragment>;
        }
      })}
    </span>
  );
}

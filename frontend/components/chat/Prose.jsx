// @ts-check
'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * A coach's words (P5.3; owner, 15 Nov 2026): a safe Markdown subset, so a heading,
 * bold, a list or a small comparison table reads as meant. Never a link, an image or
 * raw HTML: a link shows as its words, whatever the text holds (`javascript:`, `hxxp`,
 * `[.]`), because sources are the only links (C.6, Part E #59). A heading reads as a
 * bold line inside the answer.
 */

const ALLOWED = ['p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'h4',
                 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'code', 'blockquote', 'del']
const asHeading = ({ children }) => <p><strong>{children}</strong></p>
const COMPONENTS = { h1: asHeading, h2: asHeading, h3: asHeading, h4: asHeading }

/** @param {{ text: string }} props */
export default function Prose({ text }) {
  return (
    <div className="prose prose-holos max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} allowedElements={ALLOWED} unwrapDisallowed
                     skipHtml components={COMPONENTS} urlTransform={() => null}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

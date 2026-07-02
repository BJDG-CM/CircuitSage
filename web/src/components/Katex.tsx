import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

export function Katex({ tex, block = false }: { tex: string; block?: boolean }) {
  const html = useMemo(
    () => katex.renderToString(tex, { displayMode: block, throwOnError: false }),
    [tex, block],
  )
  const Tag = block ? 'div' : 'span'
  return <Tag className={block ? 'katex-block' : undefined} dangerouslySetInnerHTML={{ __html: html }} />
}

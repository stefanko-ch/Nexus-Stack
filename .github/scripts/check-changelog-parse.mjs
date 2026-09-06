// Fail a PR whose squash message Release Please cannot parse.
//
// WHY THIS EXISTS. Release Please drops a commit it cannot parse, silently,
// with a green workflow. It logs one line and carries on:
//
//     ❯ commit could not be parsed: 67b46c7 fix(ci): Stop seven D1 calls …
//     ✔ Considering: 3 commits
//
// Four commits existed. The dropped one never reached CHANGELOG.md and
// nothing failed — no red check, no warning on the release PR. It has
// happened twice (#769 before v0.75.0, #797 before v0.77.0) and both times
// it was caught only because somebody read the release PR before merging,
// which is not a control.
//
// Repairing it afterwards means hand-editing CHANGELOG.md on
// `release-please--branches--main` AND the release PR body, in that order,
// before anything else merges — any further commit to main regenerates that
// branch and discards the repair. Catching it here instead makes the fix an
// edit to the PR description.
//
// WHAT IT CHECKS. GitHub composes the squash commit as the PR title plus
// " (#N)" as the subject, and the PR body verbatim as the body — verified
// against #797, whose merged commit body matches its PR body once GitHub's
// line wrapping is normalised. The wrapping itself is not the trigger: the
// raw PR body and the wrapped commit message both throw.
//
// The parser is the one Release Please actually uses. Note it is
// `@conventional-commits/parser`, NOT `conventional-commits-parser` — a
// different package, and the reason an earlier investigation concluded the
// message parsed fine. Version pinned to match release-please 17.x's
// `^0.4.1`.
//
// WHAT IT DOES NOT DO. It does not explain WHY a message fails. The trigger
// has never been isolated: for #797 the parser first throws inside a fenced
// bash block at `ENABLED_SERVICES=$(`, but closing that parenthesis does not
// make the whole body parse, so there is more than one. Guessing a content
// rule from that would be worse than useless, which is why this reports the
// location and leaves the diagnosis to a human.

import { readFileSync } from 'node:fs'

import { parser } from '@conventional-commits/parser'

// The prefix scan below reparses a growing prefix per line, which is
// quadratic in the body length. Measured with this parser: 200 lines takes
// 0.9s, 1000 takes 25s and 3000 takes 245s. A PR body may be 65536
// characters, so an unbounded scan hands a fork PR minutes of runner CPU.
// Real bodies in this repo run 50-123 lines; 400 costs about 4s and leaves
// ample headroom.
const MAX_SCANNED_LINES = 400

const title = process.env.PR_TITLE ?? ''
const body = process.env.PR_BODY ?? ''
const number = process.env.PR_NUMBER ?? '?'

if (!title) {
  console.error('❌ PR_TITLE is empty — this step cannot check anything.')
  process.exit(1)
}

// GitHub appends " (#N)" to the title when it composes the squash subject.
const subject = `${title} (#${number})`
const message = body ? `${subject}\n\n${body}` : `${subject}\n`

const throwsOn = (text) => {
  try {
    parser(text)
    return null
  } catch (error) {
    return error
  }
}

//: The runner reads a step's stderr for workflow commands and strips leading
//: whitespace first, so a title beginning with `::error::` would forge an
//: annotation from this script's own output. Only the title is interpolated
//: into a line of its own; the body excerpts below all carry a fixed prefix.
const neutralise = (text) => text.replaceAll('::', ':\u200b:')

//: The commit type, read out of the parser's own AST rather than a regex
//: over the subject — the parser is the authority on where the type ends.
const typeOf = (text) => {
  let found = null
  const walk = (node) => {
    if (!node || typeof node !== 'object' || found !== null) return
    if (node.type === 'type' && typeof node.value === 'string') {
      found = node.value
      return
    }
    for (const child of node.children ?? []) walk(child)
  }
  try {
    walk(parser(text))
  } catch {
    return null
  }
  return found
}

//: Types Release Please is configured to understand. A type absent from this
//: list parses fine and then has no section to land in — the same silent
//: outcome this check exists to prevent, reached a different way. `hidden`
//: entries stay allowed: `test:` and `style:` are deliberately kept out of
//: the changelog, which is a decision rather than a failure.
const configuredTypes = () => {
  try {
    const config = JSON.parse(readFileSync('release-please-config.json', 'utf8'))
    const sections = []
    const walk = (node) => {
      if (!node || typeof node !== 'object') return
      if (Array.isArray(node['changelog-sections'])) sections.push(...node['changelog-sections'])
      for (const value of Object.values(node)) walk(value)
    }
    walk(config)
    return new Set(sections.map((section) => section.type).filter(Boolean))
  } catch {
    // Unreadable or restructured config: say nothing rather than invent a
    // failure. The parse check above is unaffected.
    return null
  }
}

const failure = throwsOn(message)

if (!failure) {
  const known = configuredTypes()
  const type = typeOf(message)
  if (known && known.size > 0 && type && !known.has(type)) {
    console.error('')
    console.error(`❌ \`${neutralise(type)}:\` is not a type Release Please is configured for.`)
    console.error('')
    console.error('   The message parses, so nothing will fail — and the entry will')
    console.error('   have no section to land in. Same silent outcome, different route.')
    console.error('')
    console.error(`   Configured: ${[...known].sort().join(', ')}`)
    console.error('')
    console.error('   `test` and `style` are configured but hidden on purpose; both are')
    console.error('   fine to use. Anything outside the list is not.')
    console.error('')
    process.exit(1)
  }
  console.log(`✅ Release Please can parse the squash message for #${number}.`)
  process.exit(0)
}

// Is the subject itself the problem? Ask before scanning the body, because
// an unparseable subject makes EVERY body prefix fail and the scan below
// would then blame body line 1 — a confident, wrong diagnostic of exactly
// the kind this whole check exists to prevent.
const subjectFails = throwsOn(`${subject}\n`) !== null

// Narrow it down: the shortest body prefix that already fails. This is a
// location, not a cause — see the note above.
const lines = body.split('\n')
const scanned = Math.min(lines.length, MAX_SCANNED_LINES)
let firstBadLine = null
if (!subjectFails) {
  for (let n = 1; n <= scanned; n++) {
    if (throwsOn(`${subject}\n\n${lines.slice(0, n).join('\n')}`)) {
      firstBadLine = n
      break
    }
  }
}

console.error('')
console.error('❌ Release Please cannot parse the commit message this PR would produce.')
console.error('')
console.error(`   Parser error: ${failure.message?.split('\n')[0] ?? '(no message)'}`)
console.error('')
console.error('   If this merges, Release Please will DROP the commit from the')
console.error('   changelog without failing. Its own workflow stays green and the')
console.error('   entry simply never appears.')
console.error('')

if (subjectFails) {
  console.error('   The TITLE is what the parser rejects, before the description is')
  console.error('   even reached:')
  console.error('')
  console.error(`     ${neutralise(subject)}`)
  console.error('')
  console.error('   A conventional-commit subject looks like `type(scope): description`.')
} else if (firstBadLine !== null) {
  const from = Math.max(1, firstBadLine - 2)
  console.error(`   Parsing first fails at body line ${firstBadLine}:`)
  console.error('')
  for (let i = from; i <= firstBadLine; i++) {
    const marker = i === firstBadLine ? '>' : ' '
    console.error(`   ${marker} ${String(i).padStart(4)} | ${lines[i - 1]}`)
  }
  console.error('')
  console.error('   That is where the parser gives up first, not necessarily the only')
  console.error('   problem — fixing it may reveal another. Removing the surrounding')
  console.error('   block from the description and re-running is the fastest way through.')
} else if (scanned < lines.length) {
  console.error(`   The description is ${lines.length} lines; only the first`)
  console.error(`   ${MAX_SCANNED_LINES} were scanned and none of them fails on its own.`)
  console.error('   The scan is quadratic, so it is capped rather than left to run for')
  console.error('   minutes. Shorten the description and push again to locate it.')
} else {
  console.error('   The failure could not be narrowed to a single body line: the whole')
  console.error('   message is rejected while every prefix of it parses. That is')
  console.error('   unusual — attach the message to the issue rather than guessing.')
}

console.error('')
console.error(
  subjectFails
    ? '   Nothing about the CODE is wrong. Edit the PR title.'
    : '   Nothing about the CODE is wrong. Edit the PR description.'
)
console.error('')
process.exit(1)

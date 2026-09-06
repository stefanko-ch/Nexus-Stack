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

import { parser } from '@conventional-commits/parser'

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

const failure = throwsOn(message)

if (!failure) {
  console.log(`✅ Release Please can parse the squash message for #${number}.`)
  process.exit(0)
}

// Narrow it down: the shortest body prefix that already fails. This is a
// location, not a cause — see the note above.
const lines = body.split('\n')
let firstBadLine = null
for (let n = 1; n <= lines.length; n++) {
  if (throwsOn(`${subject}\n\n${lines.slice(0, n).join('\n')}`)) {
    firstBadLine = n
    break
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

if (firstBadLine !== null) {
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
} else {
  console.error('   The failure could not be narrowed to a body line, which points at')
  console.error('   the title rather than the description.')
}

console.error('')
console.error('   Nothing about the CODE is wrong. Edit the PR description.')
console.error('')
process.exit(1)

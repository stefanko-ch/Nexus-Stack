/**
 * Which stack is this panel? Baked in at build time.
 *
 * Two Nexus-Stack panels are otherwise pixel-identical — same logo, same
 * header, same buttons, one of which is Teardown. With a Conductor-Stack
 * and a production stack open in neighbouring tabs, the only thing left to
 * tell them apart would be the URL, and the URL is what an operator is not
 * looking at while reaching for a button.
 *
 * So a stack that sets STACK_LABEL says which machine it is in the two
 * places the eye already rests: the heading, and the browser tab title.
 *
 * Read from `process.env`, not from a Pages binding or an API call.
 * `npm run build` runs on the GitHub runner (spin-up.yml and
 * setup-control-plane.yaml) and `wrangler pages deploy` uploads the
 * finished `dist`, so Cloudflare's own `environment_variables` never reach
 * this build — and `wrangler pages deploy` deletes Terraform-managed ones
 * anyway (see the comment in tofu/control-plane/main.tf). Fetching it at
 * runtime would also make the label arrive *after* the buttons are
 * clickable, which defeats the point.
 *
 * The label takes the `h1` rather than sitting in a badge below it (#841).
 * A badge lost: it was one small element inside a header that still said
 * *Nexus Stack, in green* everywhere else — 360px logo, 2.5rem heading,
 * green tagline — and the eye resolved the page before reaching it.
 * Enlarging it did not help either, because a loud badge competes with the
 * heading instead of replacing the signal.
 */

/** Empty means "look exactly as before". */
export const stackLabel: string = (process.env.STACK_LABEL ?? '').trim();

/**
 * Operator-supplied and interpolated into a style attribute, so it is
 * constrained rather than trusted. Two forms are accepted: a CSS hex
 * colour, or one of the 148 CSS named colours. Anything else is dropped
 * and the panel keeps its own accent.
 *
 * Since #841 the value lands on `--accent` at the document root, so it
 * cascades to the whole panel rather than to a single badge. That widens
 * what a bad value costs, not what an unvalidated one could do: this is the
 * only thing standing between the environment variable and the attribute.
 *
 * It deliberately does NOT reach `--status-ok`. A stack with a violet accent
 * still shows green for healthy, because that green sits in a set with
 * `--error` and `--warning`, and recolouring it would make the palette say
 * something untrue.
 *
 * **A shape test is not enough, and the difference is not cosmetic.** A
 * custom property accepts any token sequence, so an unrecognised word is
 * stored happily and only fails where it is *used* — at which point
 * `color: var(--accent)` is invalid at computed-value time. CSS does not
 * then fall back to an earlier declaration; the property inherits or resets.
 * So `STACK_ACCENT=foobar` would leave the heading, tagline, glow, masked
 * logo and — since part A — every accented element on every page with no
 * colour at all rather than the panel's green, and the setup guide's promise
 * that invalid values are ignored would be false.
 *
 * The keyword list is therefore an allowlist, not a shape. It also settles
 * the keywords that *are* valid CSS and still wrong here — `transparent`
 * and `currentcolor` are not named colours, and neither are `inherit`,
 * `initial`, `unset` or `revert`. `transparent` is the one that would hurt
 * most: it erases heading, glow, tagline, nav link and the masked logo at
 * once, leaving an empty header on the one stack that asked to be
 * recognisable.
 */
const HEX_PATTERN = /^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

/**
 * The 147 CSS3 named colours plus `rebeccapurple`, which CSS Color 4 added.
 * Generated from the `webcolors` package rather than typed out, because a
 * single mis-spelling here silently rejects a colour an operator can read
 * in the spec.
 */
const NAMED_COLOURS = new Set([
	'aliceblue', 'antiquewhite', 'aqua', 'aquamarine', 'azure', 'beige',
	'bisque', 'black', 'blanchedalmond', 'blue', 'blueviolet', 'brown',
	'burlywood', 'cadetblue', 'chartreuse', 'chocolate', 'coral',
	'cornflowerblue', 'cornsilk', 'crimson', 'cyan', 'darkblue',
	'darkcyan', 'darkgoldenrod', 'darkgray', 'darkgreen', 'darkgrey',
	'darkkhaki', 'darkmagenta', 'darkolivegreen', 'darkorange',
	'darkorchid', 'darkred', 'darksalmon', 'darkseagreen',
	'darkslateblue', 'darkslategray', 'darkslategrey', 'darkturquoise',
	'darkviolet', 'deeppink', 'deepskyblue', 'dimgray', 'dimgrey',
	'dodgerblue', 'firebrick', 'floralwhite', 'forestgreen', 'fuchsia',
	'gainsboro', 'ghostwhite', 'gold', 'goldenrod', 'gray', 'green',
	'greenyellow', 'grey', 'honeydew', 'hotpink', 'indianred', 'indigo',
	'ivory', 'khaki', 'lavender', 'lavenderblush', 'lawngreen',
	'lemonchiffon', 'lightblue', 'lightcoral', 'lightcyan',
	'lightgoldenrodyellow', 'lightgray', 'lightgreen', 'lightgrey',
	'lightpink', 'lightsalmon', 'lightseagreen', 'lightskyblue',
	'lightslategray', 'lightslategrey', 'lightsteelblue', 'lightyellow',
	'lime', 'limegreen', 'linen', 'magenta', 'maroon',
	'mediumaquamarine', 'mediumblue', 'mediumorchid', 'mediumpurple',
	'mediumseagreen', 'mediumslateblue', 'mediumspringgreen',
	'mediumturquoise', 'mediumvioletred', 'midnightblue', 'mintcream',
	'mistyrose', 'moccasin', 'navajowhite', 'navy', 'oldlace', 'olive',
	'olivedrab', 'orange', 'orangered', 'orchid', 'palegoldenrod',
	'palegreen', 'paleturquoise', 'palevioletred', 'papayawhip',
	'peachpuff', 'peru', 'pink', 'plum', 'powderblue', 'purple',
	'rebeccapurple', 'red', 'rosybrown', 'royalblue', 'saddlebrown',
	'salmon', 'sandybrown', 'seagreen', 'seashell', 'sienna', 'silver',
	'skyblue', 'slateblue', 'slategray', 'slategrey', 'snow',
	'springgreen', 'steelblue', 'tan', 'teal', 'thistle', 'tomato',
	'turquoise', 'violet', 'wheat', 'white', 'whitesmoke', 'yellow',
	'yellowgreen'
]);

const rawAccent = (process.env.STACK_ACCENT ?? '').trim();
export const stackAccent: string =
	HEX_PATTERN.test(rawAccent) || NAMED_COLOURS.has(rawAccent.toLowerCase()) ? rawAccent : '';

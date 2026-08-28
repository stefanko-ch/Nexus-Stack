/**
 * Wall-clock time in an IANA zone -> the UTC instant it names.
 *
 * Lived in info.js and scheduled-teardown.js as byte-identical copies. A
 * third copy sat in worker/src/index.js with no caller at all; it could
 * never have shared this module, because Terraform deploys the worker as a
 * raw single file (`content = file(...)` in tofu/control-plane/main.tf) with
 * no bundler, so an import there would not resolve. It was deleted rather
 * than kept in sync.
 */

/**
 * Read an instant's local calendar and clock in a zone, as numbers.
 *
 * `Intl` is the only zone database available in Workers, so both the
 * calendar date and the UTC offset are read back out of a formatter rather
 * than computed.
 *
 * @param {Date} instant
 * @param {string} timezone - IANA zone, e.g. 'Europe/Zurich'
 * @returns {{year: number, month: number, day: number, hour: number, minute: number, second: number}}
 */
function localPartsAt(instant, timezone) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(instant);

  const f = {};
  for (const p of parts) {
    if (p.type !== 'literal') f[p.type] = p.value;
  }

  return {
    year: Number(f.year),
    month: Number(f.month),
    day: Number(f.day),
    // Some runtimes render midnight as "24" rather than "00".
    hour: Number(f.hour) % 24,
    minute: Number(f.minute),
    second: Number(f.second),
  };
}

/**
 * @param {string} timeStr - 'HH:MM' wall-clock time in the target zone
 * @param {string} timezone - IANA zone
 * @param {Date} baseDate - which local day to resolve it on (default: now)
 * @returns {Date} the UTC instant
 */
export function timeInTimezoneToUTC(timeStr, timezone, baseDate = new Date()) {
  const [hours, minutes] = timeStr.split(':').map(Number);

  // The wanted wall-clock moment, read as if it were UTC. Not the answer --
  // it is off by exactly the zone's offset, which the passes below measure.
  //
  // Built from numeric parts rather than by parsing a formatted string. The
  // earlier version went through `toLocaleDateString('en-CA')` on the
  // assumption that 'en-CA' yields YYYY-MM-DD, which is an ICU data detail
  // and not something the locale guarantees. Were that output to shift, the
  // template below would produce an unparseable string, `naive` would be
  // NaN, and every arithmetic step after it would stay NaN -- surfacing as
  // a RangeError from .toISOString() and a 500 on an endpoint that only
  // wanted to render a date. Date.UTC() takes numbers and has no such
  // failure mode.
  const base = localPartsAt(baseDate, timezone);
  const naive = Date.UTC(base.year, base.month - 1, base.day, hours, minutes, 0);

  // The offset is measured by reading back the FULL local date, not just
  // hours and minutes. Reading only hh:mm is the bug this module was split
  // out of: for a late local time the probe lands on the next day in the
  // zone (22:00Z is 00:00 in Europe/Zurich), so 22:00 against 00:00 measured
  // +1320 minutes instead of -120, and "next teardown" rendered tomorrow.
  // Folding that modulo a day fixes Zurich but stays ambiguous near +/-12h,
  // where UTC+14 and UTC+10 leave the same remainder.
  const offsetMsAt = (instant) => {
    const p = localPartsAt(instant, timezone);
    return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - instant.getTime();
  };

  // Two passes, because the offset has to be the one in force at the ANSWER,
  // not at the probe. They differ across a daylight-saving transition: on
  // 2026-03-29 in Europe/Zurich, 01:30Z is already 03:30 local, so a single
  // pass measures +2h and returns 00:30 local for a requested 01:30.
  //
  // The second pass re-measures at the candidate instant and converges. A
  // clock time that does not exist -- 02:30 on a spring-forward day -- maps
  // forward to 03:30, which is what zoneinfo and the JDK also do.
  const firstPass = naive - offsetMsAt(new Date(naive));
  return new Date(naive - offsetMsAt(new Date(firstPass)));
}

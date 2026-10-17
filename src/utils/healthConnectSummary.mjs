/* Parser for the exact text shared by ARKUS/SPARK Android Health Connect.
 * Explicit user paste only. No API calls, storage, or assertion of Garmin
 * origin: aggregate totals may come from multiple Android data producers.
 */
export function parseHealthConnectSummary(raw) {
  if (typeof raw !== 'string' || raw.length < 45 || raw.length > 10000) {
    throw new Error('Paste a SPARK Android Health Connect 7-day summary (up to 10 KB).');
  }
  const normalized = raw.replace(/\r\n/g,'\n').trim();
  const match = /^Last 7 days\n\nActivities: (\d{1,7})\nSteps: (\d{1,3}(?:,\d{3})*|\d{1,10})\nDistance: (\d{1,8}(?:\.\d{1,2})?) km\n\n(?:(?:Source apps: ([a-zA-Z0-9._,\s-]+))|(No activity-session sources found))(?:\nShowing first 100 activities\.)?\n\nHealth Connect totals may include non-Garmin sources\.$/.exec(normalized);
  if (!match) throw new Error('Unrecognized or modified Health Connect summary. Copy it directly from the SPARK Companion.');
  const activities=Number(match[1]),steps=Number(match[2].replace(/,/g,'')),distanceKm=Number(match[3]);
  if (!Number.isSafeInteger(activities)||!Number.isSafeInteger(steps)||activities>100000||steps>1000000000||distanceKm>1000000) {
    throw new Error('Summary contains unsupported values.');
  }
  const sources=(match[4]||'').trim().split(/,\s*/).filter(Boolean).slice(0,30);
  return Object.freeze({
    period:'Last 7 days',
    activities,steps,distanceKm,
    sources,
    origin:'Android Health Connect (user-shared)',
    directGarminConnection:false,
    verifiedGarminOrigin:false,
    note:'Aggregates may include multiple sources; package names apply to exercise sessions only.',
  });
}

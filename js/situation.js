// Calculs purs de l'encart « Situation actuelle » : aucun DOM, aucun fetch.
// Script classique (fonctions globales), chargé avant le <script> inline d'index.html.

const MS_PER_DAY = 86400000;

function computePercentiles(values, percentiles) {
  if (!values || values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const out = {};
  for (const p of percentiles) {
    const idx = (p / 100) * (sorted.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.ceil(idx);
    out[p] = lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }
  return out;
}

function isUsableValue(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function parseIsoDay(dateIso) {
  const [year, month, day] = dateIso.split('-').map(Number);
  return { year, month, day };
}

function epochDay(year, month, day) {
  return Math.round(Date.UTC(year, month - 1, day) / MS_PER_DAY);
}

function isLeapYear(year) {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function latestValidRecord(records) {
  if (!records) return null;
  let latest = null;
  for (const record of records) {
    if (!record || !record.date || !isUsableValue(record.value)) continue;
    if (latest === null || record.date > latest.date) latest = record;
  }
  if (latest === null) return null;
  return { date: latest.date, value: latest.value, quality: latest.quality ?? null };
}

// Le 29 février est ramené au 28 février dans les années non bissextiles.
function anchorEpochDay(year, month, day) {
  const anchorDay = month === 2 && day === 29 && !isLeapYear(year) ? 28 : day;
  return epochDay(year, month, anchorDay);
}

function sameSeasonValues(records, refDateIso, halfWindowDays) {
  if (!records || !refDateIso) return [];
  const ref = parseIsoDay(refDateIso);
  const values = [];
  for (const record of records) {
    if (!record || !record.date || !isUsableValue(record.value)) continue;
    const { year, month, day } = parseIsoDay(record.date);
    const recordDay = epochDay(year, month, day);
    // Ancres de l'année précédente, courante et suivante : couvre le passage déc./janv.
    const anchorYear = [-1, 0, 1]
      .map(shift => year + shift)
      .find(candidate => Math.abs(recordDay - anchorEpochDay(candidate, ref.month, ref.day)) <= halfWindowDays);
    // Exclut l'occurrence courante de la saison, pas l'année civile de la mesure.
    const isInWindow = anchorYear !== undefined && anchorYear !== ref.year;
    if (isInWindow) values.push(record.value);
  }
  return values;
}

function percentileRank(values, value) {
  if (!values || values.length === 0 || !isUsableValue(value)) return null;
  let below = 0;
  let equal = 0;
  for (const v of values) {
    if (v < value) below++;
    else if (v === value) equal++;
  }
  return ((below + equal / 2) / values.length) * 100;
}

function classifyPercentile(rank) {
  if (rank === null || rank === undefined || Number.isNaN(rank)) return null;
  if (rank < 10) return 'tres_bas';
  if (rank < 25) return 'bas';
  if (rank <= 75) return 'normal';
  if (rank <= 90) return 'haut';
  return 'tres_haut';
}

function annualMinMovingAverage(records, windowDays, minDaysPerYear) {
  if (!records) return [];
  const valueByDay = new Map();
  const countByYear = new Map();
  for (const record of records) {
    if (!record || !record.date || !isUsableValue(record.value)) continue;
    const { year, month, day } = parseIsoDay(record.date);
    valueByDay.set(epochDay(year, month, day), record.value);
    countByYear.set(year, (countByYear.get(year) || 0) + 1);
  }
  const minByYear = new Map();
  for (const endDay of valueByDay.keys()) {
    const average = windowAverage(valueByDay, endDay, windowDays);
    if (average === null) continue;
    const year = new Date(endDay * MS_PER_DAY).getUTCFullYear();
    if (!minByYear.has(year) || average < minByYear.get(year)) minByYear.set(year, average);
  }
  return [...minByYear.entries()]
    .filter(([year]) => countByYear.get(year) >= minDaysPerYear)
    .map(([year, value]) => ({ year, value }))
    .sort((a, b) => a.year - b.year);
}

// null dès qu'un jour de la fenêtre manque : un trou casse la fenêtre.
function windowAverage(valueByDay, endDay, windowDays) {
  let sum = 0;
  for (let offset = 0; offset < windowDays; offset++) {
    const value = valueByDay.get(endDay - offset);
    if (value === undefined) return null;
    sum += value;
  }
  return sum / windowDays;
}

const MIN_YEARS_FOR_RETURN_PERIOD = 10;

function dryReturnPeriodLowFlow(annualMins, returnPeriodYears) {
  if (!annualMins || annualMins.length < MIN_YEARS_FOR_RETURN_PERIOD) return null;
  const probabilityPercent = 100 / returnPeriodYears;
  const quantiles = computePercentiles(annualMins.map(entry => entry.value), [probabilityPercent]);
  return quantiles ? quantiles[probabilityPercent] : null;
}

function dataAgeDays(latestDateIso, todayIso) {
  const latest = parseIsoDay(latestDateIso);
  const today = parseIsoDay(todayIso);
  const age = epochDay(today.year, today.month, today.day) - epochDay(latest.year, latest.month, latest.day);
  return Math.max(0, age);
}

const VCN3_WINDOW_DAYS = 3;
const VCN3_MIN_DAYS_PER_YEAR = 300;
const VCN3_RETURN_PERIOD_YEARS = 5;

function computeSituation(records, { todayIso, halfWindowDays = 7, withLowFlow } = {}) {
  const latest = latestValidRecord(records);
  if (latest === null) return null;
  const seasonValues = sameSeasonValues(records, latest.date, halfWindowDays);
  const rank = percentileRank(seasonValues, latest.value);
  return {
    latest,
    rank,
    category: classifyPercentile(rank),
    sampleSize: seasonValues.length,
    lowFlowDry5: withLowFlow ? computeLowFlowDry5(records) : null,
    ageDays: dataAgeDays(latest.date, todayIso),
    isProvisional: latest.quality !== 'Bonne',
  };
}

function computeLowFlowDry5(records) {
  const annualMins = annualMinMovingAverage(records, VCN3_WINDOW_DAYS, VCN3_MIN_DAYS_PER_YEAR);
  return dryReturnPeriodLowFlow(annualMins, VCN3_RETURN_PERIOD_YEARS);
}

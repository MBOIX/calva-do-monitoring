// Client VigiEau : niveau de restriction sécheresse d'une zone. Aucun DOM.
// API non contractuelle : tout écart de schéma dégrade en { status: 'unavailable' }.

const VIGIEAU_API_BASE = 'https://api.vigieau.gouv.fr/api/zones/departement/';
const VIGIEAU_ZONE_CODE_PATTERN = /^\d+_([0-9AB]{2,3})_\d{4}$/;

const VIGIEAU_LEVELS = {
  vigilance: { label: 'Vigilance', severity: 1 },
  alerte: { label: 'Alerte', severity: 2 },
  alerte_renforcee: { label: 'Alerte renforcée', severity: 3 },
  crise: { label: 'Crise', severity: 4 },
};

// Zones par département, pour la session ; on ne mémorise que les succès.
const vigieauZonesByDepartment = new Map();

function clearVigieauCache() {
  vigieauZonesByDepartment.clear();
}

function zoneDepartment(zoneCode) {
  if (typeof zoneCode !== 'string') return null;
  const match = VIGIEAU_ZONE_CODE_PATTERN.exec(zoneCode);
  return match ? match[1] : null;
}

function pickSurfaceZone(zones, zoneCode) {
  if (!Array.isArray(zones)) return null;
  return zones.find((zone) => zone && zone.type === 'SUP' && zone.code === zoneCode) || null;
}

function safeHttpsUrl(url) {
  return typeof url === 'string' && url.startsWith('https://') ? url : null;
}

function rejectAfter(timeoutMs, controller) {
  let timerId;
  const promise = new Promise((_, reject) => {
    timerId = setTimeout(() => {
      controller.abort();
      reject(new Error('timeout'));
    }, timeoutMs);
  });
  return { promise, cancel: () => clearTimeout(timerId) };
}

async function fetchDepartmentZones(department, fetchFn, timeoutMs) {
  if (vigieauZonesByDepartment.has(department)) return vigieauZonesByDepartment.get(department);

  const controller = new AbortController();
  const timeout = rejectAfter(timeoutMs, controller);
  try {
    const request = (async () => {
      const response = await fetchFn(VIGIEAU_API_BASE + encodeURIComponent(department), {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (!response || !response.ok) throw new Error('HTTP ' + (response ? response.status : 'inconnu'));
      const zones = await response.json();
      if (!Array.isArray(zones)) throw new Error('réponse inattendue');
      return zones;
    })();
    request.catch(() => {}); // évite un rejet non géré si le timeout gagne la course
    const zones = await Promise.race([request, timeout.promise]);
    vigieauZonesByDepartment.set(department, zones);
    return zones;
  } finally {
    timeout.cancel();
  }
}

function describeRestriction(zone) {
  const level = VIGIEAU_LEVELS[zone.niveauGravite];
  if (!level) return null;
  const decree = zone.arrete || {};
  return {
    status: 'restricted',
    level: zone.niveauGravite,
    label: level.label,
    severity: level.severity,
    zoneName: typeof zone.nom === 'string' ? zone.nom : null,
    validUntil: typeof decree.dateFinValidite === 'string' ? decree.dateFinValidite : null,
    decreeUrl: safeHttpsUrl(decree.cheminFichier),
  };
}

async function fetchRestriction(zoneCode, { fetchFn = fetch, timeoutMs = 8000 } = {}) {
  try {
    const department = zoneDepartment(zoneCode);
    if (!department) return { status: 'unavailable', reason: 'code de zone invalide' };

    const zones = await fetchDepartmentZones(department, fetchFn, timeoutMs);
    const zone = pickSurfaceZone(zones, zoneCode);
    if (!zone) return { status: 'none' };

    const restriction = describeRestriction(zone);
    return restriction || { status: 'unavailable', reason: 'niveau de gravité inconnu' };
  } catch (error) {
    return { status: 'unavailable', reason: error && error.message ? error.message : String(error) };
  }
}

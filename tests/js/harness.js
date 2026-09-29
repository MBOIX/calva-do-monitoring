// Mini-harnais de test sans dépendance. Les tests s'exécutent au chargement de la page ;
// le bilan est écrit dans <pre id="test-results" data-status="running|pass|fail">.
const registeredTests = [];

function test(name, fn) {
  registeredTests.push({ name, fn });
}

function describeValue(value) {
  try {
    return JSON.stringify(value);
  } catch (error) {
    return String(value);
  }
}

function assertEqual(actual, expected, message) {
  if (describeValue(actual) !== describeValue(expected)) {
    throw new Error(`${message || 'assertEqual'} : attendu ${describeValue(expected)}, obtenu ${describeValue(actual)}`);
  }
}

function assertClose(actual, expected, tolerance = 1e-9, message) {
  if (typeof actual !== 'number' || Math.abs(actual - expected) > tolerance) {
    throw new Error(`${message || 'assertClose'} : attendu ${expected} ± ${tolerance}, obtenu ${describeValue(actual)}`);
  }
}

function assertTrue(condition, message) {
  if (!condition) throw new Error(message || 'assertTrue : condition fausse');
}

async function runRegisteredTests() {
  const output = document.getElementById('test-results');
  output.dataset.status = 'running';
  const failures = [];
  for (const { name, fn } of registeredTests) {
    try {
      await fn();
    } catch (error) {
      failures.push(`ÉCHEC ${name} : ${error && error.message ? error.message : error}`);
    }
  }
  const passed = registeredTests.length - failures.length;
  const summary = `${passed}/${registeredTests.length} tests réussis`;
  output.textContent = [summary, ...failures].join('\n');
  output.dataset.status = failures.length === 0 && registeredTests.length > 0 ? 'pass' : 'fail';
}

window.addEventListener('load', () => {
  runRegisteredTests().catch(error => {
    const output = document.getElementById('test-results');
    output.textContent = `Erreur du harnais : ${error}`;
    output.dataset.status = 'fail';
  });
});

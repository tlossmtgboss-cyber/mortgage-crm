#!/usr/bin/env bash
# 03-auth/frontend/remove-localstorage-jwt.sh
#
# Automated codemod: finds and removes every localStorage-based auth pattern
# in the frontend. Writes a report, applies edits with prompts, runs tests.
#
# Patterns replaced:
#   localStorage.getItem('token')       -> REMOVED (use authFetch — cookies auto-attach)
#   localStorage.setItem('token', ...)  -> REMOVED
#   localStorage.removeItem('token')    -> REMOVED
#   fetch(..., { headers: { Authorization: `Bearer ${token}` } })
#                                        -> authFetch(...)
#
# Run from repo root. Review the diff before committing.

set -euo pipefail

FRONTEND_DIR="${FRONTEND_DIR:-frontend/src}"

if [ ! -d "${FRONTEND_DIR}" ]; then
  echo "!! ${FRONTEND_DIR} not found. Set FRONTEND_DIR env var."
  exit 1
fi

REPORT="/tmp/perennia-localstorage-jwt-report.txt"
: > "${REPORT}"

echo "==> Step 1: Inventory of localStorage auth usage"
grep -rEn --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  "localStorage\.(setItem|getItem|removeItem)\(['\"](token|jwt|auth_token|access_token|refresh_token)" \
  "${FRONTEND_DIR}" | tee -a "${REPORT}" || true

echo ""
echo "==> Step 2: Inventory of Bearer token fetch patterns"
grep -rEn --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  "Authorization.*Bearer" \
  "${FRONTEND_DIR}" | tee -a "${REPORT}" || true

echo ""
echo "==> Full report written to: ${REPORT}"
echo ""
echo "==> Step 3: Apply codemod? [y/N]"
read -r confirm
if [ "${confirm}" != "y" ]; then
  echo "Aborted. No changes made."
  exit 0
fi

# Use a jscodeshift codemod for the structured edits
cat > /tmp/perennia-auth-codemod.js <<'EOF'
/**
 * jscodeshift transform: remove localStorage auth + replace fetch Bearer with authFetch
 */
module.exports = function transformer(file, api) {
  const j = api.jscodeshift;
  const root = j(file.source);
  let modified = false;

  // Remove localStorage.{set,get,remove}Item('token' | 'jwt' | ...)
  const AUTH_KEYS = ['token', 'jwt', 'auth_token', 'access_token', 'refresh_token', 'authToken', 'accessToken', 'refreshToken'];

  root
    .find(j.CallExpression, {
      callee: {
        object: { name: 'localStorage' },
        property: { name: (n) => ['getItem', 'setItem', 'removeItem'].includes(n) },
      },
    })
    .filter((path) => {
      const first = path.node.arguments[0];
      return first && first.type === 'Literal' && AUTH_KEYS.includes(first.value);
    })
    .forEach((path) => {
      // Remove containing statement if standalone; otherwise replace with undefined
      const parent = path.parent.node;
      if (parent.type === 'ExpressionStatement') {
        j(path.parent).remove();
      } else {
        j(path).replaceWith(j.identifier('undefined'));
      }
      modified = true;
    });

  // Replace fetch(url, { headers: { Authorization: `Bearer ${...}` }, ... })
  //   with authFetch(url, { ... })
  root
    .find(j.CallExpression, { callee: { name: 'fetch' } })
    .forEach((path) => {
      const args = path.node.arguments;
      if (args.length < 2 || args[1].type !== 'ObjectExpression') return;

      const opts = args[1];
      const headersProp = opts.properties.find(
        (p) => p.key && (p.key.name === 'headers' || p.key.value === 'headers'),
      );
      if (!headersProp || headersProp.value.type !== 'ObjectExpression') return;

      const authProp = headersProp.value.properties.find((p) => {
        const k = p.key;
        return k && ((k.name === 'Authorization') || (k.value === 'Authorization'));
      });
      if (!authProp) return;

      // Remove Authorization header
      headersProp.value.properties = headersProp.value.properties.filter(
        (p) => p !== authProp,
      );
      // If headers object is now empty, remove it
      if (headersProp.value.properties.length === 0) {
        opts.properties = opts.properties.filter((p) => p !== headersProp);
      }

      // Swap fetch -> authFetch
      path.node.callee = j.identifier('authFetch');
      modified = true;
    });

  if (!modified) return null;

  // Ensure authFetch is imported
  const hasImport = root.find(j.ImportDeclaration, { source: { value: (v) => v && v.includes('authClient') } }).size() > 0;
  if (!hasImport) {
    root.get().node.program.body.unshift(
      j.importDeclaration(
        [j.importSpecifier(j.identifier('authFetch'))],
        j.literal('@/lib/auth/authClient'),
      ),
    );
  }

  return root.toSource({ quote: 'single' });
};
EOF

if ! command -v npx &>/dev/null; then
  echo "!! npx not found. Install Node.js."
  exit 1
fi

echo "==> Running codemod against ${FRONTEND_DIR}"
npx jscodeshift \
  -t /tmp/perennia-auth-codemod.js \
  --extensions=ts,tsx,js,jsx \
  --parser=tsx \
  "${FRONTEND_DIR}"

echo ""
echo "==> Step 4: Running frontend tests"
cd "$(dirname "${FRONTEND_DIR}")/.."
npm test -- --run || {
  echo "!! Tests failed. Review codemod output, fix, and re-run tests before committing."
  exit 1
}

echo ""
echo "==> Codemod complete. Review the diff:"
echo "    git diff ${FRONTEND_DIR}"

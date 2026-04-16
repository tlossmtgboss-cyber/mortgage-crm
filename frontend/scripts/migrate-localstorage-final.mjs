#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────
// scripts/migrate-localstorage-final.mjs
//
// Migrates remaining localStorage auth-token reads/writes to
// use the tokenStore API (src/utils/tokenStore.js).
//
// Keys migrated:
//   localStorage.getItem('token')         → getToken()
//   localStorage.getItem('refresh_token') → getRefreshToken()
//   localStorage.getItem('user')          → getUserData()
//   localStorage.setItem('token', X)      → /* TODO: await */ setTokens({ access_token: X })
//   localStorage.setItem('refresh_token', X) → /* TODO: await */ setTokens({ refresh_token: X })
//   localStorage.setItem('user', X)       → /* TODO: await */ setTokens({ user_data: X })
//   localStorage.removeItem('token')      → /* TODO: await */ clearTokens()
//   localStorage.removeItem('refresh_token') → /* TODO: await */ clearTokens()
//   localStorage.removeItem('user')       → /* TODO: await */ clearTokens()
//
// Run: cd frontend && node scripts/migrate-localstorage-final.mjs
// Then: git diff src/ — review before committing
// ─────────────────────────────────────────────────────────────

import { readFileSync, writeFileSync, readdirSync, statSync } from 'fs';
import { join, extname, relative, dirname } from 'path';

const SRC_DIR = './src';
const EXTENSIONS = ['.jsx', '.tsx', '.js', '.ts'];
const SKIP_DIRS = ['node_modules', '.git', 'dist', 'build', 'public', '__tests__', 'test'];

// ── Files already handled manually or that ARE the tokenStore ─
const SKIP_FILES = new Set([
  'src/api.js',
  'src/utils/tokenStore.js',
  'src/utils/storage.js',
  'src/services/sessionManager.js',
  'src/services/pushNotificationService.js',
  'src/hooks/usePushNotifications.js',
  'src/services/certificatePinning.js',
  'src/services/mobileAnalytics.js',
  'src/hooks/useMobileAudioCapture.js',
  'src/services/performanceMonitor.js',
  'src/services/remoteConfig.js',
  'src/services/deviceIntegrity.js',
  'src/contexts/PermissionContext.js',
  'src/contexts/BrandingContext.js',
  'src/contexts/ModuleContext.js',
  'src/hooks/useQueries.js',
  'src/hooks/usePagePermissions.js',
  'src/hooks/useDialerSession.js',
  // Mobile-path files (handled by separate agent)
  'src/screens/AriaScreen.tsx',
  'src/screens/CalendarScreen.tsx',
  'src/screens/TasksScreen.tsx',
  'src/screens/AppointmentDetailScreen.tsx',
  'src/screens/CallIntelligenceScreen.tsx',
  'src/screens/LoginScreen.tsx',
  'src/screens/ProfileScreen.tsx',
  'src/screens/BookAppointmentScreen.tsx',
]);

// ── Replacement patterns ──────────────────────────────────────
// Order matters: getItem before setItem/removeItem to avoid partial matches
const PATTERNS = [
  // ── getItem — synchronous, direct replacement ──────────────
  {
    regex: /localStorage\.getItem\s*\(\s*['"]token['"]\s*\)/g,
    replacement: 'getToken()',
    addImport: 'getToken',
  },
  {
    regex: /localStorage\.getItem\s*\(\s*['"]refresh_token['"]\s*\)/g,
    replacement: 'getRefreshToken()',
    addImport: 'getRefreshToken',
  },
  {
    regex: /localStorage\.getItem\s*\(\s*['"]user['"]\s*\)/g,
    replacement: 'getUserData()',
    addImport: 'getUserData',
  },
  // ── setItem — async, mark with TODO ────────────────────────
  {
    regex: /localStorage\.setItem\s*\(\s*['"]token['"],\s*(.+?)\s*\)/g,
    replacement: '/* TODO: await */ setTokens({ access_token: $1 })',
    addImport: 'setTokens',
  },
  {
    regex: /localStorage\.setItem\s*\(\s*['"]refresh_token['"],\s*(.+?)\s*\)/g,
    replacement: '/* TODO: await */ setTokens({ refresh_token: $1 })',
    addImport: 'setTokens',
  },
  {
    regex: /localStorage\.setItem\s*\(\s*['"]user['"],\s*(.+?)\s*\)/g,
    replacement: '/* TODO: await */ setTokens({ user_data: $1 })',
    addImport: 'setTokens',
  },
  // ── removeItem — async, mark with TODO ─────────────────────
  {
    regex: /localStorage\.removeItem\s*\(\s*['"]token['"]\s*\)/g,
    replacement: '/* TODO: await */ clearTokens()',
    addImport: 'clearTokens',
  },
  {
    regex: /localStorage\.removeItem\s*\(\s*['"]refresh_token['"]\s*\)/g,
    replacement: '/* TODO: await */ clearTokens()',
    addImport: 'clearTokens',
  },
  {
    regex: /localStorage\.removeItem\s*\(\s*['"]user['"]\s*\)/g,
    replacement: '/* TODO: await */ clearTokens()',
    addImport: 'clearTokens',
  },
];

function getRelativeImportPath(filePath) {
  // Calculate relative path from file to tokenStore
  const fileDir = dirname(filePath);
  const relToSrc = relative('src', fileDir);
  const levels = relToSrc ? relToSrc.split('/').length : 0;
  const prefix = levels > 0 ? '../'.repeat(levels) : './';
  return `${prefix}utils/tokenStore`;
}

function addTokenStoreImport(content, filePath, importsNeeded) {
  if (importsNeeded.size === 0) return content;

  const importPath = getRelativeImportPath(filePath);
  const importNames = Array.from(importsNeeded).sort().join(', ');
  const importStatement = `import { ${importNames} } from '${importPath}';`;

  // Don't add if already imported — merge the names
  if (content.includes('from') && content.includes('tokenStore')) {
    return content.replace(
      /import\s*\{([^}]+)\}\s*from\s*['"][^'"]*tokenStore['"]/,
      (match, existing) => {
        const existingNames = existing.split(',').map(s => s.trim());
        const allNames = [...new Set([...existingNames, ...importsNeeded])].sort();
        return `import { ${allNames.join(', ')} } from '${importPath}'`;
      }
    );
  }

  // Add after the last import statement
  const lines = content.split('\n');
  let lastImportLine = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*import\s/.test(lines[i])) {
      // Handle multi-line imports — find the end
      let j = i;
      while (j < lines.length && !lines[j].includes(';') && !lines[j].match(/['"][^'"]*['"]\s*$/)) {
        j++;
      }
      lastImportLine = j;
    }
  }

  if (lastImportLine >= 0) {
    lines.splice(lastImportLine + 1, 0, importStatement);
    return lines.join('\n');
  }

  // No imports found — add at top
  return importStatement + '\n\n' + content;
}

function processFile(filePath) {
  const relPath = relative('.', filePath);
  if (SKIP_FILES.has(relPath)) return { skipped: true };

  let content = readFileSync(filePath, 'utf-8');
  const original = content;
  const importsNeeded = new Set();
  let hitCount = 0;

  for (const { regex, replacement, addImport } of PATTERNS) {
    // Reset regex lastIndex
    regex.lastIndex = 0;
    const matches = content.match(regex);
    if (matches) {
      hitCount += matches.length;
      regex.lastIndex = 0;
      content = content.replace(regex, replacement);
      if (addImport) importsNeeded.add(addImport);
    }
  }

  if (content === original) return { changed: false, hits: 0 };

  // Add tokenStore import
  content = addTokenStoreImport(content, filePath, importsNeeded);

  writeFileSync(filePath, content, 'utf-8');
  return { changed: true, hits: hitCount, imports: Array.from(importsNeeded) };
}

function walkDir(dir) {
  const files = [];
  try {
    for (const entry of readdirSync(dir)) {
      const fullPath = join(dir, entry);
      if (SKIP_DIRS.includes(entry)) continue;
      const stat = statSync(fullPath);
      if (stat.isDirectory()) {
        files.push(...walkDir(fullPath));
      } else if (EXTENSIONS.includes(extname(entry))) {
        files.push(fullPath);
      }
    }
  } catch {}
  return files;
}

// ── Run ───────────────────────────────────────────────────────
const files = walkDir(SRC_DIR);
let migrated = 0;
let totalHits = 0;
const todoFiles = [];

console.log(`\nScanning ${files.length} files...\n`);

for (const file of files) {
  const result = processFile(file);
  if (result.skipped) {
    console.log(`  SKIP  ${relative('.', file)}`);
  } else if (result.changed) {
    migrated++;
    totalHits += result.hits;
    console.log(`  OK    ${relative('.', file).padEnd(65)} (${result.hits} hits)`);

    // Track files with TODO markers that need manual async wrapping
    if (result.imports?.includes('setTokens') || result.imports?.includes('clearTokens')) {
      todoFiles.push(file);
    }
  }
}

console.log(`\n${'─'.repeat(70)}`);
console.log(`Migrated: ${migrated} files, ${totalHits} total hits`);
console.log(`\nReview diff:  git diff src/`);
console.log(`Find TODOs:   grep -rn "TODO: await" src/\n`);

if (todoFiles.length > 0) {
  console.log(`WARNING: ${todoFiles.length} file(s) have setTokens/clearTokens calls`);
  console.log(`   marked with /* TODO: await */ — these need async wrappers:\n`);
  todoFiles.forEach(f => console.log(`   ${relative('.', f)}`));
  console.log(`\n   For each TODO, ensure the enclosing function is async,`);
  console.log(`   then remove the /* TODO: await */ comment and add await.\n`);
}

// ── Verification: count remaining hits after migration ────────
console.log('Verifying...\n');
const remainingToken = [];
const remainingUser = [];
const remainingRefresh = [];
for (const file of walkDir(SRC_DIR)) {
  const relFile = relative('.', file);
  if (SKIP_FILES.has(relFile)) continue;
  const content = readFileSync(file, 'utf-8');

  const tokenMatches = (content.match(/localStorage\.(getItem|setItem|removeItem)\s*\(\s*['"]token['"]/g) || []);
  if (tokenMatches.length > 0) {
    remainingToken.push({ file: relFile, count: tokenMatches.length });
  }

  const userMatches = (content.match(/localStorage\.(getItem|setItem|removeItem)\s*\(\s*['"]user['"]/g) || []);
  if (userMatches.length > 0) {
    remainingUser.push({ file: relFile, count: userMatches.length });
  }

  const refreshMatches = (content.match(/localStorage\.(getItem|setItem|removeItem)\s*\(\s*['"]refresh_token['"]/g) || []);
  if (refreshMatches.length > 0) {
    remainingRefresh.push({ file: relFile, count: refreshMatches.length });
  }
}

const totalRemaining = remainingToken.length + remainingUser.length + remainingRefresh.length;

if (totalRemaining === 0) {
  console.log('PASS: Zero remaining localStorage auth reads/writes (outside skipped files).\n');
} else {
  console.log(`WARNING: ${totalRemaining} file(s) still have localStorage auth calls:\n`);
  for (const { file, count } of remainingToken) {
    console.log(`   [token]          ${file} (${count})`);
  }
  for (const { file, count } of remainingUser) {
    console.log(`   [user]           ${file} (${count})`);
  }
  for (const { file, count } of remainingRefresh) {
    console.log(`   [refresh_token]  ${file} (${count})`);
  }
  console.log('\n   These likely need manual inspection (in test files, skipped files, etc.)\n');
}

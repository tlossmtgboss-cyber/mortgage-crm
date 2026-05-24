import React, { useState, Suspense, lazy } from 'react';

const builders = [
  { key: 'v1', label: 'Timeline', desc: 'Vertical timeline with expandable cards and drag-to-reorder' },
  { key: 'v2', label: 'Kanban', desc: 'Swim-lane board with drag cards between time columns' },
  { key: 'v3', label: 'Rules Engine', desc: 'Natural language if-then rules with inline dropdowns' },
  { key: 'v4', label: 'Flow Chart', desc: 'Node-based visual diagram with draggable connections' },
  { key: 'v5', label: 'Spreadsheet', desc: 'Excel-style grid with inline editing and bulk actions' },
  { key: 'v6', label: 'AI Copilot', desc: 'Chat-driven builder with live preview panel' },
];

const components = {
  v1: lazy(() => import('./WorkflowBuilderV1')),
  v2: lazy(() => import('./WorkflowBuilderV2')),
  v3: lazy(() => import('./WorkflowBuilderV3')),
  v4: lazy(() => import('./WorkflowBuilderV4')),
  v5: lazy(() => import('./WorkflowBuilderV5')),
  v6: lazy(() => import('./WorkflowBuilderV6')),
};

const T = {
  bg: '#FAF7F1',
  card: '#FFFFFF',
  primary: '#1F3D2E',
  accent: '#B8924A',
  border: '#ECE6D8',
  text: '#1A1F1B',
  muted: '#8B8A7E',
};

export default function WorkflowBuilderShowcase() {
  const [active, setActive] = useState('v1');
  const ActiveComponent = components[active];
  const activeMeta = builders.find(b => b.key === active);

  return (
    <div style={{ background: T.bg, minHeight: '100vh' }}>
      <div style={{
        background: T.card,
        borderBottom: `1px solid ${T.border}`,
        padding: '24px 32px 0',
        position: 'sticky',
        top: 0,
        zIndex: 200,
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
            <h1 style={{
              fontFamily: "'Fraunces', serif",
              fontSize: 24,
              fontWeight: 700,
              color: T.primary,
              margin: 0,
            }}>
              Workflow Builder Prototypes
            </h1>
            <span style={{
              fontSize: 12,
              fontWeight: 600,
              color: T.accent,
              background: `${T.accent}18`,
              padding: '4px 12px',
              borderRadius: 20,
              letterSpacing: 0.5,
            }}>
              6 VARIANTS
            </span>
          </div>
          <p style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 14,
            color: T.muted,
            margin: '0 0 20px',
          }}>
            Each tab is a fully interactive prototype — click, drag, edit, and test to find the best UX.
          </p>

          <div style={{
            display: 'flex',
            gap: 4,
            overflowX: 'auto',
            paddingBottom: 0,
          }}>
            {builders.map((b, i) => (
              <button
                key={b.key}
                onClick={() => setActive(b.key)}
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: 13,
                  fontWeight: active === b.key ? 600 : 400,
                  color: active === b.key ? T.primary : T.muted,
                  background: active === b.key ? T.bg : 'transparent',
                  border: `1px solid ${active === b.key ? T.border : 'transparent'}`,
                  borderBottom: active === b.key ? `2px solid ${T.primary}` : '2px solid transparent',
                  borderRadius: '8px 8px 0 0',
                  padding: '10px 16px',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{
                  display: 'inline-block',
                  width: 20,
                  height: 20,
                  lineHeight: '20px',
                  textAlign: 'center',
                  borderRadius: '50%',
                  background: active === b.key ? T.primary : T.border,
                  color: active === b.key ? '#fff' : T.muted,
                  fontSize: 11,
                  fontWeight: 700,
                  marginRight: 8,
                }}>
                  {i + 1}
                </span>
                {b.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div style={{
        background: `${T.accent}10`,
        borderBottom: `1px solid ${T.border}`,
        padding: '10px 32px',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 13,
            fontWeight: 600,
            color: T.primary,
          }}>
            V{builders.findIndex(b => b.key === active) + 1}: {activeMeta.label}
          </span>
          <span style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 13,
            color: T.muted,
          }}>
            — {activeMeta.desc}
          </span>
        </div>
      </div>

      <div style={{ position: 'relative' }}>
        <Suspense fallback={
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: 400,
            fontFamily: "'Inter', sans-serif",
            color: T.muted,
          }}>
            Loading builder...
          </div>
        }>
          <ActiveComponent />
        </Suspense>
      </div>
    </div>
  );
}

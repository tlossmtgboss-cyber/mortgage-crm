# Styling Guide

## New Components
All new components MUST use CSS Modules:
- Name: `ComponentName.module.css`
- Import: `import styles from './ComponentName.module.css'`
- Usage: `<div className={styles.container}>`

## Design Tokens
Import from `./design-tokens.css` (loaded globally).
Use `var(--pf-primary)` etc. in your CSS Modules.

## Legacy Variables
Existing components use `var(--color-primary)`, `var(--space-md)`, etc. from
`index.css`. These remain valid. New `--pf-*` tokens are additive and preferred
for new CSS Modules because the prefix makes them self-documenting.

## Migration
Existing `.css` files will be migrated to `.module.css` when their component
is touched. No bulk rename needed.

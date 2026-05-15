/**
 * Microsite Theme Registry
 *
 * This module manages the registry of available microsite themes and
 * provides utilities for theme rendering and configuration.
 */

// Import theme components (lazy loaded for performance)
const themeComponents = {
  BoldImpact: () => import('../../pages/microsites/themes/BoldImpact'),
  ProfessionalClean: () => import('../../pages/microsites/themes/ProfessionalClean'),
  ModernGradient: () => import('../../pages/microsites/themes/ModernGradient'),
  MinimalFocus: () => import('../../pages/microsites/themes/MinimalFocus'),
  // Default fallback to legacy LOMicrosite
  LOMicrosite: () => import('../../pages/microsites/LOMicrosite'),
};

/**
 * Theme metadata for UI display
 */
export const themeMetadata = {
  'bold-impact': {
    slug: 'bold-impact',
    name: 'Bold Impact',
    description: 'A bold, modern theme with strong call-to-actions and lead capture focus.',
    category: 'bold',
    componentName: 'BoldImpact',
    features: ['hero_image', 'contact_form', 'rate_calculator', 'testimonials', 'about_section'],
    thumbnailUrl: '/images/themes/bold-impact-thumb.png',
    previewImages: [
      '/images/themes/bold-impact-1.png',
      '/images/themes/bold-impact-2.png',
    ],
    supportsCustomColors: true,
    layoutOptions: {
      heroStyle: ['image', 'gradient', 'video'],
      headerStyle: ['centered', 'left'],
      ctaStyle: ['button', 'form'],
    },
    defaultConfig: {
      primaryColor: '#dc2626',
      secondaryColor: '#1e3a5f',
      heroStyle: 'image',
      headerStyle: 'centered',
      showTestimonials: true,
      showRateCalculator: true,
    },
  },
  'professional-clean': {
    slug: 'professional-clean',
    name: 'Professional Clean',
    description: 'A clean, professional theme perfect for established loan officers.',
    category: 'professional',
    componentName: 'ProfessionalClean',
    features: ['hero_image', 'contact_form', 'credentials', 'about_section'],
    thumbnailUrl: '/images/themes/professional-clean-thumb.png',
    supportsCustomColors: true,
    layoutOptions: {
      heroStyle: ['image', 'solid'],
      headerStyle: ['left', 'centered'],
    },
    defaultConfig: {
      primaryColor: '#2563eb',
      secondaryColor: '#1e40af',
      heroStyle: 'solid',
      headerStyle: 'left',
    },
  },
  'modern-gradient': {
    slug: 'modern-gradient',
    name: 'Modern Gradient',
    description: 'A contemporary theme with gradient backgrounds and smooth animations.',
    category: 'modern',
    componentName: 'ModernGradient',
    features: ['hero_gradient', 'contact_form', 'testimonials', 'about_section'],
    thumbnailUrl: '/images/themes/modern-gradient-thumb.png',
    supportsCustomColors: true,
    layoutOptions: {
      gradientDirection: ['diagonal', 'horizontal', 'vertical'],
      animationStyle: ['subtle', 'dynamic', 'none'],
    },
    defaultConfig: {
      primaryColor: '#B8924A',
      secondaryColor: '#ec4899',
      gradientDirection: 'diagonal',
      animationStyle: 'subtle',
    },
  },
  'minimal-focus': {
    slug: 'minimal-focus',
    name: 'Minimal Focus',
    description: 'A minimalist theme that puts the focus on your message and lead capture.',
    category: 'minimal',
    componentName: 'MinimalFocus',
    features: ['contact_form', 'about_section'],
    thumbnailUrl: '/images/themes/minimal-focus-thumb.png',
    supportsCustomColors: true,
    layoutOptions: {
      layout: ['centered', 'split'],
    },
    defaultConfig: {
      primaryColor: '#18181b',
      secondaryColor: '#71717a',
      layout: 'centered',
    },
  },
};

/**
 * Get a theme component by its component name
 * @param {string} componentName - The name of the component to load
 * @returns {Promise} - Promise that resolves to the component module
 */
export const getThemeComponent = async (componentName) => {
  const loader = themeComponents[componentName];
  if (!loader) {
    console.warn(`Theme component "${componentName}" not found, falling back to LOMicrosite`);
    return themeComponents.LOMicrosite();
  }
  return loader();
};

/**
 * Get theme metadata by slug
 * @param {string} slug - The theme slug
 * @returns {Object|null} - Theme metadata or null if not found
 */
export const getThemeMetadata = (slug) => {
  return themeMetadata[slug] || null;
};

/**
 * Get all available themes
 * @returns {Array} - Array of theme metadata objects
 */
export const getAllThemes = () => {
  return Object.values(themeMetadata);
};

/**
 * Get themes by category
 * @param {string} category - The category to filter by
 * @returns {Array} - Array of theme metadata objects
 */
export const getThemesByCategory = (category) => {
  return Object.values(themeMetadata).filter(theme => theme.category === category);
};

/**
 * Get featured themes
 * @returns {Array} - Array of featured theme metadata objects
 */
export const getFeaturedThemes = () => {
  // For now, return the first 3 themes as featured
  return Object.values(themeMetadata).slice(0, 3);
};

/**
 * Merge theme config with defaults
 * @param {string} slug - Theme slug
 * @param {Object} userConfig - User's custom configuration
 * @returns {Object} - Merged configuration
 */
export const mergeThemeConfig = (slug, userConfig = {}) => {
  const theme = themeMetadata[slug];
  if (!theme) {
    return userConfig;
  }
  return {
    ...theme.defaultConfig,
    ...userConfig,
  };
};

/**
 * Validate theme configuration against layout options
 * @param {string} slug - Theme slug
 * @param {Object} config - Configuration to validate
 * @returns {Object} - { isValid: boolean, errors: string[] }
 */
export const validateThemeConfig = (slug, config) => {
  const theme = themeMetadata[slug];
  if (!theme) {
    return { isValid: false, errors: ['Theme not found'] };
  }

  const errors = [];
  const { layoutOptions } = theme;

  // Check each config option against allowed values
  Object.entries(config).forEach(([key, value]) => {
    if (layoutOptions[key] && !layoutOptions[key].includes(value)) {
      errors.push(`Invalid value "${value}" for ${key}. Allowed: ${layoutOptions[key].join(', ')}`);
    }
  });

  return {
    isValid: errors.length === 0,
    errors,
  };
};

/**
 * Theme categories for filtering
 */
export const themeCategories = [
  { value: 'all', label: 'All Themes' },
  { value: 'professional', label: 'Professional' },
  { value: 'modern', label: 'Modern' },
  { value: 'classic', label: 'Classic' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'bold', label: 'Bold' },
  { value: 'elegant', label: 'Elegant' },
];

export default {
  getThemeComponent,
  getThemeMetadata,
  getAllThemes,
  getThemesByCategory,
  getFeaturedThemes,
  mergeThemeConfig,
  validateThemeConfig,
  themeCategories,
  themeMetadata,
};

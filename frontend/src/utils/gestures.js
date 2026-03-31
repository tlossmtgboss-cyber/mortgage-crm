/**
 * Shared Touch Gesture Utility Library
 *
 * Provides foundational gesture detection and math utilities used by multiple
 * mobile components in the Perennia AI app. All functions are pure with no
 * side effects, making them safe to call from any context (event handlers,
 * animation frames, workers, etc.).
 *
 * Covers: swipe detection, pinch/zoom, rotation, edge-zone awareness,
 * rubber-band damping, and spring physics for snappy animations.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Threshold values used across gesture detection logic.
 * Import and reference these instead of scattering magic numbers.
 *
 * @readonly
 * @enum {number}
 */
export const GESTURE_CONSTANTS = Object.freeze({
  /** Minimum distance (px) a touch must travel to count as a swipe */
  SWIPE_THRESHOLD: 50,

  /** Minimum velocity (px/ms) for a movement to qualify as a swipe */
  SWIPE_VELOCITY_THRESHOLD: 0.3,

  /** Duration (ms) a touch must be held to trigger a long-press */
  LONG_PRESS_DURATION: 500,

  /** Maximum movement (px) allowed during a long-press before it cancels */
  LONG_PRESS_MOVE_TOLERANCE: 10,

  /** Minimum scale delta before a pinch gesture is recognized */
  PINCH_THRESHOLD: 0.1,

  /** Width (px) of the iOS back-gesture edge zone on each side */
  EDGE_ZONE_WIDTH: 20,

  /** Maximum duration (ms) for a touch to be classified as a tap */
  TAP_DURATION_MAX: 200,
});

// ---------------------------------------------------------------------------
// Geometric helpers
// ---------------------------------------------------------------------------

/**
 * Calculate the Euclidean distance between two touch points.
 * Useful for measuring pinch spread.
 *
 * @param {{ clientX: number, clientY: number }} touch1 - First touch point.
 * @param {{ clientX: number, clientY: number }} touch2 - Second touch point.
 * @returns {number} Distance in pixels.
 */
export function getDistance(touch1, touch2) {
  const dx = touch2.clientX - touch1.clientX;
  const dy = touch2.clientY - touch1.clientY;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Get the center point between two touches.
 * Useful as the transform-origin for pinch-to-zoom.
 *
 * @param {{ clientX: number, clientY: number }} touch1 - First touch point.
 * @param {{ clientX: number, clientY: number }} touch2 - Second touch point.
 * @returns {{ x: number, y: number }} Center coordinates.
 */
export function getCenter(touch1, touch2) {
  return {
    x: (touch1.clientX + touch2.clientX) / 2,
    y: (touch1.clientY + touch2.clientY) / 2,
  };
}

/**
 * Get the angle (in degrees) of the line connecting two touch points.
 * Useful for detecting rotation gestures. Returns a value in [-180, 180].
 *
 * @param {{ clientX: number, clientY: number }} touch1 - First touch point.
 * @param {{ clientX: number, clientY: number }} touch2 - Second touch point.
 * @returns {number} Angle in degrees.
 */
export function getAngle(touch1, touch2) {
  const dx = touch2.clientX - touch1.clientX;
  const dy = touch2.clientY - touch1.clientY;
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

// ---------------------------------------------------------------------------
// Swipe helpers
// ---------------------------------------------------------------------------

/**
 * Determine the dominant swipe direction from start to end coordinates.
 * Compares absolute horizontal vs. vertical displacement and returns the
 * axis with greater magnitude.
 *
 * @param {number} startX - Starting X coordinate.
 * @param {number} startY - Starting Y coordinate.
 * @param {number} endX   - Ending X coordinate.
 * @param {number} endY   - Ending Y coordinate.
 * @returns {'left' | 'right' | 'up' | 'down'} Cardinal swipe direction.
 */
export function getDirection(startX, startY, endX, endY) {
  const dx = endX - startX;
  const dy = endY - startY;

  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? 'right' : 'left';
  }
  return dy >= 0 ? 'down' : 'up';
}

/**
 * Calculate swipe velocity.
 *
 * @param {number} distance - Distance traveled in pixels.
 * @param {number} duration - Time elapsed in milliseconds.
 * @returns {number} Velocity in px/ms. Returns 0 if duration is zero.
 */
export function getVelocity(distance, duration) {
  if (duration <= 0) {
    return 0;
  }
  return distance / duration;
}

// ---------------------------------------------------------------------------
// Edge zone detection
// ---------------------------------------------------------------------------

/**
 * Check whether a horizontal touch position falls within the iOS back-gesture
 * edge zone. This is the narrow strip along the left (and optionally right)
 * edge of the screen where the OS intercepts swipes for navigation.
 *
 * Components should avoid starting custom gestures when the touch originates
 * here, otherwise they will fight with the native back swipe.
 *
 * @param {number} x           - The clientX of the touch.
 * @param {number} screenWidth - The viewport / screen width in pixels.
 * @param {number} [edgeSize=20] - Width of the edge zone in pixels.
 * @returns {boolean} True if the touch is inside either edge zone.
 */
export function isInEdgeZone(x, screenWidth, edgeSize = 20) {
  return x <= edgeSize || x >= screenWidth - edgeSize;
}

// ---------------------------------------------------------------------------
// Math helpers
// ---------------------------------------------------------------------------

/**
 * Clamp a numeric value between a minimum and maximum bound.
 *
 * @param {number} value - The value to clamp.
 * @param {number} min   - Lower bound.
 * @param {number} max   - Upper bound.
 * @returns {number} The clamped value.
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

/**
 * Apply rubber-band damping to a value. Used for the "overscroll" feel
 * when a user drags past the content boundary. The further past the
 * boundary, the more resistance is applied.
 *
 * @param {number} value      - The raw displacement past the boundary.
 * @param {number} [factor=0.5] - Damping factor (0 = fully damped, 1 = no damping).
 * @returns {number} The damped displacement.
 */
export function dampValue(value, factor = 0.5) {
  if (value === 0) {
    return 0;
  }
  const sign = value < 0 ? -1 : 1;
  const abs = Math.abs(value);
  return sign * abs * factor;
}

// ---------------------------------------------------------------------------
// Spring physics
// ---------------------------------------------------------------------------

/**
 * Compute the next frame of a critically-damped spring animation.
 * Call this on every animation frame, passing the returned values back
 * in on the next frame to converge on the target.
 *
 * Based on a simple damped harmonic oscillator:
 *   acceleration = -stiffness * (current - target) - damping * velocity
 *
 * Uses a fixed 16ms timestep (approx. 60 fps).
 *
 * @param {number} current     - Current position.
 * @param {number} target      - Desired resting position.
 * @param {number} velocity    - Current velocity (px/frame).
 * @param {number} [stiffness=200] - Spring stiffness (higher = snappier).
 * @param {number} [damping=20]    - Damping coefficient (higher = less bouncy).
 * @returns {{ position: number, velocity: number }} Next position and velocity.
 */
export function springAnimation(
  current,
  target,
  velocity,
  stiffness = 200,
  damping = 20,
) {
  const dt = 1 / 60; // normalized timestep (~16ms at 60 fps)
  const displacement = current - target;
  const springForce = -stiffness * displacement;
  const dampingForce = -damping * velocity;
  const acceleration = springForce + dampingForce;

  const nextVelocity = velocity + acceleration * dt;
  const nextPosition = current + nextVelocity * dt;

  return {
    position: nextPosition,
    velocity: nextVelocity,
  };
}

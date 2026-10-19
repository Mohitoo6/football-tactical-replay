/** The intro plays once per visit, and never when the viewer asks for reduced motion. */
export function shouldPlayIntro(): boolean {
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
    return sessionStorage.getItem('intro-seen') !== '1';
  } catch { return true; }
}

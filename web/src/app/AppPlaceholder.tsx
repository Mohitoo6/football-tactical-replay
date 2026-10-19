import Nav from '../components/Nav';

/** Stands in for the app screens (Library, Replay, Upload) until Part B2. */
export default function AppPlaceholder() {
  return (
    <>
      <Nav variant="app" />
      <main className="container" style={{ paddingTop: 140 }}>
        <p className="eyebrow">Coming next</p>
        <h1 className="headline" style={{ fontSize: 'var(--step-3)' }}>The app screens are being built.</h1>
      </main>
    </>
  );
}

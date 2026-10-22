import io from 'socket.io-client';

// Keep the session owner stable across cockpit UI hot updates.
// Parallel/installation-safe: the Electron main process injects the backend
// port into the page query string (a vite build statically bundles process.env,
// so runtime env cannot be read from production renderer code).
const queryPort=new URLSearchParams(window.location.search).get('sparkBackendPort');
const backendPort=queryPort || process.env.SPARK_BACKEND_PORT || '8000';
const socket=import.meta.hot?.data.sparkSocket || io('http://localhost:'+backendPort);
if(import.meta.hot)import.meta.hot.data.sparkSocket=socket;
export default socket;

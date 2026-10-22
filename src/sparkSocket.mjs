import io from 'socket.io-client';

// Keep the session owner stable across cockpit UI hot updates.
// Parallel/installation-safe: SPARK_BACKEND_PORT lets a second SPARK
// checkout (e.g. a commissioning worktree) run its own backend without
// touching the original SPARK installation's localhost port.
const backendPort=process.env.SPARK_BACKEND_PORT||'8000';
const socket=import.meta.hot?.data.sparkSocket || io('http://localhost:'+backendPort);
if(import.meta.hot)import.meta.hot.data.sparkSocket=socket;
export default socket;

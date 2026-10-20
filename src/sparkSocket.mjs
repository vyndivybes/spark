import io from 'socket.io-client';

// Keep the session owner stable across cockpit UI hot updates.
const socket=import.meta.hot?.data.sparkSocket || io('http://localhost:8000');
if(import.meta.hot)import.meta.hot.data.sparkSocket=socket;
export default socket;

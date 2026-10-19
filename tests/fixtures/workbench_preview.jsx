import React from 'react';
import {createRoot} from 'react-dom/client';
import io from 'socket.io-client';
import WorkbenchPanel from '../../src/components/WorkbenchPanel';
import ReminderToast from '../../src/components/ReminderToast';
import IntelligenceConsole from '../../src/components/IntelligenceConsole';

const socket=io({auth:{acceptance:true}});
const root=createRoot(document.getElementById('root'));
const render=()=>root.render(window.location.search.includes('intelligence')?<IntelligenceConsole socket={socket} project="acceptance"/>:<><WorkbenchPanel socket={socket} project="acceptance"/><ReminderToast socket={socket} project="acceptance" enabled/></>);
render();socket.on('connect',render);

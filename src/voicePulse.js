const palette=['#3b82f6','#10b981','#f87171','#fbbf24','#a78bfa','#f472b6','#6b7280'];
const types={organization:0,organisation:0,division:1,project:2,contact:3,document:4,decision:5,record:6};
let index=0,current=null;
function pulse(){const choice=types[current]??index++%palette.length;document.documentElement.style.setProperty('--spark-pulse-color',palette[choice]);}
// Use the existing approved voice session. Never start a second recognition/microphone stream.
window.sparkVoicePulse=pulse;
window.updateNodeType=type=>{current=type;pulse();};

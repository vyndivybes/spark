/* Local-only advisory policy for SPARK diagnostics.
 * Measurements come from existing, whitelisted /status vitals; no background
 * collectors, new permissions, process termination, file deletion or cloud AI.
 * Thresholds are generic operational guidance, not a device-specific diagnosis.
 */
const valid=(v,max)=>typeof v==='number' && Number.isFinite(v) && v>=0 && v<=max;

export function getPressureAdvice(vitals){
 const h=vitals && typeof vitals==='object' && !Array.isArray(vitals)?vitals:{};
 const findings=[];
 if(valid(h.ram_percent,100) && h.ram_percent>=80){
   findings.push({
     id:'memory',label:'Memory pressure',
     text:'RAM usage is '+h.ram_percent.toFixed(1)+'%. Close unused Chrome tabs or other applications before running resource-intensive audits.',
     action:'advice_only'
   });
 }
 if(valid(h.disk_free_gb,1048576) && h.disk_free_gb<=15){
   findings.push({
     id:'storage',label:'Low disk headroom',
     text:'Only '+h.disk_free_gb.toFixed(2)+' GB free on the monitored system drive. Review large temporary or downloaded files before installing build dependencies; SPARK will not delete anything.',
     action:'advice_only'
   });
 }
 if(h.ac_connected===false && valid(h.battery_percent,100) && h.battery_percent<=25){
   findings.push({
     id:'battery',label:'Low battery',
     text:'Battery is '+h.battery_percent.toFixed(1)+'% and AC is disconnected. Connect your charger before lengthy builds or audits.',
     action:'advice_only'
   });
 }
 if(valid(h.cpu_percent,100) && h.cpu_percent>=90){
   findings.push({
     id:'cpu',label:'High CPU load',
     text:'CPU load is '+h.cpu_percent.toFixed(1)+'% in the latest snapshot. Avoid simultaneous heavy builds and close unneeded workloads manually.',
     action:'advice_only'
   });
 }
 return findings;
}

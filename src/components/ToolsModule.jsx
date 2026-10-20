import React, {useEffect, useRef, useState} from 'react';
import {Mic, MicOff, Settings, Power, Video, VideoOff, Hand, Lightbulb, Printer, Globe, Box, MoreHorizontal, X} from 'lucide-react';

export default function ToolsModule(props) {
    const [expanded,setExpanded]=useState(false);
    const root=useRef(null);
    useEffect(()=>{
        if(!expanded)return undefined;
        const outside=event=>{if(!root.current?.contains(event.target))setExpanded(false);};
        const escape=event=>{if(event.key==='Escape'){setExpanded(false);root.current?.querySelector('[aria-controls="cockpit-device-tools"]')?.focus();}};
        document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
        return ()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
    },[expanded]);
    const devices=[
        ['Settings',Settings,props.onToggleSettings,props.showSettings],
        ['Hand tracking',Hand,props.onToggleHand,props.isHandTrackingEnabled],
        ['Lights',Lightbulb,props.onToggleKasa,props.showKasaWindow],
        ['Printers',Printer,props.onTogglePrinter,props.showPrinterWindow],
        ['CAD',Box,props.onToggleCad,props.showCadWindow],
        ['Browser',Globe,props.onToggleBrowser,props.showBrowserWindow],
    ];
    return <div id="tools" ref={root} className="spatial-dock" onMouseDown={props.onMouseDown} style={{left:props.position.x,top:props.position.y,transform:'translate(-50%, -50%)',pointerEvents:'auto'}}>
        <div className="spatial-dock-primary">
            <button type="button" onClick={props.onTogglePower} aria-label={props.isConnected?'Turn Spark off':'Turn Spark on'} aria-pressed={props.isConnected} className="dock-power"><Power size={19}/></button>
            <span className="dock-separator"/>
            <button type="button" className="dock-mic" onClick={props.onToggleMute} disabled={!props.isConnected} aria-label={props.isMuted?'Unmute microphone':'Mute microphone'} aria-pressed={!props.isMuted}>{props.isMuted?<MicOff size={20}/>:<Mic size={20}/>}<span>{props.isMuted?'Mic muted':'Mic on'}</span></button>
            <button type="button" onClick={props.onToggleVideo} aria-label={props.isVideoOn?'Turn camera off':'Turn camera on'} aria-pressed={props.isVideoOn}>{props.isVideoOn?<Video size={19}/>:<VideoOff size={19}/>}</button>
            <span className="dock-separator"/>
            <button type="button" aria-label="Device tools" aria-controls="cockpit-device-tools" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?<X size={20}/>:<MoreHorizontal size={20}/>}</button>
        </div>
        {expanded&&<div id="cockpit-device-tools" className="spatial-device-tray" aria-label="Device tools">{devices.map(([name,Icon,action,active])=><button type="button" key={name} aria-pressed={Boolean(active)} onClick={()=>{action();setExpanded(false);}}><Icon size={17}/><span>{name}</span></button>)}</div>}
    </div>;
}

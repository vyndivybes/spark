// Synthetic tones for verification only. This fixture never requests a mic.
import React from 'react';
import {createRoot} from 'react-dom/client';
import Visualizer from '../../src/components/Visualizer';
import {BrowserEchoAudio} from '../../src/audio/BrowserEchoAudio.mjs';
import {voiceBands} from '../../src/utils/brainGalaxy.mjs';
const root=createRoot(document.getElementById('root'));
let bridge=null, oscillator=null, context=null;
const extraTones=[];
const paint=listening=>root.render(<Visualizer graph={window.galaxyFixtureGraph}
    width="100vw" height="100vh" isListening={listening} getSpectrum={()=>bridge?.readSpectrum()}/>);
paint(false);
window.galaxyTest={
    async tone(frequency){
        if(!context){
            context=new AudioContext({sampleRate:48000});
            const analyser=context.createAnalyser();analyser.fftSize=512;analyser.smoothingTimeConstant=0;
            const silent=context.createGain();silent.gain.value=0;
            oscillator=context.createOscillator();oscillator.connect(analyser);analyser.connect(silent);silent.connect(context.destination);
            bridge=new BrowserEchoAudio({socket:{connected:false,on(){},off(){}}});
            Object.assign(bridge,{ready:true,closed:false,muted:false,audioContext:context,analyser,spectrumBins:new Uint8Array(analyser.frequencyBinCount)});
            oscillator.start();await context.resume();
        }
        oscillator.frequency.value=frequency;bridge.setMuted(false);paint(true);
    },
    bands(){return voiceBands(bridge?.readSpectrum());},
    async chord(){
        await this.tone(187.5);
        for(const frequency of [937.5,3000,7500]){
            const tone=context.createOscillator(),gain=context.createGain();gain.gain.value=.45;
            tone.frequency.value=frequency;tone.connect(gain);gain.connect(bridge.analyser);tone.start();extraTones.push(tone);
        }
    },
    mute(){bridge?.setMuted(true);paint(false);},
    async stop(){oscillator?.stop();extraTones.forEach(tone=>tone.stop());await context?.close();}
};

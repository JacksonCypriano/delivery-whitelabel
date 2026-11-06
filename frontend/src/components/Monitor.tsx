import {useEffect,useRef,useState,type ReactNode} from "react";
export function Monitor({children}:{children:ReactNode}) {
 const root=useRef<HTMLDivElement>(null),[full,setFull]=useState(false),[error,setError]=useState("");
 useEffect(()=>{const change=()=>setFull(document.fullscreenElement===root.current);document.addEventListener("fullscreenchange",change);return()=>document.removeEventListener("fullscreenchange",change);},[]);
 async function toggle(){try{setError("");if(document.fullscreenElement)await document.exitFullscreen();else if(root.current?.requestFullscreen)await root.current.requestFullscreen();else setError("Tela cheia indisponível neste navegador.");}catch{setError("Não foi possível ativar a tela cheia.");}}
 return <div className="monitor-screen" ref={root}><div className="monitor-toolbar"><button className="secondary" onClick={toggle}>{full?"Sair da tela cheia":"Tela cheia"}</button>{full&&<small>Esc para sair</small>}{error&&<span role="status">{error}</span>}</div>{children}</div>;
}

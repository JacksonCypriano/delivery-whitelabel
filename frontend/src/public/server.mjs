import http from 'node:http';
import {renderDocument} from './document.mjs';
const server=http.createServer((req,res)=>{
  if(req.method==='GET'&&req.url==='/health'){res.end('ok');return;}
  if(req.method!=='POST'||req.url!=='/render'){res.writeHead(404).end();return;}
  let body='',bytes=0;
  req.on('data',chunk=>{bytes+=chunk.length;if(bytes>4*1024*1024){res.writeHead(413).end();req.destroy();return;}body+=chunk;});
  req.on('end',()=>{try{const html=renderDocument(JSON.parse(body));res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end(html);}catch(error){console.error('SSR render failed:',error.message);res.writeHead(500).end('Renderização indisponível');}});
});
server.requestTimeout=10000;server.headersTimeout=10000;
server.listen(Number(process.env.PUBLIC_SSR_PORT||3001),process.env.PUBLIC_SSR_HOST||'127.0.0.1');

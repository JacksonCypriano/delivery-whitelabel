#!/usr/bin/env python3
"""VemDeDelivery local ESC/POS agent. Python 3.11+, network or Windows RAW spool.

Token in VDD_PRINT_TOKEN environment only. Journal must remain on persistent disk.
A claimed job is never automatically reclaimed by the server. This deliberately
prefers human reconciliation over duplicate paper after a crash/network timeout.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
import socket
import sqlite3
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def escpos(job):
    text=''.join(c for c in job['text'] if c=='\n' or 32<=ord(c)!=127)
    # Epson-compatible CP850, 32/48 columns already wrapped on the server.
    one=b'\x1b@\x1bt\x02'+text.encode('cp850',errors='replace')+b'\n\n\n\x1dV\x00'
    copies=int(job['copies'])
    if not 1<=copies<=3: raise ValueError('invalid copies')
    return one*copies


def windows_spool(name,data):
    if os.name!='nt': raise RuntimeError('Windows printer requires Windows')
    spool=ctypes.WinDLL('winspool.drv',use_last_error=True)
    class DOC_INFO(ctypes.Structure):
        _fields_=[('pDocName',wintypes.LPWSTR),('pOutputFile',wintypes.LPWSTR),('pDatatype',wintypes.LPWSTR)]
    spool.OpenPrinterW.argtypes=[wintypes.LPWSTR,ctypes.POINTER(wintypes.HANDLE),ctypes.c_void_p]
    spool.StartDocPrinterW.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(DOC_INFO)]
    spool.StartDocPrinterW.restype=wintypes.DWORD
    spool.StartPagePrinter.argtypes=[wintypes.HANDLE]
    spool.WritePrinter.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    spool.EndPagePrinter.argtypes=[wintypes.HANDLE]
    spool.EndDocPrinter.argtypes=[wintypes.HANDLE]
    spool.ClosePrinter.argtypes=[wintypes.HANDLE]
    handle=wintypes.HANDLE()
    if not spool.OpenPrinterW(name,ctypes.byref(handle),None): raise OSError('Cannot open printer')
    try:
        doc=DOC_INFO('VemDeDelivery - comprovante nao fiscal',None,'RAW')
        if not spool.StartDocPrinterW(handle,1,ctypes.byref(doc)): raise OSError('Cannot start spool')
        if not spool.StartPagePrinter(handle): raise OSError('Cannot start page')
        written=wintypes.DWORD();buf=ctypes.create_string_buffer(data)
        if not spool.WritePrinter(handle,buf,len(data),ctypes.byref(written)) or written.value!=len(data): raise OSError('Spool uncertain')
        if not spool.EndPagePrinter(handle) or not spool.EndDocPrinter(handle): raise OSError('Spool uncertain')
    finally: spool.ClosePrinter(handle)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',required=True,help='HTTPS store origin, e.g. https://shop.example.com')
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--network',help='Local printer IP, raw TCP port 9100')
    target.add_argument('--windows-printer',help='Exact installed Windows printer name')
    parser.add_argument('--journal',default='vdd-print-journal.sqlite3')
    args=parser.parse_args()
    u=urlsplit(args.url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in {'','/'}: parser.error('Use an HTTPS store origin')
    token=os.environ.get('VDD_PRINT_TOKEN','')
    if len(token)<32: parser.error('Set VDD_PRINT_TOKEN')
    db=sqlite3.connect(args.journal)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, acked INTEGER NOT NULL DEFAULT 0)')
    def api(payload):
        req=Request(args.url.rstrip('/')+'/integracoes/print-device/',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        # Reject redirects: bearer token must stay on the configured store host.
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        with build_opener(NoRedirect).open(req,timeout=15) as response:
            raw=response.read(128001)
            if len(raw)>128000: raise ValueError('Response too large')
            return json.loads(raw)
    while True:
        try:
            for jid,state in db.execute('SELECT id,state FROM jobs WHERE acked=0').fetchall():
                api({'action':'ack','job':jid,'state':'uncertain' if state=='sending' else state})
                db.execute('UPDATE jobs SET acked=1 WHERE id=?',(jid,));db.commit()
            job=api({'action':'claim'}).get('job')
            if job:
                if db.execute('SELECT 1 FROM jobs WHERE id=?',(job['id'],)).fetchone():
                    time.sleep(2);continue
                db.execute('INSERT INTO jobs(id,state) VALUES (?,?)',(job['id'],'sending'));db.commit()
                try:
                    data=escpos(job)
                    if args.network:
                        with socket.create_connection((args.network,9100),timeout=10) as printer:
                            printer.settimeout(10);printer.sendall(data)
                    else: windows_spool(args.windows_printer,data)
                    state='spooled'
                except Exception: state='uncertain'
                db.execute('UPDATE jobs SET state=? WHERE id=?',(state,job['id']));db.commit()
                print('Job',job['id'],state,flush=True)
        except Exception:
            print('Connection unavailable; journal retained. Retrying polling only.',flush=True)
        time.sleep(3)


if __name__=='__main__': main()

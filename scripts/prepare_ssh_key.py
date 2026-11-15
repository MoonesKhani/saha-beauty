"""Normalize SSH private-key transport formatting; never change or reveal GitHub Secrets."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import textwrap

class KeyFormatError(ValueError):pass

def normalize(value):
    if not value or not value.strip():raise KeyFormatError('ARVAN_SSH_KEY is unavailable to this workflow run; start a NEW status run after saving repository secrets')
    changes=[]
    text=value.strip().lstrip('\ufeff').strip()
    if text.startswith('"') and text.endswith('"'):
        try:decoded=json.loads(text)
        except json.JSONDecodeError:decoded=text[1:-1]
        if isinstance(decoded,str):text=decoded;changes.append('quoted text')
    elif text.startswith("'") and text.endswith("'"):
        text=text[1:-1];changes.append('quoted text')
    if '\r' in text:text=text.replace('\r\n','\n').replace('\r','\n');changes.append('CRLF line endings')
    if '\\n' in text:text=text.replace('\\r\\n','\n').replace('\\n','\n');changes.append('escaped newlines')
    text=text.strip()
    if not text.startswith('-----BEGIN '):
        if re.match(r'(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+)\s',text):raise KeyFormatError('ARVAN_SSH_KEY contains a PUBLIC key; SSH needs the dedicated PRIVATE key, not the .pub file')
        try:raw=base64.b64decode(''.join(text.split()),validate=True)
        except ValueError:raw=b''
        if raw.startswith(b'openssh-key-v1\0'):
            text='-----BEGIN OPENSSH PRIVATE KEY-----\n'+base64.b64encode(raw).decode('ascii')+'\n-----END OPENSSH PRIVATE KEY-----';changes.append('bare OpenSSH payload')
        else:
            try:decoded=raw.decode('ascii')
            except UnicodeDecodeError:decoded=''
            if decoded.startswith('-----BEGIN '):text=decoded.strip();changes.append('base64 envelope')
    kinds=r'(OPENSSH\s+PRIVATE\s+KEY|RSA\s+PRIVATE\s+KEY|EC\s+PRIVATE\s+KEY|PRIVATE\s+KEY|ENCRYPTED\s+PRIVATE\s+KEY)'
    begins=list(re.finditer(r'-----BEGIN\s+'+kinds+r'-----',text))
    ends=list(re.finditer(r'-----END\s+'+kinds+r'-----',text))
    if len(begins)!=1 or len(ends)!=1:
        if text.startswith('PuTTY-User-Key-File-'):raise KeyFormatError('ARVAN_SSH_KEY is a PuTTY-format key, not an OpenSSH/PEM private key')
        raise KeyFormatError('Private-key markers are missing or ambiguous (begin='+('present' if begins else 'absent')+', end='+('present' if ends else 'absent')+'); the existing secret cannot be repaired without complete private-key data')
    begin,end=begins[0],ends[0]
    kind=' '.join(begin[1].split())
    if kind!=' '.join(end[1].split()) or end.start()<begin.end():raise KeyFormatError('Private-key begin/end markers do not match')
    body=text[begin.end():end.start()]
    if text[:begin.start()].strip() or text[end.end():].strip():changes.append('surrounding clipboard text')
    if begin[0]!=f'-----BEGIN {kind}-----' or end[0]!=f'-----END {kind}-----':changes.append('wrapped key markers')
    if kind=='ENCRYPTED PRIVATE KEY' or 'ENCRYPTED' in body:raise KeyFormatError('The key is passphrase-protected; the dedicated noninteractive deployment key is required')
    compact=''.join(body.split())
    try:binary=base64.b64decode(compact,validate=True)
    except ValueError:raise KeyFormatError('Private-key body is incomplete or corrupted; formatting repair cannot recreate missing key data') from None
    if not binary:raise KeyFormatError('Private-key body is empty')
    if kind=='OPENSSH PRIVATE KEY':
        magic=b'openssh-key-v1\0'
        if not binary.startswith(magic) or len(binary)<len(magic)+4:raise KeyFormatError('Invalid OpenSSH key payload')
        length=struct.unpack('>I',binary[len(magic):len(magic)+4])[0]
        if length>256 or len(magic)+4+length>len(binary):raise KeyFormatError('OpenSSH key payload is truncated or corrupted')
        cipher=binary[len(magic)+4:len(magic)+4+length]
        if cipher!=b'none':raise KeyFormatError('The key is passphrase-protected; the dedicated noninteractive deployment key is required')
    normalized=f'-----BEGIN {kind}-----\n'+textwrap.fill(compact,width=70)+f'\n-----END {kind}-----\n'
    if normalized!=value and not changes:changes.append('armor whitespace/wrapping')
    return normalized,changes

def prepare(value,path):
    key,changes=normalize(value)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as file:file.write(key)
    result=subprocess.run(['ssh-keygen','-y','-P','','-f',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    if result.returncode:
        path.unlink(missing_ok=True)
        raise KeyFormatError('Normalized private key still cannot be parsed; key data is invalid or unsupported. No secret value was logged')
    return changes

def is_known_hosts(value):
    lines=[line.strip() for line in value.replace('\r','').replace('\\n','\n').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    pattern=r'(?:@cert-authority\s+|@revoked\s+)?\S+\s+(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+)\s+[A-Za-z0-9+/]+=*(?:\s+.*)?'
    return bool(lines) and all(re.fullmatch(pattern,line) for line in lines)

def prepare_credentials(key_value,hosts_value,key_path,hosts_path):
    swapped=False
    if is_known_hosts(key_value):
        try:normalize(hosts_value)
        except KeyFormatError:
            raise KeyFormatError('ARVAN_SSH_KEY contains host-key data, but the other secret is not a readable private key; no secret was changed') from None
        key_value,hosts_value=hosts_value,key_value;swapped=True
    changes=prepare(key_value,key_path)
    if not is_known_hosts(hosts_value):
        key_path.unlink(missing_ok=True)
        raise KeyFormatError('ARVAN_KNOWN_HOSTS is not a known_hosts entry; strict host verification remains required')
    hosts=hosts_value.replace('\r\n','\n').replace('\r','\n').replace('\\n','\n').strip()+'\n'
    try:
        descriptor=os.open(hosts_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as file:file.write(hosts)
    except Exception:
        key_path.unlink(missing_ok=True);raise
    return changes,swapped

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--known-hosts-output',type=Path);args=parser.parse_args()
    try:
        if args.known_hosts_output:
            changes,swapped=prepare_credentials(os.environ.get('ARVAN_SSH_KEY',''),os.environ.get('ARVAN_KNOWN_HOSTS',''),args.output,args.known_hosts_output)
        else:changes=prepare(os.environ.get('ARVAN_SSH_KEY',''),args.output);swapped=False
    except KeyFormatError as error:raise SystemExit(str(error)) from None
    print('ARVAN_SSH_KEY: private-key parsing succeeded; GitHub Secret unchanged')
    if swapped:print('Private-key and known-hosts values were assigned to opposite secret names; runner bindings corrected, repository secrets unchanged')
    if changes:print('Temporary-file formatting normalized: '+', '.join(changes))
if __name__=='__main__':main()

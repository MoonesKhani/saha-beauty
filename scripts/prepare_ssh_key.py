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
    text=value.strip().lstrip('\ufeff')
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
        if text.startswith(('ssh-ed25519 ','ssh-rsa ','ecdsa-sha2-')):raise KeyFormatError('ARVAN_SSH_KEY contains a PUBLIC key; SSH needs the dedicated PRIVATE key, not the .pub file')
        try:decoded=base64.b64decode(''.join(text.split()),validate=True).decode('ascii')
        except (ValueError,UnicodeDecodeError):decoded=''
        if decoded.startswith('-----BEGIN '):text=decoded.strip();changes.append('base64 envelope')
    match=re.fullmatch(r'-----BEGIN (OPENSSH PRIVATE KEY|RSA PRIVATE KEY|EC PRIVATE KEY|PRIVATE KEY|ENCRYPTED PRIVATE KEY)-----\s*(.*?)\s*-----END \1-----',text,re.S)
    if not match:raise KeyFormatError('Private-key header/footer is missing or unsupported; no secret content was logged')
    kind,body=match.groups()
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

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:changes=prepare(os.environ.get('ARVAN_SSH_KEY',''),args.output)
    except KeyFormatError as error:raise SystemExit(str(error)) from None
    print('ARVAN_SSH_KEY: private-key parsing succeeded; GitHub Secret unchanged')
    if changes:print('Temporary-file formatting normalized: '+', '.join(changes))
if __name__=='__main__':main()

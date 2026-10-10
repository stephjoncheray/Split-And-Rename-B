#!/usr/bin/env python3
"""Interface interne Bourses : ZIP en mémoire, simulation, SMTP/IMAP sur action explicite."""
import base64
import csv
import io
import json
import re
import smtplib
import imaplib
import ssl
import time
import threading
import zipfile
from datetime import datetime, timezone
from email.utils import formatdate, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from bourses_sender import load_campaign, create_mail, check_email

HOST, PORT = "127.0.0.1", 8766
MAX_UPLOAD = 100 * 1024 * 1024
MAX_PILOT = 10
LOCK = threading.Lock()
APP = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bourses — Envoi interne</title><style>
:root{font-family:Inter,system-ui,Segoe UI,sans-serif;background:#f3f6fa;color:#192b3c}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1200px;margin:auto;padding:28px 20px}.eyebrow{font-size:12px;letter-spacing:.12em;color:#397194;font-weight:800;text-transform:uppercase}h1{margin:8px 0 20px;font-size:34px}h1 span{color:#20688e}.card{background:white;border:1px solid #dce5ec;border-radius:16px;padding:24px;margin-bottom:18px;box-shadow:0 10px 28px #192b3c08}h2{font-size:19px}label{display:block;font-size:14px;margin:12px 0}input,textarea{display:block;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}input[type=checkbox]{display:inline;width:auto}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #e6edf2;text-align:left;padding:9px;overflow-wrap:anywhere}th{background:#f4f7fa}button{border:0;padding:12px 18px;border-radius:9px;cursor:pointer;background:#145e83;color:white;font-weight:700;margin:4px 6px 4px 0}button.secondary{background:#e3f1f8;color:#145e83}button.danger{background:#a52727}button:disabled{opacity:.45;cursor:not-allowed}.status{white-space:pre-wrap;color:#285774;font-size:14px}small,p{color:#556879;line-height:1.5}a{color:#20688e}@media(max-width:750px){.grid{display:block}}
</style></head><body><div class="wrap"><div class="eyebrow">Serveur interne · Traitement temporaire</div><h1>Envoi des <span>notifications de bourses</span></h1><p>Adresse interne seulement. Les notifications et identifiants ne sont pas sauvegardés par cette interface. Contrôlez chaque destinataire avant transmission.</p>
<section class="card"><h2>1. Charger et contrôler la campagne</h2><label>ZIP créé par Split-And-Rename-B<input id="zip" type="file" accept=".zip"></label><button id="analyze">Analyser sans envoyer</button><div id="summary" class="status">Aucune campagne analysée.</div><div class="scroll"><table><thead><tr><th>Élève / classe</th><th>Responsable</th><th>Décision</th><th>Destinataire</th><th>Pièce jointe</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section class="card"><h2>2. Personnaliser le message</h2><p>Laissez vide pour conserver le contenu du ZIP. Variables disponibles : {eleve}, {parent}, {classe}, {decision}.</p><label>Objet de remplacement (facultatif)<input id="subject" maxlength="200"></label><label>Texte de remplacement (facultatif)<textarea id="body" rows="7" maxlength="5000"></textarea></label><button class="secondary" id="preview">Prévisualiser le premier message</button><div id="previewText" class="status"></div></section>
<section class="card"><h2>3. Messagerie académique</h2><div class="grid"><label>Adresse expéditeur<input id="sender" type="email" autocomplete="username" placeholder="prenom.nom@ac-corse.fr"></label><label>Mot de passe applicatif<input id="password" type="password" autocomplete="off"></label></div><label><input type="checkbox" id="sent" checked> Copier les messages acceptés dans IMAP « Sent »</label><small>SMTP smtp.education.gouv.fr:587 STARTTLS · IMAP imap.education.gouv.fr:993 TLS. Ne jamais envoyer les identifiants depuis une page HTTP non chiffrée.</small></section>
<section class="card"><h2>4. Simulation et envoi</h2><button id="simulate" class="secondary" disabled>Simuler — aucun courriel</button><label>Délai entre messages en secondes <input id="delay" type="number" min="3" max="120" value="5"></label><p><strong>Mode pilote : 10 messages maximum.</strong> Relancer une campagne après une erreur peut générer des doublons. Ne jamais recommencer sans lire le journal et vérifier « Envoyés ».</p><label>Pour autoriser l'envoi, saisir ENVOYER<input id="confirm" autocomplete="off"></label><button id="send" class="danger" disabled>Envoyer maintenant</button><p id="status" class="status">En attente.</p><button id="journal" class="secondary" disabled>Télécharger le journal CSV</button></section>
<p><a href="https://stephjoncheray.github.io/Split-And-Rename-B/">Retour à la préparation GitHub Pages</a></p></div><script>
const $=x=>document.getElementById(x);let raw=null,manifest=null,summary=null,csv=null;
const data=()=>({zip:raw,filename:$('zip').files[0]?.name||'',sender:$('sender').value.trim(),password:$('password').value,copy_sent:$('sent').checked,subject_override:$('subject').value,body_override:$('body').value,delay:Number($('delay').value),confirm:$('confirm').value});
async function invoke(action,body){const res=await fetch('./api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const out=await res.json();if(!res.ok)throw Error(out.error||'Erreur de serveur');return out}
$('analyze').onclick=async()=>{try{const f=$('zip').files[0];if(!f)throw Error('Sélectionnez une archive ZIP.');if(f.size>100*1024*1024)throw Error('ZIP trop volumineux.');raw=await new Promise((resolve,reject)=>{const reader=new FileReader;reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Lecture impossible'));reader.readAsDataURL(f)});const v=await invoke('analyze',{zip:raw});manifest=v;summary=v;$('rows').replaceChildren();for(const m of v.messages){const tr=$('rows').insertRow();for(const value of [m.eleve,m.parent,m.decision,m.to,m.attachment])tr.insertCell().textContent=value}$('summary').textContent=v.messages.length+' message(s) valides · Contrôlez les destinataires et les pièces jointes avant envoi.';$('simulate').disabled=false;$('send').disabled=false;$('journal').disabled=true;csv=null}catch(e){$('summary').textContent=e.message;$('simulate').disabled=true;$('send').disabled=true}};
$('zip').onchange=()=>{raw=null;manifest=null;$('rows').replaceChildren();$('simulate').disabled=true;$('send').disabled=true;$('summary').textContent='Analyse nécessaire pour ce nouveau fichier.'};
$('preview').onclick=()=>{if(!manifest?.messages?.length){$('previewText').textContent='Importez d’abord un ZIP.';return}const m=manifest.messages[0];const vars={eleve:m.eleve,parent:m.parent,classe:m.classe,decision:m.decision.toLowerCase()};const sub=( $('subject').value||m.subject).replace(/\{(eleve|parent|classe|decision)\}/gi,(_,k)=>vars[k.toLowerCase()]);const body=($('body').value||m.body).replace(/\{(eleve|parent|classe|decision)\}/gi,(_,k)=>vars[k.toLowerCase()]);$('previewText').textContent='À : '+m.to+'\nObjet : '+sub+'\n\n'+body};
async function run(action){try{if(!raw||!manifest)throw Error('Analyse préalable obligatoire.');if(action==='send'&&!confirm('Envoyer réellement les notifications aux destinataires affichés ?'))return;$('status').textContent='Traitement en cours…';$('simulate').disabled=true;$('send').disabled=true;const out=await invoke(action,data());$('status').textContent=out.summary;csv=out.csv;$('journal').disabled=false}catch(e){$('status').textContent='Erreur : '+e.message}finally{$('simulate').disabled=false;$('send').disabled=false;$('password').value=''}}
$('simulate').onclick=()=>run('simulate');$('send').onclick=()=>run('send');
$('journal').onclick=()=>{if(!csv)return;const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='journal-bourses.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000)};
</script></body></html>"""

def unpack(payload):
    value = payload.get("zip")
    if not isinstance(value, str) or len(value) > MAX_UPLOAD * 1.5:
        raise ValueError("ZIP absent ou trop volumineux")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("Encodage ZIP invalide") from exc
    if len(raw) > MAX_UPLOAD:
        raise ValueError("ZIP trop volumineux")
    return raw

def load_bytes(raw):
    # Reutilise la validation du moteur CLI sans ecrire de ZIP sur le disque.
    import tempfile
    # Validation identique au CLI, mais sur un ZipFile memoire
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist()
        if len(entries)>3500 or sum(m.file_size for m in entries)>500*1024*1024:
            raise ValueError("Archive trop volumineuse")
        names=[m.filename for m in entries]
        if len(names)!=len(set(names)) or "campagne.json" not in names:
            raise ValueError("Manifest ou chemins invalides")
        for m in entries:
            if m.filename.startswith("/") or "\\" in m.filename or ".." in m.filename.split("/") or m.flag_bits & 1:
                raise ValueError("Chemin ZIP interdit")
        if z.getinfo("campagne.json").file_size>5*1024*1024:
            raise ValueError("Manifeste trop volumineux")
        manifest=json.loads(z.read("campagne.json"))
        if manifest.get("source")!="Split-And-Rename-B" or manifest.get("status")!="PREPARE_NON_ENVOYE" or manifest.get("schema_version")!=1:
            raise ValueError("Campagne Bourses non reconnue")
        messages=manifest.get("messages")
        if not isinstance(messages,list) or not 0<len(messages)<=1200:raise ValueError("Nombre de messages invalide")
        used=set()
        for m in messages:
            name=m.get("attachment")
            if m.get("status")!="PREPARE_NON_ENVOYE" or not isinstance(name,str) or not name.startswith("pieces_jointes/") or not name.endswith(".pdf") or name not in names or name in used: raise ValueError("Piece ou statut invalide")
            used.add(name)
            if z.getinfo(name).file_size>20*1024*1024 or not z.read(name).startswith(b"%PDF-"):raise ValueError("Pièce jointe invalide")
            if not isinstance(m.get("to"),list) or len(m["to"])!=1 or not check_email(m["to"][0]):raise ValueError("Destinataire invalide")
            if m.get("decision") not in ("Acceptation","Refus"):raise ValueError("Décision invalide")
            if not isinstance(m.get("eleve"),dict) or not isinstance(m.get("responsable"),dict):raise ValueError("Identité manquante")
            for k in ("subject","body"):
                if not isinstance(m.get(k),str) or len(m[k])>20000:raise ValueError("Texte de courriel invalide")
        return manifest

def replacements(text, m):
    d={"eleve":m["eleve"].get("prenom","")+" "+m["eleve"].get("nom",""),
       "parent":m["responsable"].get("prenom","")+" "+m["responsable"].get("nom",""),
       "classe":m["eleve"].get("classe",""), "decision":m["decision"].lower()}
    return re.sub(r"\{(eleve|parent|classe|decision)\}",lambda match:d[match.group(1).lower()],text,flags=re.I)

def action(raw, opts, send):
    manifest=load_bytes(raw)
    if send and len(manifest["messages"])>MAX_PILOT:raise ValueError("Pilote limite à 10 messages")
    sender=opts.get("sender","")
    if send and (not check_email(sender) or not isinstance(opts.get("password"),str) or not opts["password"]):
        raise ValueError("Compte SMTP incomplet")
    if send and opts.get("confirm")!="ENVOYER":raise ValueError("Saisir ENVOYER avant transmission")
    delay=opts.get("delay",5)
    if send and (not isinstance(delay,(float,int)) or not 3<=delay<=120):raise ValueError("Délai invalide")
    subject=opts.get("subject_override","")
    body=opts.get("body_override","")
    if not isinstance(subject,str) or len(subject)>200 or "\n" in subject or "\r" in subject or not isinstance(body,str) or len(body)>5000:
        raise ValueError("Personnalisation invalide")
    if not check_email(sender):sender="simulation@example.invalid"
    result=[]
    smtp=None;imap=None
    try:
        if send:
            smtp=smtplib.SMTP("smtp.education.gouv.fr",587,timeout=30)
            smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo();smtp.login(sender,opts["password"])
            if opts.get("copy_sent"):
                imap=imaplib.IMAP4_SSL("imap.education.gouv.fr",993,ssl_context=ssl.create_default_context(),timeout=30)
                imap.login(sender,opts["password"])
                code,_=imap.select("Sent",readonly=False)
                if code!="OK":raise RuntimeError("Dossier IMAP Sent introuvable : envoi annulé")
                imap.close()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for index,m in enumerate(manifest["messages"],1):
                entry=dict(m);entry["subject"]=replacements(subject or m["subject"],m);entry["body"]=replacements(body or m["body"],m)
                mail=create_mail(entry,z.read(m["attachment"]),sender)
                line={"index":index,"eleve":str(m["eleve"]),"parent":str(m["responsable"]),"to":m["to"][0],"attachment":m["attachment"],"smtp":"SIMULATION","imap":"NON_TENTE","date_utc":datetime.now(timezone.utc).isoformat(),"message_id":str(mail["Message-ID"]),"detail":""}
                if send:
                    # Toute erreur de connexion après une tentative d'envoi rend la reprise incertaine.
                    try:
                        refused=smtp.sendmail(sender,m["to"],mail.as_bytes())
                        line["smtp"]="PARTIEL" if refused else "ACCEPTE_PAR_RELAIS"
                        if refused:line["detail"]=str(refused)[:250]
                        if imap and not refused:
                            try:
                                code,_=imap.append("Sent","\\Seen",imaplib.Time2Internaldate(datetime.now().timestamp()),mail.as_bytes())
                                line["imap"]="COPIE_OK" if code=="OK" else "COPIE_ERREUR"
                            except Exception as exc:line["imap"]="COPIE_ERREUR";line["detail"]=str(exc)[:250]
                    except Exception as exc:
                        line["smtp"]="INCERTAIN";line["detail"]=str(exc)[:250]
                result.append(line)
                if send and index<len(manifest["messages"]):time.sleep(delay)
    finally:
        if smtp:
            try:smtp.quit()
            except Exception:pass
        if imap:
            try:imap.logout()
            except Exception:pass
    report=io.StringIO();report.write("\ufeff")
    fields=["index","date_utc","eleve","parent","to","attachment","message_id","smtp","imap","detail"]
    writer=csv.DictWriter(report,fieldnames=fields,delimiter=";");writer.writeheader();writer.writerows(result)
    return {"summary":f"{len(result)} message(s) traités · "+str(sum(r["smtp"]=="ACCEPTE_PAR_RELAIS" for r in result))+" accepté(s) SMTP · "+str(sum(r["imap"]=="COPIE_OK" for r in result))+" copié(s) IMAP.","csv":report.getvalue()}

class Handler(BaseHTTPRequestHandler):
    def output(self,status,data):
        blob=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length",str(len(blob)))
        self.end_headers();self.wfile.write(blob)
    def do_GET(self):
        if urlparse(self.path).path!="/":
            self.send_error(404);return
        blob=APP.encode()
        self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Content-Length",str(len(blob)));self.end_headers();self.wfile.write(blob)
    def do_POST(self):
        endpoint=urlparse(self.path).path
        if endpoint not in ("/api/analyze","/api/simulate","/api/send"):
            return self.output(404,{"error":"Route inconnue"})
        # Same-origin : le navigateur depuis GitHub Pages n'a pas accès à cette API par CORS.
        origin=self.headers.get("Origin")
        host=self.headers.get("Host","")
        if origin and urlparse(origin).netloc!=host:
            return self.output(403,{"error":"Origine non autorisée"})
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
            return self.output(415,{"error":"JSON requis"})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<=0 or size>MAX_UPLOAD*1.5:raise ValueError("Taille invalide")
            opts=json.loads(self.rfile.read(size))
            raw=unpack(opts)
            if endpoint=="/api/analyze":
                manifest=load_bytes(raw)
                return self.output(200,{"messages":[{"eleve":m["eleve"].get("prenom","")+" "+m["eleve"].get("nom","")+" ("+m["eleve"].get("classe","")+")","classe":m["eleve"].get("classe",""),"parent":m["responsable"].get("prenom","")+" "+m["responsable"].get("nom",""),"decision":m["decision"],"to":m["to"][0],"attachment":m["attachment"],"subject":m["subject"],"body":m["body"]} for m in manifest["messages"]]})
            if endpoint=="/api/send":
                if not LOCK.acquire(blocking=False):return self.output(409,{"error":"Un envoi est déjà en cours"})
                try: result=action(raw,opts,True)
                finally:LOCK.release()
            else:result=action(raw,opts,False)
            return self.output(200,result)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError,zipfile.BadZipFile,RuntimeError,smtplib.SMTPException,imaplib.IMAP4.error,OSError) as exc:
            return self.output(400,{"error":str(exc)[:280]})
    def log_message(self,*args):pass

if __name__=="__main__":
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

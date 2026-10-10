#!/usr/bin/env python3
"""Bourses: validation et envoi de campagnes préparees dans le navigateur.

Aucun service réseau entrant. Pas de stockage de PDF hors ZIP d'entrée.
Le ZIP doit être conservé dans un répertoire privé, puis supprimé après recette.
"""
import argparse
import csv
import getpass
import hashlib
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
from pathlib import Path

SMTP_HOST = "smtp.education.gouv.fr"
SMTP_PORT = 587
IMAP_HOST = "imap.education.gouv.fr"
IMAP_PORT = 993
EMAIL = re.compile(r"^[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+$")
MAX_ZIP = 250 * 1024 * 1024
MAX_PDF = 20 * 1024 * 1024
MAX_MESSAGES = 1200


def check_email(addr):
    return isinstance(addr, str) and bool(EMAIL.fullmatch(addr))


def load_campaign(file):
    file = Path(file)
    if not file.is_file() or file.stat().st_size > MAX_ZIP:
        raise ValueError("Archive absente ou trop volumineuse")
    with zipfile.ZipFile(file) as z:
        members = z.infolist()
        if len(members) > 3500 or sum(m.file_size for m in members) > 2 * MAX_ZIP:
            raise ValueError("Archive trop volumineuse après décompression")
        names = [m.filename for m in members]
        if len(names) != len(set(names)) or "campagne.json" not in names:
            raise ValueError("campagne.json absent ou chemins dupliqués")
        for member in members:
            parts = member.filename.split("/")
            if (member.filename.startswith("/") or "\\" in member.filename or ".." in parts
                    or member.flag_bits & 1 or member.is_dir() and member.filename == "campagne.json"):
                raise ValueError("Entrée ZIP dangereuse")
        if z.getinfo("campagne.json").file_size > 5 * 1024 * 1024:
            raise ValueError("Manifeste trop volumineux")
        manifest = json.loads(z.read("campagne.json"))
        if manifest.get("schema_version") != 1 or manifest.get("source") != "Split-And-Rename-B":
            raise ValueError("Schéma de campagne bourses non reconnu")
        if manifest.get("status") != "PREPARE_NON_ENVOYE":
            raise ValueError("Statut initial invalide")
        messages = manifest.get("messages")
        if not isinstance(messages, list) or not 0 < len(messages) <= MAX_MESSAGES:
            raise ValueError("Nombre de messages invalide")
        used = set()
        for entry in messages:
            if not isinstance(entry, dict) or entry.get("status") != "PREPARE_NON_ENVOYE":
                raise ValueError("Message non préparé")
            recipients = entry.get("to")
            if not isinstance(recipients, list) or len(recipients) != 1 or not check_email(recipients[0]):
                raise ValueError("Chaque notification doit avoir un seul parent destinataire")
            name = entry.get("attachment")
            if (not isinstance(name, str) or not name.startswith("pieces_jointes/")
                    or not name.lower().endswith(".pdf") or name not in names or name in used):
                raise ValueError("Pièce jointe manquante, non PDF ou en doublon")
            used.add(name)
            if z.getinfo(name).file_size > MAX_PDF:
                raise ValueError("PDF trop volumineux")
            if not z.read(name).startswith(b"%PDF-"):
                raise ValueError("Pièce jointe invalide")
            for key, limit in (("subject", 500), ("body", 20000)):
                value = entry.get(key)
                if not isinstance(value, str) or not value.strip() or len(value) > limit:
                    raise ValueError("Objet ou texte invalide")
            if any(k in entry["subject"] for k in ("\r", "\n")):
                raise ValueError("Retour à la ligne dans l'objet")
            for key in ("eleve", "responsable"):
                person = entry.get(key)
                if not isinstance(person, dict) or not person.get("nom") or not person.get("prenom"):
                    raise ValueError("Identité incomplète dans le manifeste")
            if entry.get("decision") not in ("Refus", "Acceptation"):
                raise ValueError("Décision invalide")
        return manifest


def create_mail(entry, pdf, sender):
    mail = EmailMessage(policy=SMTP)
    mail["From"] = sender
    mail["To"] = entry["to"][0]
    mail["Subject"] = entry["subject"]
    mail["Date"] = formatdate(localtime=False)
    mail["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    mail.set_content(entry["body"])
    mail.add_attachment(pdf, maintype="application", subtype="pdf",
                        filename=Path(entry["attachment"]).name)
    return mail


def run(args):
    if not check_email(args.sender):
        raise ValueError("Adresse expéditeur invalide")
    manifest = load_campaign(args.zip)
    digest = hashlib.sha256(Path(args.zip).read_bytes()).hexdigest()
    report = Path(args.report).resolve()
    if report.exists():
        raise ValueError("Journal existant : refus de l'écraser")
    if args.send and (args.confirm != "ENVOYER" or not args.authorized):
        raise ValueError("Envoi réel : --confirm ENVOYER --authorized requis")
    if args.send and not args.state:
        raise ValueError("Envoi réel : --state /chemin/prive/etat.jsonl requis pour tracer la reprise")
    state = Path(args.state).resolve() if args.state else None
    delivered = set()
    if state and state.exists():
        with state.open(encoding="utf-8") as fp:
            for raw in fp:
                previous = json.loads(raw)
                if previous.get("digest") != digest:
                    raise ValueError("L'état de campagne ne correspond pas au ZIP")
                if previous.get("smtp") in ("ACCEPTE_PAR_RELAIS", "INCERTAIN_APRES_APPEL_SMTP"):
                    delivered.add(previous["index"])
    sender = args.sender
    password = getpass.getpass("Mot de passe académique (jamais enregistré) : ") if args.send else None
    smtp = None
    results = []
    try:
        if args.send:
            smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(sender, password)
        with zipfile.ZipFile(args.zip) as z:
            for index, entry in enumerate(manifest["messages"], 1):
                result = {"index": index, "date_utc": datetime.now(timezone.utc).isoformat(),
                          "zip_sha256": digest, "eleve": str(entry["eleve"]),
                          "responsable": str(entry["responsable"]),
                          "destinataire": entry["to"][0], "piece": entry["attachment"],
                          "message_id": "", "smtp": "NON_ENVOYE", "detail": ""}
                if index in delivered:
                    result["smtp"] = "DEJA_TRAITE_NE_PAS_REENVOYER"
                    results.append(result)
                    continue
                try:
                    mail = create_mail(entry, z.read(entry["attachment"]), sender)
                    result["message_id"] = str(mail["Message-ID"])
                    if not args.send:
                        result["smtp"] = "SIMULATION"
                    else:
                        # Journal conservateur : une coupure après l'appel SMTP peut signifier
                        # que le message a été accepté malgré l'absence de confirmation locale.
                        # La reprise automatique DOIT ignorer cet index.
                        result["smtp"] = "INCERTAIN_APRES_APPEL_SMTP"
                        with state.open("a", encoding="utf-8") as sf:
                            sf.write(json.dumps({"digest": digest, "index": index,
                                                 "smtp": result["smtp"]}) + "\n")
                            sf.flush()
                            os.fsync(sf.fileno())
                        refused = smtp.sendmail(sender, entry["to"], mail.as_bytes())
                        if refused:
                            result["smtp"] = "REFUSE_PAR_RELAIS"
                            result["detail"] = str(refused)[:400]
                        else:
                            result["smtp"] = "ACCEPTE_PAR_RELAIS"
                        with state.open("a", encoding="utf-8") as sf:
                            sf.write(json.dumps({"digest": digest, "index": index,
                                                 "smtp": result["smtp"]}) + "\n")
                            sf.flush()
                            os.fsync(sf.fileno())
                except Exception as exc:
                    result["detail"] = str(exc)[:400]
                    if result["smtp"] != "INCERTAIN_APRES_APPEL_SMTP":
                        result["smtp"] = "ERREUR"
                results.append(result)
                print(f"{index}/{len(manifest['messages'])} : {result['smtp']}", flush=True)
    finally:
        if smtp:
            try: smtp.quit()
            except Exception: pass
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=[
                "index", "date_utc", "zip_sha256", "eleve", "responsable",
                "destinataire", "piece", "message_id", "smtp", "detail"], delimiter=";")
            writer.writeheader()
            writer.writerows(results)
        os.chmod(report, 0o600)
        print("Journal :", report)
    return 0 if all(x["smtp"] in ("SIMULATION", "ACCEPTE_PAR_RELAIS",
                                  "DEJA_TRAITE_NE_PAS_REENVOYER") for x in results) else 2


def main():
    parser = argparse.ArgumentParser(description="Simulation/envoi de notifications bourses")
    parser.add_argument("zip")
    parser.add_argument("--sender", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--state", help="Fichier de reprise JSONL privé obligatoire en envoi réel")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--simulate", action="store_true")
    modes.add_argument("--send", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile,
            json.JSONDecodeError, smtplib.SMTPException) as exc:
        print("Erreur :", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

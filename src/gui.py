"""Interface Tkinter, sans accès réseau ni envoi des données."""
import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from bourses import traiter

class Interface(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Notifications de bourses — Séparation et renommage')
        self.geometry('790x460')
        self.source = tk.StringVar()
        self.messages = queue.Queue()
        ttk.Label(self, text='Dossier contenant les notifications PDF').pack(anchor='w', padx=16, pady=(16, 4))
        cadre = ttk.Frame(self); cadre.pack(fill='x', padx=16)
        ttk.Entry(cadre, textvariable=self.source).pack(side='left', expand=True, fill='x')
        ttk.Button(cadre, text='Parcourir', command=self.parcourir).pack(side='left', padx=8)
        self.lancer = ttk.Button(self, text='Traiter les PDF', command=self.demarrer)
        self.lancer.pack(anchor='w', padx=16, pady=12)
        self.barre = ttk.Progressbar(self, mode='indeterminate'); self.barre.pack(fill='x', padx=16)
        self.journal = tk.Text(self, state='disabled', wrap='word'); self.journal.pack(expand=True, fill='both', padx=16, pady=12)
        self.after(100, self.verifier)

    def parcourir(self):
        choix = filedialog.askdirectory()
        if choix: self.source.set(choix)

    def demarrer(self):
        chemin = Path(self.source.get())
        if not chemin.is_dir():
            messagebox.showerror('Dossier incorrect', 'Sélectionnez un dossier existant.'); return
        self.lancer.configure(state='disabled'); self.barre.start(12)
        def job():
            class VersUI(logging.Handler):
                def emit(inner_self, record): self.messages.put(inner_self.format(record))
            handler = VersUI(); handler.setFormatter(logging.Formatter('%(levelname)s : %(message)s'))
            logger = logging.getLogger('bourses'); logger.addHandler(handler); logger.setLevel(logging.INFO)
            try:
                stats = traiter(chemin)
                self.messages.put(f"Terminé : {stats['produits']} PDF créés, {stats['ignores']} blocs ignorés, {stats['erreurs']} erreurs.")
                self.messages.put(f'Sortie : {chemin / "export"}')
            except Exception as exc:
                self.messages.put(f'Erreur : {exc}')
            finally:
                logger.removeHandler(handler)
                self.messages.put(None)
        threading.Thread(target=job, daemon=True).start()

    def verifier(self):
        try:
            while True:
                ligne = self.messages.get_nowait()
                if ligne is None:
                    self.barre.stop(); self.lancer.configure(state='normal')
                else:
                    self.journal.configure(state='normal'); self.journal.insert('end', ligne + '\n')
                    self.journal.see('end'); self.journal.configure(state='disabled')
        except queue.Empty:
            pass
        self.after(100, self.verifier)

if __name__ == '__main__':
    Interface().mainloop()

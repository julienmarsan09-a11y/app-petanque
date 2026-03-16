# 🎯 Gestionnaire de Concours de Pétanque

Application web Python pour organiser des concours de pétanque en système suisse.

## ✨ Fonctionnalités

- **Système suisse** : appariements automatiques par niveau
- **Doublettes & Triplettes** : adapté aux deux formats
- **Classement en temps réel** : victoires, Buchholz, paniers
- **Interface responsive** : fonctionne sur téléphone et PC
- **Sauvegarde automatique** : les données sont conservées entre redémarrages

## 🚀 Installation rapide

### 1. Prérequis
- Python 3.10 ou plus récent
- Vérifiez : `python --version`

### 2. Installer les dépendances
```bash
pip install flask
```

### 3. Lancer l'application
```bash
python app.py
```

### 4. Ouvrir dans le navigateur
```
http://localhost:5000
```

## 📖 Utilisation

1. **Configurer** le concours (nom, format, nombre de tours)
2. **Inscrire** les équipes avec les noms des joueurs
3. **Démarrer** → les matchs du tour 1 se génèrent automatiquement
4. **Saisir les scores** au fil des matchs
5. **Passer au tour suivant** quand tous les matchs sont terminés
6. **Classement final** affiché à la fin des tours

## 🏆 Règles du classement

Les équipes sont classées dans cet ordre de priorité :
1. **Victoires** (nombre de matchs gagnés)
2. **Buchholz** (somme des victoires des adversaires rencontrés)
3. **Différence de paniers** (paniers marqués – paniers encaissés)
4. **Paniers marqués**

## 📁 Structure du projet

```
petanque/
├── app.py              # Application principale Flask
├── requirements.txt    # Dépendances Python
├── README.md
├── concours_data.json  # Créé automatiquement lors du 1er concours
└── templates/
    ├── base.html       # Template de base (header, style)
    ├── index.html      # Page d'accueil
    ├── configurer.html # Configuration du concours
    ├── inscriptions.html
    ├── matchs.html     # Saisie des scores
    └── classement.html # Classement et podium
```

## 💡 Pour les apprenants Python

Ce projet illustre plusieurs concepts importants :
- **Dataclasses** (`@dataclass`) pour modéliser les données
- **Flask** pour créer une application web
- **Jinja2** pour les templates HTML
- **JSON** pour la persistance des données
- **Type hints** pour documenter le code
- **Séparation métier / présentation** (logique dans `app.py`, affichage dans les templates)
# app-petanque
